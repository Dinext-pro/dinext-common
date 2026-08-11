"""Bootinfo extensions for dinext_common."""

from __future__ import annotations

from typing import Any

import frappe

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


def extend_bootinfo(bootinfo) -> None:
	"""Expose workspace sidebar hover-expand flag to Desk (default: enabled).

	Does not filter ``bootinfo.changelog_feed`` by app name: owned daily sync
	already replaces local ``Changelog Feed`` with Dinext News Feed items that
	may use any ``app_name``.
	"""
	raw = frappe.conf.get(CONF_KEY, 1)
	bootinfo.dinext_workspace_sidebar_hover_expand = as_bool(raw, default=True)
