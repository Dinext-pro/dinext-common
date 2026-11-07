import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval import api

USER = "list-approver@example.com"


def transition(parent, uuid, *, action="Approve", state="Approved", required=0):
	return frappe._dict(
		parent=parent,
		transition_uuid=uuid,
		action=action,
		next_state=state,
		allowed_role="Approver",
		comment_is_required=required,
	)


class TestWorkflowListActions(unittest.TestCase):
	def read_actions(self, tasks, transitions, *, allowed=None):
		with ExitStack() as stack:
			stack.enter_context(patch.object(frappe, "session", frappe._dict(user=USER)))
			stack.enter_context(
				patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True)
			)
			can_read = stack.enter_context(
				patch.object(api, "get_task_read_checker", return_value=allowed or (lambda row: True))
			)
			get_all = stack.enter_context(patch.object(frappe, "get_all", side_effect=[tasks, transitions]))
			result = api.get_common_list_transitions("Issue", '["ISS-1", "ISS-2", "ISS-1"]')
		can_read.assert_called_once_with(USER, monitored_only=False, require_source=True)
		self.assertEqual(
			get_all.call_args_list[0].kwargs["filters"],
			{
				"approver": USER,
				"reference_doctype": "Issue",
				"reference_name": ("in", ["ISS-1", "ISS-2"]),
				"round_status": "Open",
				"status": "Working",
				"source_deleted_at": ("is", "not set"),
			},
		)
		return result, get_all

	def test_list_intersects_transition_uuids_and_combines_comment_requirement(self):
		tasks = [
			frappe._dict(name="TASK-1", reference_name="ISS-1"),
			frappe._dict(name="TASK-2", reference_name="ISS-2"),
		]
		result, get_all = self.read_actions(
			tasks,
			[
				transition("TASK-1", "both"),
				transition("TASK-1", "first-only"),
				transition("TASK-2", "both", required=1),
				transition("TASK-2", "second-only"),
			],
		)
		self.assertEqual(
			result,
			[{
				"transition_uuid": "both",
				"action": "Approve",
				"next_state": "Approved",
				"allowed": "Approver",
				"comment_is_required": True,
			}],
		)
		self.assertEqual(get_all.call_count, 2)
		self.assertEqual(
			get_all.call_args.kwargs["filters"]["parent"], ("in", ["TASK-1", "TASK-2"])
		)

	def test_inaccessible_missing_or_ambiguous_task_removes_common_actions(self):
		first = frappe._dict(name="TASK-1", reference_name="ISS-1")
		second = frappe._dict(name="TASK-2", reference_name="ISS-2")
		duplicate = frappe._dict(name="TASK-3", reference_name="ISS-2")
		for tasks, allowed in (
			([first], None),
			([first, second], lambda row: row.name == "TASK-1"),
			([first, second, duplicate], None),
		):
			with self.subTest(tasks=tasks):
				result, get_all = self.read_actions(tasks, [], allowed=allowed)
				self.assertEqual(result, [])
				self.assertEqual(get_all.call_count, 1)

	def test_inconsistent_destination_and_ambiguous_uuid_are_excluded(self):
		tasks = [
			frappe._dict(name="TASK-1", reference_name="ISS-1"),
			frappe._dict(name="TASK-2", reference_name="ISS-2"),
		]
		result, _ = self.read_actions(tasks, [
			transition("TASK-1", "drift"),
			transition("TASK-2", "drift", state="Different"),
			transition("TASK-1", "duplicate"),
			transition("TASK-1", "duplicate"),
			transition("TASK-2", "duplicate"),
		])
		self.assertEqual(result, [])

	def test_bulk_rejects_a_selection_that_became_ambiguous(self):
		with (
			patch.object(frappe, "session", frappe._dict(user=USER)),
			patch.object(frappe, "get_all", return_value=["TASK-1", "TASK-2"]),
			patch.object(frappe, "db", SimpleNamespace(exists=lambda dt, filters: filters["parent"] == "TASK-1")),
			patch.object(api, "_", side_effect=lambda message: message),
			patch.object(api.engine, "cast_vote") as cast_vote,
		):
			with self.assertRaises(api.engine.WorkflowApprovalConflictError):
				api._vote_source_action(
					"Issue", "ISS-1", "Approve", transition_uuid="matching", completion_source="Bulk",
				)
		cast_vote.assert_not_called()

	def test_progress_reports_commit_and_rollback_including_failed_document(self):
		events = []
		db = SimpleNamespace(
			commit=lambda: events.append("commit"),
			rollback=lambda: events.append("rollback"),
		)
		with (
			patch.object(frappe, "db", db),
			patch.object(frappe, "session", frappe._dict(user=USER)),
			patch.object(api, "_require_post"),
			patch.object(api, "_", side_effect=lambda message: message),
			patch.object(
				api, "_vote_source_action", side_effect=[{}, frappe.PermissionError("private")]
			),
			patch.object(
				frappe, "publish_realtime", side_effect=lambda *args, **kwargs: events.append((args, kwargs))
			),
		):
			result = api.bulk_vote("Issue", ["A", "B"], "Approve", request_id="req-1", track_progress=True)
		self.assertEqual(result["failed"][0]["error_type"], "Unavailable")
		self.assertEqual([events[0], events[2]], ["commit", "rollback"])
		for i in range(1, 3):
			args, kwargs = events[2 * i - 1]
			self.assertEqual(args, ("dinext_workflow_progress", {"request_id": "req-1", "count": i, "total": 2}))
			self.assertEqual(kwargs, {"room": f"user:{USER}"})

	def test_bulk_returns_outcomes_or_job_reference(self):
		with (
			patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True),
			patch.object(api, "bulk_vote", return_value={"succeeded": [], "failed": []}) as vote,
			patch.object(frappe, "msgprint"),
			patch.object(frappe, "enqueue", return_value=object()) as enqueue,
		):
			self.assertEqual(
				api.bulk_workflow_approval(["A", "B"], "Issue", "Approve", track_progress=True),
				{"succeeded": [], "failed": []},
			)
			vote.assert_called_once()
			response = api.bulk_workflow_approval(
				[str(i) for i in range(20)], "Issue", "Approve", track_progress=True
			)
		self.assertEqual(enqueue.call_args.kwargs["job_id"], response["job_id"])
		self.assertTrue(enqueue.call_args.kwargs["track_progress"])

	def test_background_results_are_scoped_to_initiator_and_site(self):
		from unittest.mock import Mock

		token = "1" * 32
		result = {"succeeded": [], "failed": []}
		job = Mock(
			kwargs={"user": USER, "site": "test", "method": "dinext_common.workflow_approval.api.bulk_vote"}
		)
		job.get_status.return_value = "finished"
		job.return_value.return_value = result
		with (
			patch.object(frappe, "session", frappe._dict(user=USER)),
			patch.object(frappe.local, "site", "test", create=True),
			patch("frappe.utils.background_jobs.get_job", return_value=job),
		):
			self.assertEqual(api.get_bulk_workflow_job(token), {"status": "finished", "result": result})
			job.kwargs["user"] = "someone-else"
			self.assertEqual(api.get_bulk_workflow_job(token), {"status": "unavailable"})
			job.kwargs.update(user=USER, site="another-site")
			self.assertEqual(api.get_bulk_workflow_job(token), {"status": "unavailable"})
