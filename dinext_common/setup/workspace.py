# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import json
from pathlib import Path

import frappe

from dinext_common.setup.hub_catalog import (
	DINEXT_HUB_SETTINGS,
	SETTINGS_HUB_SETTINGS,
	SETTINGS_SECTION_CARD_COLUMNS,
	ensure_workspace_settings,
	register_hub_items,
	register_hub_sections,
)

DINEXT_WORKSPACE = "Dinext"
SETTINGS_WORKSPACE = "Settings"
LEGACY_SETTINGS_WORKSPACE = "Настройки"
SETTINGS_CHILDREN = ("Integrations", "Tools", "Users", "Build", "Website")
DINEXT_APP_PREFIX = "dinext_"
DINEXT_MODULE = "Dinext Common"
SETTINGS_ROLES = ("System Manager", "Workspace Manager")
DINEXT_HUB_BLOCK = "Dinext Hub"
SETTINGS_HUB_BLOCK = "Dinext Settings Hub"
REPLACED_WORKSPACES = ("Home",)
WORKSPACE_HUB_BLOCKS = {
	DINEXT_WORKSPACE: (DINEXT_HUB_BLOCK, "dinext-hub"),
	SETTINGS_WORKSPACE: (SETTINGS_HUB_BLOCK, "dinext-settings-hub"),
}


def omit_replaced_workspaces(pages):
	"""Drop ERPNext Home (and later replacements) from Desk sidebar payloads."""
	if not isinstance(pages, (list, tuple)):
		return pages

	omitted = set(REPLACED_WORKSPACES)
	kept = []
	for page in pages:
		name = _workspace_page_field(page, "name")
		title = _workspace_page_field(page, "title")
		if name in omitted or title in omitted:
			continue
		kept.append(page)
	return kept


def _workspace_page_field(page, key: str) -> str:
	if isinstance(page, dict):
		return page.get(key) or ""
	return getattr(page, key, None) or ""


@frappe.whitelist()
def get_workspace_sidebar_items():
	"""Return sidebar pages without replaced workspaces such as Home."""
	from frappe.desk.desktop import get_workspace_sidebar_items as original

	payload = original() or {}
	payload["pages"] = omit_replaced_workspaces(payload.get("pages") or [])
	return payload


def configure_workspace_menu() -> None:
	"""Hide public non-Dinext workspaces and build the Dinext menu."""
	migrate_legacy_settings_workspace()
	ensure_dinext_roots()
	hide_non_dinext_workspaces()
	nest_settings_children()
	ensure_default_dinext_hub_settings()
	ensure_workspace_hub_blocks()
	frappe.clear_cache()


def ensure_dinext_roots() -> None:
	for title, icon, sequence_id in (
		(DINEXT_WORKSPACE, "organization", 1.0),
		(SETTINGS_WORKSPACE, "setting", 2.0),
	):
		_ensure_public_workspace(title=title, icon=icon, sequence_id=sequence_id)
	ensure_settings_workspace_roles()


def sync_workspace_hub_block_fixtures() -> None:
	"""Force-refresh hub Custom HTML Blocks from app fixtures (script/style/html)."""
	path = Path(frappe.get_app_path("dinext_common")) / "fixtures" / "custom_html_block.json"
	if not path.exists():
		return

	for row in json.loads(path.read_text()):
		name = row.get("name")
		if not name:
			continue
		if frappe.db.exists("Custom HTML Block", name):
			doc = frappe.get_doc("Custom HTML Block", name)
		else:
			doc = frappe.new_doc("Custom HTML Block")
			doc.name = name

		changed = False
		for fieldname in ("html", "script", "style"):
			value = row.get(fieldname) or ""
			if doc.get(fieldname) != value:
				doc.set(fieldname, value)
				changed = True

		wanted_roles = [role_row["role"] for role_row in row.get("roles") or []]
		current_roles = [role_row.role for role_row in doc.roles]
		if current_roles != wanted_roles:
			doc.roles = []
			for role in wanted_roles:
				doc.append("roles", {"role": role})
			changed = True

		if changed or doc.is_new():
			doc.save(ignore_permissions=True)


