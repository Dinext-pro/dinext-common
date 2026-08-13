# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Shared Dinext Hub catalog registration for domain apps."""

from __future__ import annotations

from typing import Iterable, Mapping

import frappe

DEFAULT_SECTION_LIST_LIMIT = 5
DEFAULT_SECTION_CARD_COLUMNS = 4
SETTINGS_SECTION_CARD_COLUMNS = 5
DINEXT_HUB_SETTINGS = "Dinext"
SETTINGS_HUB_SETTINGS = "Settings"
SETTINGS_ROLES = ("System Manager", "Workspace Manager")


def ensure_workspace_settings(settings_name: str, *, roles: Iterable[str] | None = None):
	"""Return the named settings document, creating it when the DocType exists."""
	if not settings_name or not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return None
	if frappe.get_meta("Dinext Workspace Settings").issingle:
		return frappe.get_single("Dinext Workspace Settings")

	if frappe.db.exists("Dinext Workspace Settings", settings_name):
		doc = frappe.get_doc("Dinext Workspace Settings", settings_name)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Dinext Workspace Settings",
				"settings_name": settings_name,
			}
		)
		doc.insert(ignore_permissions=True)

	if roles and doc.meta.has_field("roles"):
		current = {row.role for row in doc.get("roles") or []}
		changed = False
		for role in roles:
			if role and role not in current:
				doc.append("roles", {"role": role})
				current.add(role)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
			frappe.clear_cache(doctype="Dinext Workspace Settings")
			doc.reload()

	return doc


def register_hub_items(
	items: Iterable[Mapping],
	*,
	source_app: str | None = None,
	settings_name: str = DINEXT_HUB_SETTINGS,
) -> None:
	"""Append missing hub cards into a named Dinext Workspace Settings record.

	Match key is ``(element_type, target)`` within that record. Existing rows keep
	admin edits (label, description, icon, section, enabled, required_role). Empty
	icons on existing rows are backfilled from the registration payload when provided.
	"""
	settings = ensure_workspace_settings(settings_name)
	if settings is None:
		return

	existing = {(row.element_type, row.target): row for row in settings.items}
	changed = False

	for raw in items:
		element_type = raw.get("element_type")
		target = raw.get("target")
		if not element_type or not target:
			continue

		key = (element_type, target)
		if key in existing:
			row = existing[key]
			if not row.icon and raw.get("icon"):
				row.icon = raw["icon"]
				changed = True
			if source_app and not getattr(row, "source_app", None):
				row.source_app = source_app
				changed = True
			continue

		row_data = {
			"section": raw.get("section") or "",
			"element_type": element_type,
			"target": target,
			"label": raw.get("label") or target,
			"description": raw.get("description") or "",
			"icon": raw.get("icon") or "",
			"enabled": 1 if raw.get("enabled", 1) else 0,
		}
		if source_app:
			row_data["source_app"] = source_app
		if raw.get("required_role"):
			row_data["required_role"] = raw["required_role"]

		settings.append("items", row_data)
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")


def register_hub_sections(
	sections: Iterable[Mapping],
	*,
	source_app: str | None = None,
	settings_name: str = DINEXT_HUB_SETTINGS,
) -> None:
	"""Append missing section limit rows. Key is section name; admin limits are preserved."""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings Section"):
		return

	settings = ensure_workspace_settings(settings_name)
	if settings is None:
		return

	existing = {row.section: row for row in settings.get("sections") or []}
	changed = False

	for raw in sections:
		section = (raw.get("section") or "").strip()
		if not section:
			continue

		if section in existing:
			row = existing[section]
			if source_app and not getattr(row, "source_app", None):
				row.source_app = source_app
				changed = True
			continue

		list_limit = raw.get("list_limit", DEFAULT_SECTION_LIST_LIMIT)
		try:
			list_limit = int(list_limit)
		except (TypeError, ValueError):
			list_limit = DEFAULT_SECTION_LIST_LIMIT
		if list_limit < 1:
			list_limit = DEFAULT_SECTION_LIST_LIMIT

		row_data = {
			"section": section,
			"list_limit": list_limit,
		}
		if frappe.get_meta("Dinext Workspace Settings Section").has_field("card_columns"):
			row_data["card_columns"] = _parse_card_columns(raw.get("card_columns"))
		if source_app:
			row_data["source_app"] = source_app

		settings.append("sections", row_data)
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")


def register_hub_doctype_items(
	items: Iterable[Mapping],
	*,
	source_app: str | None = None,
	settings_name: str = DINEXT_HUB_SETTINGS,
) -> None:
	"""Append missing DocType list contributions.

	Match key is ``(section, document_type, source_app)``. Existing rows keep
	administrator edits to flags and attention_filter. Unknown keys such as
	legacy ``show_recently_opened`` / ``recent`` are ignored.
	"""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings DocType"):
		return

	settings = ensure_workspace_settings(settings_name)
	if settings is None:
		return

	existing = {
		(row.section, row.document_type, getattr(row, "source_app", None) or ""): row
		for row in settings.get("doctype_items") or []
	}
	changed = False

	for raw in items:
		section = (raw.get("section") or "").strip()
		document_type = raw.get("document_type") or raw.get("doctype")
		if not section or not document_type:
			continue

		app_key = source_app or raw.get("source_app") or ""
		key = (section, document_type, app_key)
		if key in existing:
			continue

		attention_filter = raw.get("attention_filter") or ""
		if isinstance(attention_filter, (list, dict)):
			attention_filter = frappe.as_json(attention_filter)

		row_data = {
			"section": section,
			"document_type": document_type,
			"enabled": 1 if raw.get("enabled", 1) else 0,
			"show_quick_create": 1 if raw.get("show_quick_create") or raw.get("quick_create") else 0,
			"show_assigned": 1 if raw.get("show_assigned") or raw.get("assigned") else 0,
			"show_liked": 1 if raw.get("show_liked") or raw.get("liked") else 0,
			"show_attention": 1 if raw.get("show_attention") or raw.get("attention") else 0,
			"attention_filter": attention_filter,
		}
		if app_key:
			row_data["source_app"] = app_key

		settings.append("doctype_items", row_data)
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")


def relocate_hub_item_section(
	*,
	element_type: str,
	target: str,
	section: str,
	settings_name: str = DINEXT_HUB_SETTINGS,
) -> None:
	"""Set section for an existing hub item without changing other fields."""
	settings = ensure_workspace_settings(settings_name)
	if settings is None:
		return

	changed = False
	for row in settings.items:
		if row.element_type == element_type and row.target == target and row.section != section:
			row.section = section
			changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")


def _parse_card_columns(value) -> int:
	try:
		columns = int(value)
	except (TypeError, ValueError):
		columns = DEFAULT_SECTION_CARD_COLUMNS
	if columns < 1:
		return DEFAULT_SECTION_CARD_COLUMNS
	return columns


