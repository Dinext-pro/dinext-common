"""Integration coverage for mandatory-target pending display selection."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.workflow_approval import api, pending


class PendingFixture:
	def setUp(self):
		super().setUp()
		self.round_id = frappe.generate_hash(length=40)
		self.workflow = self.make_workflow()
		self.source = frappe.get_doc(
			{
				"doctype": "ToDo",
				"name": "_Test Pending " + frappe.generate_hash(length=12),
				"description": "Mandatory pending display",
				"status": "Open",
			}
		)
		self.source.db_insert()

	def make_workflow(self, *, optional=False, doctype="ToDo"):
		workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"name": "_Test Pending WF " + frappe.generate_hash(length=12),
				"workflow_name": "Pending display fixture",
				"document_type": doctype,
				"workflow_state_field": "status",
				"is_active": 0,
			}
		)
		workflow.workflow_name = workflow.name
		workflow.db_insert()
		for state, flag in [("Open", 1), ("Required", int(optional)), ("Optional", 1)]:
			row = frappe.get_doc(
				{
					"doctype": "Workflow Document State",
					"parent": workflow.name,
					"parenttype": "Workflow",
					"parentfield": "states",
					"state": state,
					"doc_status": "0",
					"is_optional_state": flag,
				}
			)
			row.db_insert()
		return workflow

	def task(self, actor, targets, *, source=None, workflow=None, status="Working", round_status="Open"):
		source = source or self.source
		workflow = workflow or self.workflow
		task = frappe.get_doc(
			{
				"doctype": "Workflow Task",
				"name": "_Test Pending Task " + frappe.generate_hash(length=12),
				"workflow": workflow.name,
				"reference_doctype": source.doctype,
				"reference_name": source.name,
				"approver": actor,
				"user": actor,
				"status": status,
				"round_status": round_status,
				"workflow_state": "Open",
				"approval_round_id": self.round_id,
				"round_manifest": "{}",
				"next_state": "Optional",
			}
		)
		task.db_insert()
		for target in targets:
			row = frappe.get_doc(
				{
					"doctype": "Available Workflow Transitions",
					"parent": task.name,
					"parenttype": "Workflow Task",
					"parentfield": "available_workflow_transitions",
					"state": "Open",
					"action": "Choose " + target,
					"next_state": target,
				}
			)
			row.db_insert()
		return task

	def rows(self):
		return pending.get_required_state_pending_tasks(self.source.doctype, [self.source.name])


class TestRequiredStatePending(PendingFixture, FrappeTestCase):
	def test_required_and_mixed_targets_are_included_once(self):
		self.task("required@example.com", ["Required"])
		self.task("optional@example.com", ["Optional"])
		self.task("mixed@example.com", ["Optional", "Required", "Required"])
		self.assertEqual(
			[row["approver"] for row in self.rows()], ["mixed@example.com", "required@example.com"]
		)

	def test_optional_current_state_does_not_hide_mandatory_targets(self):
		self.task("required@example.com", ["Required"])
		self.assertEqual(len(self.rows()), 1)

	def test_optional_only_targets_are_empty(self):
		self.task("optional@example.com", ["Optional"])
		self.assertEqual(self.rows(), [])

	def test_unknown_target_is_not_treated_as_mandatory(self):
		self.task("unknown@example.com", ["Missing"])
		self.assertEqual(self.rows(), [])

	def test_state_names_are_scoped_to_their_workflow(self):
		other = self.make_workflow(optional=True)
		self.task("required@example.com", ["Required"])
		self.task("optional@example.com", ["Required"], workflow=other)
		self.assertEqual([row["approver"] for row in self.rows()], ["required@example.com"])

	def test_completed_and_non_open_tasks_are_excluded(self):
		self.task("completed@example.com", ["Required"], status="Completed")
		self.task("stalled@example.com", ["Required"], round_status="Stalled")
		self.task("cancelled@example.com", ["Required"], status="Cancelled", round_status="Cancelled")
		self.task("working@example.com", ["Required"])
		self.assertEqual([row["approver"] for row in self.rows()], ["working@example.com"])

	def test_empty_approvers_and_missing_options_are_excluded(self):
		self.task(None, ["Required"])
		self.task("empty@example.com", [])
		self.assertEqual(self.rows(), [])

	def test_live_flag_change_does_not_modify_the_task(self):
		task = self.task("required@example.com", ["Required"])
		before = frappe.db.get_value(
			"Workflow Task", task.name, ["modified", "status", "round_status", "round_manifest"], as_dict=True
		)
		self.assertEqual(len(self.rows()), 1)
		frappe.db.set_value(
			"Workflow Document State",
			{"parent": self.workflow.name, "state": "Required"},
			"is_optional_state",
			1,
		)
		self.assertEqual(self.rows(), [])
		frappe.db.set_value(
			"Workflow Document State",
			{"parent": self.workflow.name, "state": "Required"},
			"is_optional_state",
			0,
		)
		self.assertEqual(len(self.rows()), 1)
		self.assertEqual(before, frappe.db.get_value("Workflow Task", task.name, list(before), as_dict=True))

	def test_pending_api_preserves_public_keys(self):
		self.task("required@example.com", ["Required"])
		rows = api.get_pending_approvers(self.source.doctype, self.source.name)
		self.assertEqual(len(rows), 1)
		self.assertEqual(set(rows[0]), {"approver", "approver_name", "approval_round_id", "workflow_state"})

	def test_optional_only_banner_preserves_open_round_metadata(self):
		self.task("optional@example.com", ["Optional"])
		with patch.object(api, "describe_rebuild_rounds", return_value=[]):
			banner = api.get_form_approval_banner(self.source.doctype, self.source.name)
		self.assertEqual(banner["round_status"], "Open")
		self.assertEqual(banner["round_id"], self.round_id)
		self.assertEqual(banner["pending_approvers"], [])

	def test_rebuild_indicator_is_not_filtered(self):
		self.task("optional@example.com", ["Optional"], round_status="Stalled")
		round_info = {
			"round_id": self.round_id,
			"round_status": "Stalled",
			"can_reset": True,
			"configuration_change": None,
		}
		with patch.object(api, "describe_rebuild_rounds", return_value=[round_info]):
			banner = api.get_form_approval_banner(self.source.doctype, self.source.name)
		self.assertEqual(
			banner,
			{
				"round_id": self.round_id,
				"round_status": "Stalled",
				"pending_approvers": [],
				"can_reset": True,
				"configuration_change": None,
				"rounds": [round_info],
			},
		)

	def test_pending_banner_coexists_with_rebuild_metadata(self):
		self.task("required@example.com", ["Required"])
		self.task("optional@example.com", ["Optional"])
		self.round_id = frappe.generate_hash(length=40)
		self.task("stalled@example.com", ["Required"], round_status="Stalled")
		metadata = {"reason": "configuration_changed", "void": [{"action": "Approve"}], "stable": []}
		round_info = {
			"round_id": self.round_id,
			"round_status": "Stalled",
			"reference_name": self.source.name,
			"source_title": "Pending display fixture",
			"can_reset": True,
			"configuration_change": metadata,
		}
		with patch.object(api, "describe_rebuild_rounds", return_value=[round_info]):
			banner = api.get_form_approval_banner(self.source.doctype, self.source.name)
		self.assertEqual(
			banner,
			{
				"round_id": self.round_id,
				"round_status": "Stalled",
				"pending_approvers": [
					{"approver": "required@example.com", "approver_name": "required@example.com"}
				],
				"can_reset": True,
				"configuration_change": metadata,
				"rounds": [round_info],
			},
		)

	def test_apis_authorize_source_before_selecting_names(self):
		source = SimpleNamespace(check_permission=Mock(side_effect=frappe.PermissionError))
		with (
			patch.object(api.frappe, "get_doc", return_value=source),
			patch.object(api, "get_required_state_pending_tasks") as select,
		):
			for endpoint in [api.get_pending_approvers, api.get_form_approval_banner]:
				with self.assertRaises(frappe.PermissionError):
					endpoint("ToDo", "private")
		select.assert_not_called()

	def test_large_cohort_is_filtered_without_a_limit_or_per_user_queries(self):
		for index in range(105):
			self.task(f"a-optional-{index:03}@example.com", ["Optional"])
		self.task("z-required@example.com", ["Required"])
		self.rows()  # Warm metadata before measuring the fixed batch query count.
		with patch.object(pending.frappe, "get_all", wraps=frappe.get_all) as query:
			rows = self.rows()
		self.assertEqual([row["approver"] for row in rows], ["z-required@example.com"])
		self.assertEqual(query.call_count, 3)

	def test_empty_reference_set_does_not_query(self):
		with patch.object(pending.frappe, "get_all") as query:
			self.assertEqual(pending.get_required_state_pending_tasks("ToDo", []), [])
		query.assert_not_called()
