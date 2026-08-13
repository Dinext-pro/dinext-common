# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe

from dinext_common.patches.v1_0.workspace_settings_migrate import (
	CHILD_TABLES,
	LEGACY_PARENT,
	dump_path,
)
from dinext_common.setup.hub_catalog import (
	DINEXT_HUB_SETTINGS,
	SETTINGS_HUB_SETTINGS,
	ensure_workspace_settings,
)
from dinext_common.setup.workspace import SETTINGS_ROLES, ensure_default_dinext_hub_settings


def execute() -> None:
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return
	if frappe.get_meta("Dinext Workspace Settings").issingle:
		return

	dinext = ensure_workspace_settings(DINEXT_HUB_SETTINGS)
	if dinext is None:
		return
	_reparent_legacy_children(dinext)
	_restore_dump_if_empty(dinext)
	ensure_workspace_settings(SETTINGS_HUB_SETTINGS, roles=SETTINGS_ROLES)
	ensure_default_dinext_hub_settings()
	_delete_dump()


def _reparent_legacy_children(dinext) -> None:
	changed = False
	for doctype, fieldname in CHILD_TABLES:
		if not frappe.db.exists("DocType", doctype):
			continue
		names = frappe.get_all(doctype, filters={"parent": LEGACY_PARENT}, pluck="name")
		if not names:
			continue
		for name in names:
			frappe.db.set_value(doctype, name, "parent", dinext.name, update_modified=False)
		changed = True
	if changed:
		dinext.reload()


def _restore_dump_if_empty(dinext) -> None:
	path = dump_path()
	if not path.exists():
		return
	if dinext.get("items") or dinext.get("sections") or dinext.get("doctype_items"):
		return

	payload = json.loads(path.read_text(encoding="utf-8"))
	changed = False
	for fieldname in ("items", "sections", "doctype_items"):
		if not dinext.meta.has_field(fieldname):
			continue
		for row in payload.get(fieldname) or []:
			dinext.append(fieldname, row)
			changed = True
	if changed:
		dinext.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dinext Workspace Settings")


def _delete_dump() -> None:
	path = dump_path()
	if path.exists():
		path.unlink()
