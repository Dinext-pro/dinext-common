# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Shared Dinext Hub catalog registration for domain apps."""

from __future__ import annotations

from typing import Iterable, Mapping

import frappe


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