def ensure_workspace_hub_blocks() -> None:
	"""Keep Custom HTML Block attachments on root Workspaces after migrate/rename."""
	sync_workspace_hub_block_fixtures()

	for workspace_name, (block_name, content_id) in WORKSPACE_HUB_BLOCKS.items():
		if not frappe.db.exists("Workspace", workspace_name):
			continue
		if not frappe.db.exists("Custom HTML Block", block_name):
			continue

		workspace = frappe.get_doc("Workspace", workspace_name)
		changed = False

		if workspace_name == SETTINGS_WORKSPACE:
			if workspace.title != SETTINGS_WORKSPACE:
				workspace.title = SETTINGS_WORKSPACE
				changed = True
			if workspace.label != SETTINGS_WORKSPACE:
				workspace.label = SETTINGS_WORKSPACE
				changed = True

		if _ensure_hub_content_widget(workspace, block_name=block_name, content_id=content_id):
			changed = True

		current_blocks = {row.custom_block_name for row in workspace.custom_blocks}
		if block_name not in current_blocks:
			workspace.append(
				"custom_blocks",
				{"custom_block_name": block_name, "label": block_name},
			)
			changed = True

		if changed:
			workspace.save(ignore_permissions=True)


def _ensure_hub_content_widget(workspace, *, block_name: str, content_id: str) -> bool:
	"""Add the hub custom block widget without replacing existing Workspace content."""
	hub_widget = {
		"id": content_id,
		"type": "custom_block",
		"data": {"custom_block_name": block_name, "col": 12},
	}

	raw = (workspace.content or "").strip()
	if not raw or raw == "[]":
		workspace.content = json.dumps([hub_widget], separators=(",", ":"))
		return True

	try:
		widgets = json.loads(raw)
	except (TypeError, ValueError):
		workspace.content = json.dumps([hub_widget], separators=(",", ":"))
		return True

	if not isinstance(widgets, list):
		workspace.content = json.dumps([hub_widget], separators=(",", ":"))
		return True

	for widget in widgets:
		if not isinstance(widget, dict):
			continue
		data = widget.get("data") or {}
		if widget.get("type") == "custom_block" and data.get("custom_block_name") == block_name:
			return False
		if widget.get("id") == content_id:
			return False

	widgets.append(hub_widget)
	workspace.content = json.dumps(widgets, separators=(",", ":"))
	return True


def migrate_legacy_settings_workspace() -> None:
	"""Rename the former Russian root before ensuring the English replacement."""
	if not frappe.db.exists("Workspace", LEGACY_SETTINGS_WORKSPACE):
		return

	if frappe.db.exists("Workspace", SETTINGS_WORKSPACE):
		frappe.delete_doc("Workspace", LEGACY_SETTINGS_WORKSPACE, force=True, ignore_permissions=True)
		return

	frappe.rename_doc("Workspace", LEGACY_SETTINGS_WORKSPACE, SETTINGS_WORKSPACE, force=True)


def ensure_settings_workspace_roles() -> None:
	if not frappe.db.exists("Workspace", SETTINGS_WORKSPACE):
		return

	workspace = frappe.get_doc("Workspace", SETTINGS_WORKSPACE)
	current_roles = {row.role for row in workspace.roles}
	roles_changed = False
	for role in SETTINGS_ROLES:
		if role not in current_roles:
			workspace.append("roles", {"role": role})
			current_roles.add(role)
			roles_changed = True

	if current_roles != set(SETTINGS_ROLES):
		workspace.roles = [row for row in workspace.roles if row.role in SETTINGS_ROLES]
		roles_changed = True

	if roles_changed:
		workspace.save(ignore_permissions=True)


def ensure_default_dinext_hub_settings() -> None:
	"""Ensure standard named records exist; domain cards are registered by owning apps."""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return

	ensure_workspace_settings(DINEXT_HUB_SETTINGS)
	ensure_workspace_settings(SETTINGS_HUB_SETTINGS, roles=SETTINGS_ROLES)

	from dinext_common.workspace_hub import default_settings_hub_items

	register_hub_items(
		default_settings_hub_items(),
		source_app="dinext_common",
		settings_name=SETTINGS_HUB_SETTINGS,
	)
	register_hub_sections(
		[
			{"section": "Workspaces", "card_columns": SETTINGS_SECTION_CARD_COLUMNS},
			{"section": "Configuration", "card_columns": SETTINGS_SECTION_CARD_COLUMNS},
		],
		source_app="dinext_common",
		settings_name=SETTINGS_HUB_SETTINGS,
	)
	_disable_settings_hub_page_lists()


def _disable_settings_hub_page_lists() -> None:
	"""Keep Frequent/Recent Pages off on the product-owned Settings record."""
	if not frappe.db.exists("Dinext Workspace Settings", SETTINGS_HUB_SETTINGS):
		return

	settings = frappe.get_doc("Dinext Workspace Settings", SETTINGS_HUB_SETTINGS)
	if not settings.meta.has_field("show_frequent_pages") or not settings.meta.has_field(
		"show_recent_pages"
	):
		return
	if not settings.show_frequent_pages and not settings.show_recent_pages:
		return

	settings.show_frequent_pages = 0
	settings.show_recent_pages = 0
	settings.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Dinext Workspace Settings")


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
