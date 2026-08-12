# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Shared Dinext Hub catalog registration for domain apps."""

from __future__ import annotations

from typing import Iterable, Mapping

import frappe

DEFAULT_SECTION_LIST_LIMIT = 5


def register_hub_items(items: Iterable[Mapping], *, source_app: str | None = None) -> None:
	"""Append missing hub cards into Dinext Workspace Settings.

	Match key is ``(element_type, target)``. Existing rows keep admin edits
	(label, description, icon, section, enabled, required_role). Empty icons on
	existing rows are backfilled from the registration payload when provided.
	"""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return

	settings = frappe.get_single("Dinext Workspace Settings")
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


def register_hub_sections(sections: Iterable[Mapping], *, source_app: str | None = None) -> None:
	"""Append missing section limit rows. Key is section name; admin limits are preserved."""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return
	if not frappe.db.exists("DocType", "Dinext Workspace Settings Section"):
		return

	settings = frappe.get_single("Dinext Workspace Settings")
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
		if source_app:
			row_data["source_app"] = source_app

		settings.append("sections", row_data)
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")


def register_hub_doctype_items(items: Iterable[Mapping], *, source_app: str | None = None) -> None:
	"""Append missing DocType list contributions.

	Match key is ``(section, document_type, source_app)``. Existing rows keep
	administrator edits to flags and attention_filter.
	"""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return
	if not frappe.db.exists("DocType", "Dinext Workspace Settings DocType"):
		return

	settings = frappe.get_single("Dinext Workspace Settings")
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
			"show_recently_opened": 1 if raw.get("show_recently_opened") or raw.get("recent") else 0,
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
) -> None:
	"""Set section for an existing hub item without changing other fields."""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return

	settings = frappe.get_single("Dinext Workspace Settings")
	changed = False
	for row in settings.items:
		if row.element_type == element_type and row.target == target and row.section != section:
			row.section = section
			changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")
