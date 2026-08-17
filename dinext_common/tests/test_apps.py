import unittest
from unittest.mock import MagicMock, patch

from dinext_common.apps import (
	DINEXT_DEFAULT_APP,
	DEFAULT_HIDDEN_APPS,
	ensure_default_apps,
	filter_hidden_apps,
	get_hidden_app_names,
	needs_dinext_default_app,
	set_default_app_for_new_user,
	update_website_context,
)


class TestDinextApps(unittest.TestCase):
	def test_missing_site_config_uses_platform_defaults(self):
		with patch("dinext_common.apps.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = None
			self.assertEqual(get_hidden_app_names(), set(DEFAULT_HIDDEN_APPS))

	def test_empty_site_config_does_not_hide_apps(self):
		with patch("dinext_common.apps.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = []
			self.assertEqual(get_hidden_app_names(), set())

	def test_comma_separated_site_config_hides_named_apps(self):
		with patch("dinext_common.apps.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = "erpnext, hrms, crm"
			self.assertEqual(get_hidden_app_names(), {"erpnext", "hrms", "crm"})

	def test_filter_hidden_apps_uses_app_name(self):
		apps = [
			{"name": "dinext_common", "title": "Dinext"},
			{"name": "erpnext", "title": "ERPNext"},
			{"name": "hrms", "title": "Frappe HR"},
			{"name": "crm", "title": "CRM"},
		]
		with patch("dinext_common.apps.get_hidden_app_names", return_value={"erpnext", "hrms"}):
			self.assertEqual(
				[app["name"] for app in filter_hidden_apps(apps)],
				["dinext_common", "crm"],
			)

	def test_website_context_excludes_hidden_launchers(self):
		context = {
			"apps": [
				{"name": "dinext_common"},
				{"name": "erpnext"},
			]
		}
		with patch("dinext_common.apps.get_hidden_app_names", return_value={"erpnext"}):
			update_website_context(context)
		self.assertEqual(context["apps"], [{"name": "dinext_common"}])

	def test_new_user_with_no_preference_defaults_to_dinext(self):
		user = MagicMock(default_app="")
		set_default_app_for_new_user(user)
		user.db_set.assert_called_once_with(
			"default_app",
			DINEXT_DEFAULT_APP,
			update_modified=False,
		)

	def test_new_user_preference_is_preserved(self):
		user = MagicMock(default_app="crm")
		set_default_app_for_new_user(user)
		user.db_set.assert_not_called()

	def test_empty_and_hidden_defaults_need_repair(self):
		with patch("dinext_common.apps.get_hidden_app_names", return_value={"erpnext", "hrms"}):
			self.assertTrue(needs_dinext_default_app(""))
			self.assertTrue(needs_dinext_default_app("erpnext"))
			self.assertFalse(needs_dinext_default_app("crm"))

	def test_migration_repairs_system_and_user_defaults(self):
		with patch("dinext_common.apps.frappe") as mock_frappe:
			mock_frappe.db.get_single_value.return_value = "erpnext"
			mock_frappe.db.get_all.return_value = [
				{"name": "hidden@example.test", "default_app": "hrms"},
				{"name": "visible@example.test", "default_app": "crm"},
			]
			with patch("dinext_common.apps.get_hidden_app_names", return_value={"erpnext", "hrms"}):
				ensure_default_apps()

		mock_frappe.db.set_single_value.assert_called_once_with(
			"System Settings",
			"default_app",
			DINEXT_DEFAULT_APP,
			update_modified=False,
		)
		mock_frappe.db.set_value.assert_called_once_with(
			"User",
			"hidden@example.test",
			"default_app",
			DINEXT_DEFAULT_APP,
			update_modified=False,
		)
		mock_frappe.clear_cache.assert_called_once()

	def test_apps_screen_hook_registers_dinext(self):
		import frappe

		launchers = frappe.get_hooks("add_to_apps_screen", app_name="dinext_common")
		self.assertEqual(
			launchers,
			[
				{
					"name": DINEXT_DEFAULT_APP,
					"logo": "/assets/dinext_common/images/DI_SQ_NBG.png",
					"title": "Dinext",
					"route": "/app/dinext",
				}
			],
		)

	def test_boot_session_hook_filters_apps_data_before_sessions_builds_it(self):
		import frappe

		self.assertIn("dinext_common.apps.configure_boot_app_filter", frappe.get_hooks("boot_session"))
