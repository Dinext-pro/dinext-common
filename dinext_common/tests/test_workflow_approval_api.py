import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


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

	def test_queue_filters_each_task_through_source_aware_permission(self):
		api = self.api()
		rows = [
			SimpleNamespace(name="WT-1"),
			SimpleNamespace(name="WT-2"),
		]
		mock_frappe = MagicMock()
		mock_frappe.session.user = "alice@example.com"
		mock_frappe.get_all.return_value = [{"name": "WT-1"}, {"name": "WT-2"}]
		mock_frappe.get_doc.side_effect = rows

		with (
			patch.object(api, "frappe", mock_frappe),
			patch.object(
				api,
				"has_workflow_task_permission",
				side_effect=[True, False],
			),
		):
			result = api.get_my_queue()
		self.assertEqual([row["name"] for row in result], ["WT-1"])

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

		def capture(filters, limit=500):
			seen["filters"] = filters
			seen["limit"] = limit
			return []

		with (
			patch.object(api, "_filtered_tasks", side_effect=capture),
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
