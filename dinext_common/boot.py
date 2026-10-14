"""Bootinfo extensions for dinext_common."""

from __future__ import annotations

from typing import Any

import frappe

from dinext_common.setup.workspace import omit_replaced_workspaces

CONF_KEY = "dinext_workspace_sidebar_hover_expand"


def as_bool(value: Any, default: bool = True) -> bool:
	"""Parse site_config / conf values into a boolean.

	Missing/None uses *default*. Strings ``0``, ``false``, ``no``, ``off`` (any case)
	and empty string are false; other non-empty strings are true.
	"""
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return bool(value)
	if isinstance(value, str):
		normalized = value.strip().lower()
		if normalized in ("", "0", "false", "no", "off"):
			return False
		return True
	return bool(value)


def workflow_action_icons() -> dict[str, str]:
	"""Action name to Frappe icon. Empty icons are omitted. Missing column yields {}."""
	try:
		if not frappe.db.has_column("Workflow Action Master", "custom_icon"):
			return {}
		rows = frappe.get_all("Workflow Action Master", fields=["name", "custom_icon"])
	except Exception:
		return {}
	if not isinstance(rows, list):
		return {}
	icons: dict[str, str] = {}
	for row in rows:
		if not isinstance(row, dict):
			continue
		icon = str(row.get("custom_icon") or "").strip()
		name = row.get("name")
		if icon and name:
			icons[str(name)] = icon
	return icons


def extend_bootinfo(bootinfo) -> None:
	"""Expose workspace sidebar hover-expand flag to Desk (default: enabled).

	Does not filter ``bootinfo.changelog_feed`` by app name: owned daily sync
	already replaces local ``Changelog Feed`` with Dinext News Feed items that
	may use any ``app_name``.
	"""
	raw = frappe.conf.get(CONF_KEY, 1)
	bootinfo.dinext_workspace_sidebar_hover_expand = as_bool(raw, default=True)
	bootinfo.enable_parallel_workflow_approval = as_bool(
		frappe.conf.get("enable_parallel_workflow_approval", False),
		default=False,
	)
	bootinfo.workflow_action_icons = workflow_action_icons()
	pages = getattr(bootinfo, "allowed_workspaces", None)
	if isinstance(pages, (list, tuple)):
		bootinfo.allowed_workspaces = omit_replaced_workspaces(pages)
