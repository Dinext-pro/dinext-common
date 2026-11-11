import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.tests.workspace_defaults_ui import cleanup, seed


class TestWorkspaceDefaultsUIAccess(FrappeTestCase):
	def test_fixture_actions_cannot_be_called_through_http(self):
		for action in (seed, cleanup):
			with self.subTest(action=action.__name__):
				with self.assertRaises(frappe.PermissionError):
					frappe.is_whitelisted(action)
