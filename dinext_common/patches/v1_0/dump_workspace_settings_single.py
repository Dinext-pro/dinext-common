# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe

from dinext_common.patches.v1_0.workspace_settings_migrate import (
	dump_legacy_children,
	dump_path,
	is_single_settings,
)


def execute() -> None:
	if not is_single_settings():
		return

	path = dump_path()
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(dump_legacy_children(), indent=2, default=str), encoding="utf-8")

	# DocType.validate forbids changing issingle on save; flip it before JSON sync
	# so import does not see a value change.
	frappe.db.set_value(
		"DocType",
		"Dinext Workspace Settings",
		"issingle",
		0,
		update_modified=False,
	)
	frappe.clear_cache(doctype="Dinext Workspace Settings")
	frappe.clear_cache(doctype="DocType")
