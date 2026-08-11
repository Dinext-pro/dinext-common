"""Runtime data providers for the Dinext Desk Workspace hubs."""

from urllib.parse import urlparse

import frappe
from frappe import _

SETTINGS_CHILDREN = (
	("Users", "Manage users, roles, and permissions.", "users"),
	("Tools", "Import, export, automation, notifications, and data maintenance.", "tool"),
	("Integrations", "External services, authentication, and integration settings.", "integration"),
	("Build", "Configure DocTypes, reports, scripts, print formats, and system logs.", "setting-gear"),
)
SETTINGS_ROLES = {"System Manager", "Workspace Manager"}


@frappe.whitelist()
def get_dinext_hub() -> dict:
	"""Return the current user's configured and accessible Dinext hub cards."""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return {"sections": []}

	# Singleton write is admin-only; hub projection is readable for all Desk users.
	settings = frappe.get_cached_doc("Dinext Workspace Settings")
	sections = {}
	for item in settings.items:
		if not item.enabled or not _has_required_role(item.required_role):
			continue

		route = _get_route(item.element_type, item.target)
		if not route:
			continue

		sections.setdefault(item.section, []).append(
			{
				"label": _(item.label),
				"description": _(item.description or ""),
				"icon": getattr(item, "icon", None) or "",
				"route": route,
			}
		)

	return {
		"sections": [
			{"label": _(section), "items": items}
			for section, items in sections.items()
			if items
		]
	}


@frappe.whitelist()
def get_settings_hub() -> dict:
	"""Return Settings Workspace navigation for authorised administrators only."""
	if not SETTINGS_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	items = [
		{
			"label": _(label),
			"description": _(description),
			"icon": icon,
			"route": _get_workspace_route(label),
		}
		for label, description, icon in SETTINGS_CHILDREN
	]
	return {"items": [item for item in items if item["route"]]}


def _has_required_role(required_role: str | None) -> bool:
	return not required_role or required_role in frappe.get_roles()


def _get_route(element_type: str, target: str) -> str | None:
	if not target:
		return None

	if element_type == "Workspace":
		return _get_workspace_route(target)

	if element_type == "DocType":
		return _get_desk_route("DocType", target)

	if element_type == "Report":
		return _get_desk_route("Report", target, "query-report")

	if element_type == "Page":
		return _get_desk_route("Page", target)

	if element_type == "URL":
		return _get_safe_url(target)

	return None


def _get_workspace_route(target: str) -> str | None:
	if not frappe.db.exists("Workspace", target):
		return None

	workspace = frappe.get_doc("Workspace", target)
	if workspace.is_hidden or not frappe.has_permission("Workspace", "read", workspace):
		return None

	return _desk_route(target)


def _get_desk_route(doctype: str, target: str, route_prefix: str | None = None) -> str | None:
	if not frappe.db.exists(doctype, target) or not frappe.has_permission(doctype, "read", target):
		return None

	return _desk_route(target, route_prefix)


def _desk_route(target: str, route_prefix: str | None = None) -> str:
	slug = frappe.scrub(target).replace("_", "-")
	return f"/app/{route_prefix}/{slug}" if route_prefix else f"/app/{slug}"


def _get_safe_url(target: str) -> str | None:
	parsed = urlparse(target)
	if parsed.scheme in {"http", "https"} or (not parsed.scheme and target.startswith("/")):
		return target
	return None
