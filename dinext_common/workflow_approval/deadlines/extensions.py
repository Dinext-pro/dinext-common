"""Trusted installed-app registry; stored workflow values are type IDs only."""

import frappe

GROUPS = ("deadline_intervals", "sending_intervals", "recipients")


def get_extensions(doctype):
	result = {group: {} for group in GROUPS}
	for path in frappe.get_hooks("workflow_deadline_extensions") or []:
		supplied = frappe.get_attr(path)(doctype) or {}
		for group in GROUPS:
			for key, item in supplied.get(group, {}).items():
				if key in result[group] or key in ("Hours", "Days", "User", "Role"):
					raise ValueError("Duplicate workflow deadline extension: " + key)
				result[group][key] = item
	return result


def options(doctype):
	extensions = get_extensions(doctype)
	bases = {
		"deadline_intervals": ["Hours", "Days"],
		"sending_intervals": ["Hours", "Days"],
		"recipients": ["User", "Role"],
	}
	return {
		group: [{"value": key, "label": frappe._(key)} for key in bases[group]]
		+ [
			{"value": key, "label": frappe._(item.get("label") or key)}
			for key, item in extensions[group].items()
		]
		for group in GROUPS
	}
