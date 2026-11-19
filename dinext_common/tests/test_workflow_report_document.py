from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from dinext_common.workflow_approval import monitoring


class TestWorkflowReportDocument(TestCase):
	def test_personal_queue_metadata_requires_permission_for_that_report(self):
		report = frappe._dict(
			doctype="Report", name="My Approvals", report_name="My Approvals", is_standard="Yes",
			module="Dinext Common", ref_doctype="Workflow Task", report_type="Script Report",
			query="internal field", has_permission=Mock(return_value=False),
		)
		with (
			patch.object(frappe, "response", frappe._dict(docs=[])),
			patch.object(frappe, "get_doc", return_value=report),
			patch.object(monitoring, "get_report_doc", return_value=report) as authorized,
			patch.object(monitoring, "getdoc") as native,
		):
			monitoring.get_report_document("Report", "My Approvals")
			authorized.assert_called_once_with("My Approvals")
			native.assert_not_called()
			self.assertEqual(frappe.response.docs[0]["name"], "My Approvals")
			self.assertNotIn("query", frappe.response.docs[0])

			authorized.side_effect = frappe.PermissionError
			with self.assertRaises(frappe.PermissionError):
				monitoring.get_report_document("Report", "My Approvals")
			monitoring.get_report_document("Report", "Unrelated Report")
			native.assert_called_once_with("Report", "Unrelated Report")
