# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path

import frappe

DUMP_FILENAME = "dinext_workspace_settings_single.json"
LEGACY_PARENT = "Dinext Workspace Settings"
CHILD_TABLES = (
	("Dinext Workspace Settings Item", "items"),
	("Dinext Workspace Settings Section", "sections"),
	("Dinext Workspace Settings DocType", "doctype_items"),
)
_SKIP = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"parent",
	"parentfield",
	"parenttype",
	"docstatus",
	"doctype",
}


def dump_path() -> Path:
	return Path(frappe.get_site_path("private", DUMP_FILENAME))


def is_single_settings() -> bool:
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return False
	return bool(frappe.get_meta("Dinext Workspace Settings").issingle)


def dump_legacy_children() -> dict:
	payload = {"items": [], "sections": [], "doctype_items": []}
	for doctype, fieldname in CHILD_TABLES:
		if not frappe.db.exists("DocType", doctype):
			continue
		rows = frappe.get_all(
			doctype,
			filters={"parent": LEGACY_PARENT},
			fields=_child_fields(doctype),
			order_by="idx",
		)
		payload[fieldname] = [_clean_row(row) for row in rows]
	return payload


def _child_fields(doctype: str) -> list[str]:
	meta = frappe.get_meta(doctype)
	names = ["idx"]
	for df in meta.fields:
		if df.fieldtype in {"Section Break", "Column Break", "Tab Break", "HTML"}:
			continue
		if df.fieldname and df.fieldname not in names:
			names.append(df.fieldname)
	return names


def _clean_row(row: dict) -> dict:
	return {key: value for key, value in row.items() if key not in _SKIP}
