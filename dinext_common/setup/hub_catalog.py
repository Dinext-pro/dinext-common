# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Shared Dinext Hub catalog registration for domain apps."""

from __future__ import annotations

import json
from typing import Iterable, Mapping

import frappe
from frappe.utils import cstr

DEFAULT_SECTION_LIST_LIMIT = 5
DEFAULT_SECTION_CARD_COLUMNS = 4
SETTINGS_SECTION_CARD_COLUMNS = 5
SETTINGS_WORKSPACES_SECTION_LIST_LIMIT = 3
SETTINGS_WORKSPACES_SECTION_CARD_COLUMNS = 3
DINEXT_HUB_SETTINGS = "Dinext"
SETTINGS_HUB_SETTINGS = "Settings"
SETTINGS_ROLES = ("System Manager", "Workspace Manager")

# Only new rows use this order. Existing administrator layouts are never sorted.
_DINEXT_ROW_ORDER = {
	"items": (
		("Workspace", "Мои задачи"),
		("Workspace", "Мои проекты"),
		("DocType", "Project Portfolio"),
		("Workspace", "Скоринг проектов"),
		("Report", "Task Epic Burndown"),
		("Workspace", "My Timesheets"),
		("Workspace", "Разработки"),
		("Workspace", "Моя доска"),
		("URL", "https://docs.dinext.ru"),
		("Workspace", "Goals"),
	),
	"sections": (("My Work",), ("Project Management",)),
	"doctype_items": (
		("My Work", "Issue"),
		("My Work", "Task"),
		("Project Management", "Project"),
		("Project Management", "Project Portfolio"),
	),
}
_ROW_KEY_FIELDS = {
	"items": ("element_type", "target"),
	"sections": ("section",),
	"doctype_items": ("section", "document_type"),
}


def _insert_hub_row(settings, table: str, values: Mapping, settings_name: str):
	"""Insert a new default before its next known neighbor, retaining existing order."""
	position = -1
	if settings_name == DINEXT_HUB_SETTINGS:
		fields = _ROW_KEY_FIELDS[table]
		ranks = {key: idx for idx, key in enumerate(_DINEXT_ROW_ORDER[table])}
		rank = ranks.get(tuple(values.get(field) for field in fields))
		if rank is not None:
			for idx, row in enumerate(settings.get(table) or []):
				next_rank = ranks.get(tuple(row.get(field) for field in fields))
				if next_rank is not None and next_rank > rank:
					position = idx
					break
	return settings.append(table, values, position=position)


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

		existing[key] = _insert_hub_row(settings, "items", row_data, settings_name)
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

		existing[section] = _insert_hub_row(settings, "sections", row_data, settings_name)
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
	administrator edits to flags, attention_filter, and a non-empty list_filter.
	Empty ``list_filter`` is backfilled from the payload. ``show_assigned`` and
	``show_quick_create`` are enabled one-way when the payload enables them.
	Unknown keys such as legacy ``show_recently_opened`` / ``recent`` are ignored.
	An optional ``fallback_source_app`` plus ``fallback_defaults`` adopts a matching
	fallback row field-by-field. For these opt-in contributions existing owner rows
	are preserved without legacy backfills, so adopted administrator edits persist.
	"""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings DocType"):
		return

	settings = ensure_workspace_settings(settings_name)
	if settings is None:
		return

	has_list_filter = frappe.get_meta("Dinext Workspace Settings DocType").has_field("list_filter")
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
		row_data = _doctype_values(raw, has_list_filter)
		fallback_app = raw.get("fallback_source_app")
		fallback_defaults = raw.get("fallback_defaults")
		adopts_fallback = bool(fallback_app and isinstance(fallback_defaults, Mapping))
		fallback_key = (section, document_type, fallback_app)
		if adopts_fallback and key not in existing and fallback_key in existing:
			row = existing.pop(fallback_key)
			baseline = _doctype_values(fallback_defaults, has_list_filter)
			for field, value in row_data.items():
				if _same_hub_value(field, row.get(field), baseline.get(field)):
					row.set(field, value)
			row.source_app = app_key
			existing[key] = row
			changed = True
			continue

		if key in existing:
			if adopts_fallback:
				continue
			row = existing[key]
			list_filter = row_data.get("list_filter")
			if has_list_filter and list_filter and not cstr(row.get("list_filter") or "").strip():
				row.list_filter = list_filter
				changed = True
			if row_data["show_assigned"] and not row.get("show_assigned"):
				row.show_assigned = 1
				changed = True
			if row_data["show_quick_create"] and not row.get("show_quick_create"):
				row.show_quick_create = 1
				changed = True
			continue

		if app_key:
			row_data["source_app"] = app_key

		existing[key] = _insert_hub_row(settings, "doctype_items", row_data, settings_name)
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")


def _doctype_values(raw: Mapping, has_list_filter: bool) -> dict:
	values = {
		"section": (raw.get("section") or "").strip(),
		"document_type": raw.get("document_type") or raw.get("doctype"),
		"enabled": 1 if raw.get("enabled", 1) else 0,
		"show_quick_create": 1 if raw.get("show_quick_create") or raw.get("quick_create") else 0,
		"show_assigned": 1 if raw.get("show_assigned") or raw.get("assigned") else 0,
		"show_liked": 1 if raw.get("show_liked") or raw.get("liked") else 0,
		"show_attention": 1 if raw.get("show_attention") or raw.get("attention") else 0,
		"attention_filter": _serialize_hub_filter(raw.get("attention_filter")),
	}
	if has_list_filter:
		values["list_filter"] = _serialize_hub_filter(raw.get("list_filter"))
	return values


def _same_hub_value(field: str, actual, baseline) -> bool:
	if field in ("attention_filter", "list_filter"):
		try:
			return json.loads(actual or "[]") == json.loads(baseline or "[]")
		except (TypeError, ValueError):
			pass
	return actual == baseline


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


def _serialize_hub_filter(raw) -> str:
	if raw in (None, ""):
		return ""
	if isinstance(raw, (list, dict)):
		return frappe.as_json(raw)
	return cstr(raw)


def _parse_card_columns(value) -> int:
	try:
		columns = int(value)
	except (TypeError, ValueError):
		columns = DEFAULT_SECTION_CARD_COLUMNS
	if columns < 1:
		return DEFAULT_SECTION_CARD_COLUMNS
	return columns


