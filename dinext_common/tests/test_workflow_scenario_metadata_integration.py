"""Native Workflow saves keep peers active and the database guards routing order."""

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.workflow_approval.scenarios.metadata import next_selection_order


class TestWorkflowScenarioMetadataIntegration(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.prefix = "_Test Scenario Metadata " + frappe.generate_hash(length=8)
		self.state = self.prefix + " Draft"
		frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": self.state}).insert(ignore_permissions=True)

	def workflow(self, suffix, **values):
		return frappe.get_doc({
			"doctype": "Workflow",
			"workflow_name": self.prefix + suffix,
			"document_type": "Note",
			# Existing optional source field avoids metadata DDL inside transactional tests.
			"workflow_state_field": "content",
			"is_active": 1,
			"send_email_alert": 0,
			"custom_selection_order": next_selection_order("Note"),
			"states": [{"state": self.state, "doc_status": "0", "allow_edit": "All"}],
			**values,
		}).insert(ignore_permissions=True)

	def test_two_native_saves_keep_both_active_and_do_not_initialize_existing_sources(self):
		note = frappe.get_doc({"doctype": "Note", "title": self.prefix, "content": ""}).insert(ignore_permissions=True)
		# Text Editor normalizes an empty string, so reproduce a stored legacy blank.
		frappe.db.set_value("Note", note.name, "content", None)
		first = self.workflow(" A")
		second = self.workflow(" B")
		self.assertEqual(frappe.db.get_value("Workflow", first.name, "is_active"), 1)
		self.assertEqual(frappe.db.get_value("Workflow", second.name, "is_active"), 1)
		self.assertFalse(frappe.db.get_value("Note", note.name, "content"))

	def test_inactive_duplicate_is_rejected_by_native_save(self):
		first = self.workflow(" A", is_active=0)
		with self.assertRaises(frappe.ValidationError):
			self.workflow(" B", is_active=0, custom_selection_order=first.custom_selection_order)

	def test_database_rejects_a_duplicate_even_when_application_validation_is_bypassed(self):
		first = self.workflow(" A", is_active=0)
		second = self.workflow(" B", is_active=0)
		frappe.db.savepoint("scenario_order_constraint")
		try:
			with self.assertRaises(Exception) as raised:
				frappe.db.set_value("Workflow", second.name, "custom_selection_order", first.custom_selection_order)
			self.assertTrue(frappe.db.is_unique_key_violation(raised.exception), str(raised.exception))
		finally:
			frappe.db.rollback(save_point="scenario_order_constraint")

	def test_native_save_compiles_condition_without_evaluating_document_values(self):
		workflow = self.workflow(" Valid", is_active=0, custom_activation_condition="doc.not_present_yet == 'x'")
		self.assertEqual(workflow.custom_activation_condition, "doc.not_present_yet == 'x'")
		with self.assertRaises(frappe.ValidationError):
			self.workflow(" Invalid", is_active=0, custom_activation_condition="doc.priority ==")

	def test_new_definition_without_order_gets_next_available_number_on_server(self):
		expected = next_selection_order("Note")
		workflow = frappe.get_doc({
			"doctype": "Workflow", "workflow_name": self.prefix + " Missing Order",
			"document_type": "Note", "workflow_state_field": "content", "is_active": 0,
			"states": [{"state": self.state, "doc_status": "0", "allow_edit": "All"}],
		}).insert(ignore_permissions=True)
		self.assertEqual(workflow.custom_selection_order, expected)
