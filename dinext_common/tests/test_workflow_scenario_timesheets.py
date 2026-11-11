import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe


class TestWorkflowScenarioTimesheets(unittest.TestCase):
	def adapter(self):
		try:
			return importlib.import_module("dinext_common.workflow_approval.scenarios.timesheet_actions")
		except ImportError as error:
			self.fail(f"Timesheet scenario adapter is missing: {error}")

	def option(self, name, workflow, process, uuid, required=False):
		return {"action": "Approve", "next_state": "Approved", "mode": "vote", "task": f"TASK-{name}",
			"workflow": workflow, "process_id": process, "transition_uuid": uuid, "comment_is_required": required}

	def test_mixed_positions_keep_each_transition_identity_and_require_one_comment(self):
		adapter = self.adapter()
		result = adapter.group_position_actions({"A": "Waiting", "B": "Waiting"}, {
			"A": [self.option("A", "Alpha", "P-A", "UUID-A")],
			"B": [self.option("B", "Beta", "P-B", "UUID-B", True)],
		})
		self.assertEqual(len(result), 1)
		self.assertTrue(result[0]["comment_is_required"])
		self.assertEqual(result[0]["targets"], [
			{"name": "A", "workflow": "Alpha", "process_id": "P-A", "task_name": "TASK-A", "transition_uuid": "UUID-A", "next_state": "Approved"},
			{"name": "B", "workflow": "Beta", "process_id": "P-B", "task_name": "TASK-B", "transition_uuid": "UUID-B", "next_state": "Approved"},
		])

	def test_ambiguous_action_on_one_position_is_not_offered_on_the_parent(self):
		adapter = self.adapter()
		result = adapter.group_position_actions({"A": "Waiting", "B": "Waiting"}, {
			"A": [self.option("A", "Alpha", "P-A", "UUID-A"), self.option("A", "Alpha", "P-A", "UUID-A2")],
			"B": [self.option("B", "Beta", "P-B", "UUID-B")],
		})
		self.assertEqual(result, [])

	def test_a_completed_voter_cannot_use_domain_fallback_to_bypass_remaining_quorum(self):
		adapter = self.adapter()
		doc = SimpleNamespace(name="A")
		with (
			patch.object(adapter.service, "get_context", return_value={"workflow": "Alpha", "process_id": "P-A"}),
			patch.object(frappe, "get_all", return_value=[]),
			patch.object(frappe, "session", frappe._dict(user="approver@example.com")),
			patch("frappe.model.workflow.get_transitions", return_value=[frappe._dict(
				action="Approve", next_state="Approved", allow_self_approval=1, custom_transition_uuid="UUID-A")]),
		):
			self.assertEqual(adapter._position_action_items(doc), [])

	def test_stale_process_cannot_be_replaced_by_new_parent_discovery(self):
		adapter = self.adapter()
		expected = [{"name": "A", "workflow": "Alpha", "process_id": "P-A2", "task_name": "TASK-A2", "transition_uuid": "UUID-A"}]
		supplied = [{"name": "A", "workflow": "Alpha", "process_id": "P-A", "task_name": "TASK-A", "transition_uuid": "UUID-A"}]
		with self.assertRaises(frappe.ValidationError):
			adapter.validate_targets(expected, supplied)

	def test_parent_request_replay_uses_completed_task_before_discovering_a_repeated_process(self):
		adapter = self.adapter()
		self.assertTrue(callable(getattr(adapter, "_replay_parent_action", None)), "Parent replay guard is missing")
		parent = SimpleNamespace(name="UT-1", creation="2026-11-01", check_permission=lambda permission: None)
		source = SimpleNamespace(name="A", creation="2026-11-02", check_permission=lambda permission: None)
		task = frappe._dict(name="TASK-A", reference_name="A", workflow="Alpha", workflow_process="P-A",
			transition_uuid="UUID-A", correlation_id="request-1:0", action="Approve", source_created_at="2026-11-02")
		with (
			patch.object(adapter, "_enabled", return_value=True),
			patch.object(adapter, "_producer", return_value=SimpleNamespace()),
			patch.object(frappe, "cache", SimpleNamespace(get_value=lambda key: None)),
			patch.object(frappe, "get_doc", side_effect=lambda doctype, *args, **kwargs: parent if doctype == "User Timesheet" else source),
			patch.object(frappe, "get_all", side_effect=lambda doctype, **kwargs: ["A"] if doctype == adapter.POSITION else [task]),
			patch.object(frappe, "session", frappe._dict(user="approver@example.com")),
			patch.object(frappe.local, "flags", frappe._dict(in_test=True), create=True),
			patch("dinext_common.workflow_approval.api._require_post"),
			patch.object(adapter, "get_timesheet_position_actions", side_effect=AssertionError("Must not discover a new process")),
			patch.object(adapter.engine, "cast_vote", return_value={"task": "TASK-A", "transitioned": True}),
		):
			response = adapter.apply_timesheet_position_action("UT-1", "Approve", request_id="request-1")
		self.assertEqual(response["results"], [{"task": "TASK-A", "transitioned": True}])
		self.assertEqual(response["processed"], 1)

	def test_parent_cascade_uses_selected_state_even_when_legacy_mirror_already_matches(self):
		adapter = self.adapter()
		self.assertTrue(callable(getattr(adapter, "recalculate_parent", None)), "Context-aware rollup is missing")
		parent = SimpleNamespace(name="UT-1", ut_status="Approved", ut_approval_date="old", save=lambda **kw: None)
		sibling = SimpleNamespace(name="B", doctype=adapter.POSITION, custom_state="Waiting", workflow_state="Editing")
		changed = SimpleNamespace(name="A", doctype=adapter.POSITION, custom_state="Editing")
		producer = SimpleNamespace(_note_timesheet_transition_message=lambda message: None)
		def apply(doctype, name, state, **kwargs):
			sibling.custom_state = state
		with (
			patch.object(adapter, "_enabled", return_value=True),
			patch.object(adapter, "_producer", return_value=producer),
			patch.object(adapter, "_position_status_counts", return_value={"Editing": 1, "Waiting": 1}),
			patch.object(adapter, "_rollup_settings", return_value=(lambda counts: {
				"timesheet_status": "Rework", "position_status": "Editing", "move_all_positions": 1}, lambda: None)),
			patch.object(frappe, "get_all", return_value=["B"]),
			patch.object(frappe, "get_doc", return_value=sibling),
			patch.object(frappe.local, "flags", frappe._dict(in_timesheet_approval_cascade=False), create=True),
			patch.object(frappe, "session", frappe._dict(user="approver@example.com")),
			patch.object(adapter.service, "get_context", return_value={"workflow": "Beta", "state": "Waiting"}),
			patch.object(adapter.engine, "apply_domain_transition", side_effect=apply),
		):
			adapter.recalculate_parent(parent, changed, "Approved")
		self.assertEqual(sibling.custom_state, "Editing")
		self.assertEqual(parent.ut_status, "Rework")
		self.assertIsNone(parent.ut_approval_date)
