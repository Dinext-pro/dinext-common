"""Legacy approvals acquire process lineage without changing recorded decisions."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from dinext_common.workflow_approval.scenarios.metadata import next_selection_order
from dinext_common.workflow_approval.scenarios.migration import adopt_legacy_sources
from dinext_common.workflow_approval.scenarios.service import source_key


class TestWorkflowScenarioMigrationIntegration(FrappeTestCase):
	def test_active_and_historical_rounds_keep_ids_votes_times_and_assignments(self):
		frappe.set_user("Administrator")
		prefix = "_Test Legacy Scenario " + frappe.generate_hash(length=8)
		source = frappe.get_doc({"doctype": "Note", "title": prefix}).insert(ignore_permissions=True)
		state = frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": prefix + " Draft"}
		).insert(ignore_permissions=True)
		workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": prefix,
				"document_type": "Note",
				"workflow_state_field": "content",
				"is_active": 0,
				"custom_selection_order": next_selection_order("Note"),
				"states": [{"state": state.name, "doc_status": "0", "allow_edit": "All"}],
			}
		).insert(ignore_permissions=True)
		completed_at = now_datetime()
		tasks = []
		for suffix, status, round_status, round_id in [
			("working", "Working", "Open", prefix + " current"),
			("voted", "Completed", "Open", prefix + " current"),
			("history", "Completed", "Transitioned", prefix + " previous"),
		]:
			tasks.append(
				frappe.get_doc(
					{
						"doctype": "Workflow Task",
						"name": prefix + suffix,
						"doc": source.doctype,
						"wt_docname": source.name,
						"reference_doctype": source.doctype,
						"reference_name": source.name,
						"source_created_at": source.creation,
						"workflow": workflow.name,
						"workflow_state": state.name,
						"approval_round_id": round_id,
						"status": status,
						"round_status": round_status,
						"approver": "Administrator",
						"completion_source": "Manual" if status == "Completed" else None,
						"completed_at": completed_at if status == "Completed" else None,
						"vote_comment": "Original reviewer comment" if status == "Completed" else None,
						"transition_uuid": "legacy-transition" if status == "Completed" else None,
						"transition_semantic_hash": "legacy-hash" if status == "Completed" else None,
					}
				).insert(ignore_permissions=True)
			)
		# Foreign site scripts are unrelated to offline migration and may be disabled.
		with patch("frappe.model.document.run_server_script_for_doc_event"):
			assignment = frappe.get_doc(
				{
					"doctype": "ToDo",
					"description": "Legacy approval",
					"status": "Open",
					"reference_type": "Workflow Task",
					"reference_name": tasks[0].name,
					"allocated_to": "Administrator",
				}
			).insert(ignore_permissions=True)

		def snapshot():
			rows = []
			for task in tasks:
				row = frappe.get_doc("Workflow Task", task.name).as_dict()
				row.pop("workflow_process", None)
				rows.append(row)
			return frappe.as_json(rows)

		before = snapshot()
		adopt_legacy_sources()
		self.assertEqual(snapshot(), before)
		self.assertEqual(frappe.db.get_value("ToDo", assignment.name, "status"), "Open")
		context = frappe.get_doc("Workflow Document Context", source_key(source))
		self.assertEqual(frappe.db.get_value("Workflow Process", context.active_process, "status"), "Running")
		self.assertEqual(
			frappe.db.get_value("Workflow Task", tasks[0].name, "workflow_process"), context.active_process
		)
		self.assertEqual(
			frappe.db.get_value("Workflow Task", tasks[1].name, "workflow_process"), context.active_process
		)
		historical = frappe.db.get_value("Workflow Task", tasks[2].name, "workflow_process")
		self.assertNotEqual(historical, context.active_process)
		self.assertEqual(frappe.db.get_value("Workflow Process", historical, "status"), "Completed")
		count = frappe.db.count("Workflow Process", {"source_key": source_key(source)})
		self.assertEqual(adopt_legacy_sources(), 0)
		self.assertEqual(frappe.db.count("Workflow Process", {"source_key": source_key(source)}), count)
		self.assertEqual(snapshot(), before)

	def test_removed_legacy_workflow_is_archived_without_changing_its_task(self):
		from dinext_common.workflow_approval.scenarios import service

		prefix = "_Test Removed Scenario " + frappe.generate_hash(length=8)
		source = frappe.get_doc({"doctype": "Note", "title": prefix}).insert(ignore_permissions=True)
		task = frappe.get_doc(
			{
				"doctype": "Workflow Task",
				"name": prefix,
				"doc": "Note",
				"wt_docname": source.name,
				"reference_doctype": "Note",
				"reference_name": source.name,
				"source_created_at": source.creation,
				"workflow": prefix + " deleted",
				"workflow_state": "Draft",
				"approval_round_id": prefix + " round",
				"status": "Working",
				"round_status": "Open",
				"approver": "Administrator",
			}
		).insert(ignore_permissions=True, ignore_links=True)
		before = task.as_dict()
		service.adopt_legacy_source(source, [before])
		task.reload()
		self.assertEqual(task.status, "Working")
		self.assertEqual(task.approval_round_id, before["approval_round_id"])
		self.assertEqual(frappe.db.get_value(service.PROCESS, task.workflow_process, "status"), "Archived")
		self.assertIsNone(frappe.db.get_value(service.CONTEXT, service.source_key(source), "active_process"))

	def test_worker_adopts_its_legacy_round_before_routing_another_schema(self):
		from dinext_common.workflow_approval.scenarios import service

		prefix = "_Test Worker Adoption " + frappe.generate_hash(length=8)
		source = frappe.get_doc({"doctype": "Note", "title": prefix, "content": prefix + " Draft"}).insert(
			ignore_permissions=True
		)
		state = frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": prefix + " Draft"}
		).insert(ignore_permissions=True)
		workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": prefix,
				"document_type": "Note",
				"workflow_state_field": "content",
				"is_active": 0,
				"custom_activation_condition": "False",
				"custom_selection_order": next_selection_order("Note"),
				"states": [{"state": state.name, "doc_status": "0", "allow_edit": "All"}],
			}
		).insert(ignore_permissions=True)
		task = frappe.get_doc(
			{
				"doctype": "Workflow Task",
				"name": prefix,
				"doc": "Note",
				"wt_docname": source.name,
				"reference_doctype": "Note",
				"reference_name": source.name,
				"source_created_at": source.creation,
				"workflow": workflow.name,
				"workflow_state": state.name,
				"approval_round_id": prefix + " round",
				"status": "Working",
				"round_status": "Open",
				"approver": "Administrator",
			}
		).insert(ignore_permissions=True)
		context = service.ensure_context(source, persist_state=True)
		self.assertEqual(context["workflow"], workflow.name)
		self.assertEqual(context["process_status"], "Running")
		service.validate_task(source, task)
		self.assertEqual(task.workflow_process, context["process_id"])
		self.assertEqual(task.status, "Working")
