import unittest
from unittest.mock import MagicMock, patch


class TestBootWorkspaceSidebarFlag(unittest.TestCase):
	def test_as_bool_defaults_and_truthy(self):
		from dinext_common.boot import as_bool

		self.assertTrue(as_bool(None, default=True))
		self.assertFalse(as_bool(None, default=False))
		self.assertTrue(as_bool(1))
		self.assertFalse(as_bool(0))
		self.assertTrue(as_bool(True))
		self.assertFalse(as_bool(False))
		self.assertTrue(as_bool("1"))
		self.assertTrue(as_bool("true"))
		self.assertFalse(as_bool("0"))
		self.assertFalse(as_bool("false"))
		self.assertFalse(as_bool("no"))
		self.assertFalse(as_bool("off"))
		self.assertFalse(as_bool(""))

	def test_extend_bootinfo_default_enabled(self):
		from dinext_common.boot import extend_bootinfo

		bootinfo = MagicMock()
		with patch("dinext_common.boot.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = 1
			extend_bootinfo(bootinfo)
			mock_frappe.conf.get.assert_called_once_with(
				"dinext_workspace_sidebar_hover_expand", 1
			)
			self.assertTrue(bootinfo.dinext_workspace_sidebar_hover_expand)

	def test_extend_bootinfo_disabled_via_site_config(self):
		from dinext_common.boot import extend_bootinfo

		bootinfo = MagicMock()
		with patch("dinext_common.boot.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = 0
			extend_bootinfo(bootinfo)
			self.assertFalse(bootinfo.dinext_workspace_sidebar_hover_expand)

	def test_extend_bootinfo_preserves_changelog_feed(self):
		from dinext_common.boot import extend_bootinfo

		bootinfo = MagicMock()
		bootinfo.changelog_feed = [
			{
				"title": "A",
				"app_name": "dinext_projects",
				"link": "https://docs.dinext.ru/a",
				"posting_timestamp": "2026-08-01 00:00:00",
			}
		]
		with patch("dinext_common.boot.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = 1
			extend_bootinfo(bootinfo)
			self.assertEqual(len(bootinfo.changelog_feed), 1)
			self.assertEqual(bootinfo.changelog_feed[0]["app_name"], "dinext_projects")

	def test_extend_bootinfo_omits_home_keeps_dinext(self):
		from dinext_common.boot import extend_bootinfo

		bootinfo = MagicMock()
		bootinfo.allowed_workspaces = [
			{"name": "Home", "title": "Home"},
			{"name": "Dinext", "title": "Dinext"},
			{"name": "Settings", "title": "Settings"},
		]
		with patch("dinext_common.boot.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = 1
			extend_bootinfo(bootinfo)

		names = {page["name"] for page in bootinfo.allowed_workspaces}
		self.assertNotIn("Home", names)
		self.assertIn("Dinext", names)
		self.assertIn("Settings", names)

