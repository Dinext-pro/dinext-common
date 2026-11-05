import unittest
from types import SimpleNamespace
from unittest.mock import patch


class TestWorkflowApprovalAPI(unittest.TestCase):
	def api(self):
		try:
			from dinext_common.workflow_approval import api
		except (ImportError, ModuleNotFoundError) as exc:
			self.fail(f"workflow approval API module is missing: {exc}")
		return api

	def test_mutating_api_requires_post(self):
		api = self.api()
		request = SimpleNamespace(method="GET")
		with (
			patch.object(api.frappe.local, "request", request, create=True),
			self.assertRaises(api.frappe.PermissionError),
		):
			api._require_post()

		request.method = "POST"
		with patch.object(api.frappe.local, "request", request, create=True):
			api._require_post()

	def test_vote_delegates_to_engine_with_typed_arguments(self):
		api = self.api()
		expected = {"task": "WT-1", "status": "Completed"}
		with (
			patch.object(api, "_require_post"),
			patch.object(api.engine, "cast_vote", return_value=expected) as cast_vote,
		):
			self.assertEqual(
				api.vote(
					"WT-1",
					transition_uuid="tr-1",
					comment="ok",
					request_id="req-1",
				),
				expected,
			)
		cast_vote.assert_called_once_with(
			"WT-1",
			transition_uuid="tr-1",
			action=None,
			comment="ok",
			request_id="req-1",
			completion_source="Manual",
		)

	def test_queue_loads_transitions_in_order_only_for_readable_tasks(self):
		from dinext_common.workflow_approval import permissions

		api = self.api()
		frappe = api.frappe
		user = "alice@example.com"
		tasks = [
			frappe._dict(name=name, approver=user, reference_doctype="Issue", reference_name=name)
			for name in ("READABLE", "HIDDEN")
		]
		transitions = [
			frappe._dict(
				parent="READABLE",
				transition_uuid=uuid,
				action="Approve",
				next_state="Approved",
				allowed_role="Approver",
				comment_is_required=required,
			)
			for uuid, required in (("first", 1), ("second", 0))
		]
		with (
			patch.object(frappe, "session", frappe._dict(user=user)),
			patch.object(frappe, "get_roles", return_value=[]),
			patch.object(frappe, "get_all", side_effect=[tasks, transitions]) as get_all,
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(
				permissions,
				"_has_source_read_permission",
				side_effect=lambda row, _: row["reference_name"] == "READABLE",
			),
		):
			result = api.get_my_queue()

		self.assertEqual([row.name for row in result], ["READABLE"])
		self.assertEqual(
			result[0].available_transitions,
			[
				{
					"transition_uuid": uuid,
					"action": "Approve",
					"next_state": "Approved",
					"allowed": "Approver",
					"comment_is_required": required,
				}
				for uuid, required in (("first", True), ("second", False))
			],
		)
		self.assertEqual(get_all.call_count, 2)
		self.assertEqual(get_all.call_args.args, ("Available Workflow Transitions",))
		self.assertEqual(get_all.call_args.kwargs["filters"]["parent"], ("in", ["READABLE"]))
		self.assertEqual(get_all.call_args.kwargs["order_by"], "idx asc")
		get_doc.assert_not_called()

	def test_bulk_returns_itemized_success_and_failure(self):
		api = self.api()
		with (
			patch.object(api, "_require_post"),
			patch.object(
				api,
				"_vote_source_action",
				side_effect=[{"task": "WT-1"}, api.engine.WorkflowApprovalConflictError("closed")],
			),
			patch.object(api.frappe.db, "savepoint"),
			patch.object(api.frappe.db, "release_savepoint"),
			patch.object(api.frappe.db, "rollback"),
		):
			result = api.bulk_vote(
				"Example",
				["EX-1", "EX-2"],
				"Approve",
				request_id="bulk-1",
			)

		self.assertEqual(result["succeeded"][0]["name"], "EX-1")
		self.assertEqual(result["failed"][0]["name"], "EX-2")
		self.assertEqual(result["failed"][0]["error"], "closed")

	def test_report_bulk_deduplicates_task_and_commits_each_success(self):
		api = self.api()
		items = [
			{"task_name": "WT-1", "transition_uuid": "tr-1", "action": "Approve"},
			{"task_name": "WT-1", "transition_uuid": "tr-1", "action": "Approve"},
		]
		with (
			patch.object(api, "_require_post"),
			patch.object(
				api.engine,
				"cast_vote",
				return_value={"task": "WT-1", "status": "Completed"},
			) as cast_vote,
			patch.object(api.frappe.db, "commit") as commit,
		):
			result = api.bulk_task_vote(items, request_id="bulk-1")

		self.assertEqual(len(result["succeeded"]), 1)
		cast_vote.assert_called_once()
		commit.assert_called_once()

	def test_legacy_card_state_matches_english_and_russian_position_tasks(self):
		api = self.api()
		seen = {}

		def capture(doctype, filters=None, **kwargs):
			seen["filters"] = filters
			seen["limit"] = kwargs.get("limit_page_length")
			return []

		with (
			patch.object(api.frappe, "get_all", side_effect=capture),
			patch.object(api.frappe, "session", SimpleNamespace(user="approver@example.com")),
		):
			api.get_legacy_number_card_result(
				{
					"doc": "User Timesheet Position",
					"state": "Согласовано",
					"route": "user-timesheet-position",
				}
			)

		self.assertEqual(seen["filters"]["status"], "Completed")
		self.assertEqual(seen["filters"]["next_state"][0], "in")
		self.assertIn("Approved", seen["filters"]["next_state"][1])
		self.assertIn("Согласовано", seen["filters"]["next_state"][1])

	def test_describe_rebuild_rounds_returns_every_stalled_document(self):
		api = self.api()
		rows = [
			SimpleNamespace(
				approval_round_id="ROUND-2",
				round_status="Conflicted",
				reference_name="DOC-2",
				source_title="Second",
				failure_metadata={
					"reason": "configuration_changed",
					"stable": [],
					"void": [{"action": "Drop"}],
					"added": [],
				},
			),
			SimpleNamespace(
				approval_round_id="ROUND-2",
				round_status="Conflicted",
				reference_name="DOC-2",
				source_title="Second",
				failure_metadata=None,
			),
			SimpleNamespace(
				approval_round_id="ROUND-1",
				round_status="Stalled",
				reference_name="DOC-1",
				source_title="",
				failure_metadata=None,
			),
		]
		with (
			patch.object(api.frappe, "get_all", return_value=rows) as get_all,
			patch.object(api, "_caller_is_system_manager", return_value=False),
		):
			result = api.describe_rebuild_rounds("ToDo", ["DOC-1", "DOC-2"])

		self.assertEqual([row["round_id"] for row in result], ["ROUND-2", "ROUND-1"])
		self.assertEqual(result[0]["reference_name"], "DOC-2")
		self.assertEqual(result[0]["configuration_change"]["void"][0]["action"], "Drop")
		self.assertIsNone(result[1]["configuration_change"])
		self.assertEqual(result[1]["source_title"], "DOC-1")
		self.assertFalse(any(row["can_reset"] for row in result))
		self.assertEqual(get_all.call_args.kwargs["filters"]["reference_doctype"], "ToDo")
		self.assertNotIn("User Timesheet", str(get_all.call_args))
