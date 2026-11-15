"""Real settings documents isolated from the site's configured Hub."""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from dinext_common.setup.hub_catalog import ensure_workspace_settings


class HubRegistrationTestCase(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.settings = ensure_workspace_settings(f"Test owner defaults {random_string(8)}")
		self.addCleanup(
			frappe.delete_doc, "Dinext Workspace Settings", self.settings.name,
			force=True, ignore_permissions=True,
		)
		selector = patch("dinext_common.setup.hub_catalog.ensure_workspace_settings", return_value=self.settings)
		selector.start()
		self.addCleanup(selector.stop)
