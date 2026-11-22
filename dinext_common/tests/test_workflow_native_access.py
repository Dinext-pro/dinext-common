"""Ensure that Workflow registers its read rules on the standard Frappe hooks."""
from unittest import TestCase
from unittest.mock import patch

import frappe

from dinext_common import hooks
from dinext_common.workflow_approval import permissions


class TestWorkflowNativeAccess(TestCase):
	def test_all_protected_reads_use_standard_query_hooks(self):
		protected = {"Workflow Task", "Workflow Process", "Workflow Document Context", "Number Card"}
		self.assertTrue(protected <= hooks.permission_query_conditions.keys())
		self.assertFalse(protected & getattr(hooks, "final_permission_query_conditions", {}).keys())
		self.assertIn("DocShare", hooks.doc_events)

	def test_protected_share_grants_are_refused_and_revocation_is_allowed(self):
		for doctype, name in (
			("Workflow Task", "example"), ("Workflow Process", "example"),
			("Workflow Document Context", "example"), ("Number Card", "Открытые раунды"),
		):
			doc = frappe._dict(share_doctype=doctype, share_name=name, everyone=1, read=1)
			with self.subTest(doctype=doctype), self.assertRaises(frappe.PermissionError):
				permissions.validate_workflow_docshare(doc)
			doc.read = 0
			permissions.validate_workflow_docshare(doc)
		for doctype, name in (("Note", "example"), ("Number Card", "Unrelated Widget")):
			permissions.validate_workflow_docshare(
				frappe._dict(share_doctype=doctype, share_name=name, everyone=1, read=1)
			)

	def test_monitoring_card_permission_uses_role_even_for_private_definitions(self):
		doc = frappe._dict(name="Открытые раунды", is_public=0)
		with (
			patch.object(permissions, "require_no_workflow_shares"),
			patch.object(permissions, "_is_system_manager", return_value=False),
			patch.object(permissions, "get_monitorable_workflows", side_effect=[["Test"], []]),
		):
			self.assertTrue(permissions.has_public_number_card_permission(doc, user="monitor@example.invalid"))
			self.assertFalse(permissions.has_public_number_card_permission(doc, user="other@example.invalid"))

	def test_workflow_report_snapshots_are_never_served(self):
		from dinext_common.workflow_approval import report_access

		protected = frappe._dict(ref_doctype="Workflow Task", reference_report=None, prepared_report=1)
		other = frappe._dict(ref_doctype="Note", reference_report=None, prepared_report=1)
		report_access.require_live_workflow_report(protected)
		report_access.require_live_workflow_report(other)
		self.assertEqual((protected.prepared_report, other.prepared_report), (0, 1))
		self.assertEqual(protected.disable_prepared_report_automation, 1)
		self.assertIsNone(other.disable_prepared_report_automation)
		with patch.object(report_access, "_is_workflow_report", side_effect=lambda name: name == "Approval Load"):
			with self.assertRaises(permissions.WorkflowReadBlocked):
				report_access.has_prepared_report_permission(frappe._dict(report_name="Approval Load"))
			self.assertIsNone(report_access.has_prepared_report_permission(frappe._dict(report_name="Unrelated")))

	def test_public_search_keeps_workflow_policies_enabled(self):
		from dinext_common.workflow_approval import desk_access

		with patch.object(desk_access.search, "search_widget", return_value=[]) as search:
			desk_access.search_widget("Workflow Task", "task", query="another.method", ignore_user_permissions=True)
			self.assertIsNone(search.call_args.kwargs["query"])
			self.assertFalse(search.call_args.kwargs["ignore_user_permissions"])
			desk_access.search_widget("Project", "project", query="another.method", ignore_user_permissions=True)
			self.assertEqual(search.call_args.kwargs["query"], "another.method")
			self.assertTrue(search.call_args.kwargs["ignore_user_permissions"])



	def test_private_result_file_uses_download_gate_before_native_grants(self):
		from dinext_common.workflow_approval import report_access

		file = report_access.WorkflowReportAttachment({
			"doctype": "File", "owner": frappe.session.user, "name": "workflow-test",
			"attached_to_doctype": "Prepared Report", "attached_to_name": "workflow-result",
		})
		with (
			patch.object(report_access, "_is_workflow_report_attachment", return_value=True),
			patch.object(report_access.File, "is_downloadable", return_value=True) as native,
		):
			self.assertFalse(file.is_downloadable())
			native.assert_not_called()
