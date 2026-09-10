# Copyright (c) 2026, Dinext and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkflowTask(FrappeTestCase):
	def test_on_doctype_update_adds_approval_query_indexes(self):
		from dinext_common.dinext_common.doctype.workflow_task import workflow_task

		with patch.object(workflow_task.frappe.db, "add_index") as add_index:
			workflow_task.on_doctype_update()

		indexes = [call.args[1] for call in add_index.call_args_list]
		self.assertIn(["reference_doctype", "reference_name", "round_status"], indexes)
		self.assertIn(["approver", "status", "creation"], indexes)
		self.assertIn(["workflow", "round_status"], indexes)
		self.assertIn(
			["transition_uuid", "approver", "status", "completed_at"],
			indexes,
		)
		self.assertIn(["finalization_status", "modified"], indexes)

	def test_task_insert_requires_engine_owned_ignore_permissions(self):
		doc = frappe.new_doc("Workflow Task")
		doc.flags.ignore_permissions = False
		with self.assertRaises(frappe.PermissionError):
			doc.validate()

		doc.flags.ignore_permissions = True
		doc.validate()

	def test_existing_task_cannot_be_saved_directly(self):
		doc = frappe.new_doc("Workflow Task")
		with (
			patch.object(doc, "is_new", return_value=False),
			self.assertRaises(frappe.PermissionError),
		):
			doc.validate()
