# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe

DINEXT_WORKSPACE = "Dinext"
SETTINGS_WORKSPACE = "Настройки"
SETTINGS_CHILDREN = ("Integrations", "Tools", "Users", "Build")
DINEXT_APP_PREFIX = "dinext_"
DINEXT_MODULE = "Dinext Common"


def configure_workspace_menu() -> None:
	"""Hide public non-Dinext workspaces and build the Dinext menu."""
	ensure_dinext_roots()
	hide_non_dinext_workspaces()
	nest_settings_children()
	frappe.clear_cache()


def ensure_dinext_roots() -> None:
	for title, icon, sequence_id in (
		(DINEXT_WORKSPACE, "organization", 1.0),
		(SETTINGS_WORKSPACE, "setting", 2.0),
	):
		_ensure_public_workspace(title=title, icon=icon, sequence_id=sequence_id)


def hide_non_dinext_workspaces() -> None:
	dinext_modules = set(
		frappe.get_all(
			"Module Def",
			filters={"app_name": ["like", f"{DINEXT_APP_PREFIX}%"]},
			pluck="name",
		)
	)

	workspaces = frappe.get_all(
		"Workspace",
		filters={"public": 1},
		fields=["name", "is_hidden", "for_user", "module"],
	)

	keep_visible = set(SETTINGS_CHILDREN)
	for workspace in workspaces:
		if workspace.for_user:
			continue

		if workspace.name in keep_visible:
			if workspace.is_hidden:
				frappe.db.set_value(
					"Workspace",
					workspace.name,
					"is_hidden",
					0,
					update_modified=False,
				)
			continue

		if workspace.module not in dinext_modules and not workspace.is_hidden:
			frappe.db.set_value(
				"Workspace",
				workspace.name,
				"is_hidden",
				1,
				update_modified=False,
			)


def nest_settings_children() -> None:
	for name in SETTINGS_CHILDREN:
		if not frappe.db.exists("Workspace", name):
			continue

		values = frappe.db.get_value(
			"Workspace",
			name,
			["parent_page", "is_hidden", "public"],
			as_dict=True,
		)
		updates = {}
		if values.parent_page != SETTINGS_WORKSPACE:
			updates["parent_page"] = SETTINGS_WORKSPACE
		if values.is_hidden:
			updates["is_hidden"] = 0
		if not values.public:
			updates["public"] = 1

		if updates:
			frappe.db.set_value("Workspace", name, updates, update_modified=False)


def set_default_workspace_for_new_user(doc, method=None) -> None:
	"""Assign Dinext as default workspace for newly created users."""
	if doc.name in ("Administrator", "Guest"):
		return

	if doc.default_workspace:
		return

	if not frappe.db.exists("Workspace", DINEXT_WORKSPACE):
		return

	doc.db_set("default_workspace", DINEXT_WORKSPACE, update_modified=False)


def _ensure_public_workspace(*, title: str, icon: str, sequence_id: float) -> None:
	if frappe.db.exists("Workspace", title):
		current = frappe.db.get_value(
			"Workspace",
			title,
			["public", "is_hidden", "parent_page", "module", "for_user"],
			as_dict=True,
		)
		updates = {}
		if not current.public:
			updates["public"] = 1
		if current.is_hidden:
			updates["is_hidden"] = 0
		if current.parent_page:
			updates["parent_page"] = ""
		if current.module != DINEXT_MODULE:
			updates["module"] = DINEXT_MODULE
		if current.for_user:
			updates["for_user"] = ""
		if updates:
			frappe.db.set_value("Workspace", title, updates, update_modified=False)
		return

	doc = frappe.get_doc(
		{
			"doctype": "Workspace",
			"label": title,
			"title": title,
			"module": DINEXT_MODULE,
			"icon": icon,
			"content": "[]",
			"public": 1,
			"for_user": "",
			"parent_page": "",
			"is_hidden": 0,
			"sequence_id": sequence_id,
		}
	)
	doc.insert(ignore_permissions=True)
