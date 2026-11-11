from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.workspace_hub import _get_route


class TestTimesheetWorkspaceCompatibility(FrappeTestCase):
	def workspace(self, name):
		if frappe.db.exists("Workspace", name):
			return frappe.get_doc("Workspace", name)
		doc = frappe.get_doc({
			"doctype": "Workspace", "label": name, "title": name,
			"module": "Core", "public": 1, "is_hidden": 0, "content": "[]",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Workspace", doc.name, force=True, ignore_permissions=True)
		return doc

	def test_canonical_timesheet_target_resolves_legacy_workspace_with_permissions(self):
		self.assertFalse(frappe.db.exists("Workspace", "My Timesheets"))
		self.workspace("Мои Таймшиты")
		self.assertEqual(_get_route("Workspace", "My Timesheets"), "/app/мои-таймшиты")
		with patch("frappe.has_permission", return_value=False):
			self.assertIsNone(_get_route("Workspace", "My Timesheets"))

	def test_existing_canonical_workspace_has_priority(self):
		self.workspace("Мои Таймшиты")
		self.workspace("My Timesheets")
		self.assertEqual(_get_route("Workspace", "My Timesheets"), "/app/my-timesheets")
