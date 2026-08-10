# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from dinext_common.setup.workspace import (
	DINEXT_WORKSPACE,
	SETTINGS_CHILDREN,
	SETTINGS_WORKSPACE,
	configure_workspace_menu,
	set_default_workspace_for_new_user,
)


class TestDinextWorkspaceMenu(FrappeTestCase):
	def test_configure_ensures_roots_hides_standard_and_nests_children(self):
		configure_workspace_menu()

		for name in (DINEXT_WORKSPACE, SETTINGS_WORKSPACE):
			self.assertTrue(frappe.db.exists("Workspace", name))
			ws = frappe.db.get_value(
				"Workspace",
				name,
				["public", "is_hidden", "parent_page", "module", "for_user"],
				as_dict=True,
			)
			self.assertEqual(ws.public, 1)
			self.assertEqual(ws.is_hidden, 0)
			self.assertEqual(ws.parent_page or "", "")
			self.assertEqual(ws.module, "Dinext Common")
			self.assertEqual(ws.for_user or "", "")

		for name in SETTINGS_CHILDREN:
			if not frappe.db.exists("Workspace", name):
				continue
			ws = frappe.db.get_value(
				"Workspace",
				name,
				["parent_page", "is_hidden", "public"],
				as_dict=True,
			)
			self.assertEqual(ws.parent_page, SETTINGS_WORKSPACE)
			self.assertEqual(ws.is_hidden, 0)
			self.assertEqual(ws.public, 1)

		dinext_modules = set(
			frappe.get_all(
				"Module Def",
				filters={"app_name": ["like", "dinext_%"]},
				pluck="name",
			)
		)
		workspaces = frappe.get_all(
			"Workspace",
			filters={"public": 1},
			fields=["name", "module", "is_hidden", "for_user"],
		)
		for ws in workspaces:
			if ws.for_user or ws.name in (
				DINEXT_WORKSPACE,
				SETTINGS_WORKSPACE,
				*SETTINGS_CHILDREN,
			):
				continue

			if ws.module in dinext_modules:
				continue

			self.assertEqual(
				ws.is_hidden,
				1,
				msg=f"public non-Dinext workspace {ws.name!r} must be hidden",
			)

	def test_configure_is_idempotent(self):
		configure_workspace_menu()
		configure_workspace_menu()

		self.assertEqual(
			frappe.db.get_value("Workspace", SETTINGS_WORKSPACE, "parent_page") or "",
			"",
		)
		if frappe.db.exists("Workspace", "Tools"):
			self.assertEqual(
				frappe.db.get_value("Workspace", "Tools", "parent_page"),
				SETTINGS_WORKSPACE,
			)

	def test_new_user_gets_default_workspace(self):
		configure_workspace_menu()
		email = f"ws-menu-{random_string(8).lower()}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Administrator",
				"last_name": "",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", user.name, force=True, ignore_permissions=True))

		self.assertEqual(
			frappe.db.get_value("User", user.name, "default_workspace"),
			DINEXT_WORKSPACE,
		)

	def test_existing_user_default_workspace_untouched_by_configure(self):
		email = f"ws-keep-{random_string(8).lower()}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Administrator",
				"last_name": "",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		# Bypass after_insert side effects for this fixture by setting after insert via db
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", user.name, force=True, ignore_permissions=True))

		# Simulate a pre-existing preference that configure must not touch
		frappe.db.set_value("User", user.name, "default_workspace", "", update_modified=False)
		configure_workspace_menu()
		self.assertFalse(frappe.db.get_value("User", user.name, "default_workspace"))

	def test_handler_skips_when_default_already_set(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"ws-preset-{random_string(8).lower()}@example.com",
				"first_name": "Administrator",
				"default_workspace": "Build" if frappe.db.exists("Workspace", "Build") else DINEXT_WORKSPACE,
				"send_welcome_email": 0,
			}
		)
		# Call handler directly with a doc that already has default_workspace
		before = user.default_workspace
		set_default_workspace_for_new_user(user)
		self.assertEqual(user.default_workspace, before)
