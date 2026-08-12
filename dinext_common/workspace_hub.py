"""Runtime data providers for the Dinext Desk Workspace hubs."""

from urllib.parse import urlparse

import frappe
from frappe import _

from dinext_common.setup.hub_catalog import DEFAULT_SECTION_LIST_LIMIT
from dinext_common.workspace_hub_lists import (
	build_section_personal_lists,
	get_section_limits,
	merge_doctype_contributions,
)

SETTINGS_CHILDREN = (
	("Users", "Manage users, roles, and permissions.", "users"),
	("Tools", "Import, export, automation, notifications, and data maintenance.", "tool"),
	("Integrations", "External services, authentication, and integration settings.", "integration"),
	("Build", "Configure DocTypes, reports, scripts, print formats, and system logs.", "setting-gear"),
	("Website", "Website pages, portal, themes, and public site settings.", "website"),
)
SETTINGS_CONFIGURATION = (
	(
		"System Settings",
		"Site-wide language, date formats, session, and system flags.",
		"setting",
	),
	(
		"Security Settings",
		"Login, password policy, and two-factor authentication.",
		"lock",
	),
	(
		"Session Default Settings",
		"Default values applied to new Desk sessions.",
		"users",
	),
	(
		"Document Naming Settings",
		"Naming series and document name generation.",
		"rename",
	),
	(
		"Log Settings",
		"Retention and cleanup for system logs.",
		"file",
	),
	(
		"Global Search Settings",
		"Which DocTypes appear in global search.",
		"search",
	),
	(
		"Domain Settings",
		"Active domains that enable domain-specific features.",
		"organization",
	),
)
SETTINGS_ROLES = {"System Manager", "Workspace Manager"}


@frappe.whitelist()
def get_dinext_hub() -> dict:
	"""Return the current user's configured and accessible Dinext hub cards and lists."""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return {"sections": []}

	# Singleton write is admin-only; hub projection is readable for all Desk users.
	settings = frappe.get_cached_doc("Dinext Workspace Settings")
	section_cards: dict[str, list] = {}
	for item in settings.items:
		if not item.enabled or not _has_required_role(item.required_role):
			continue

		route = _get_route(item.element_type, item.target)
		if not route:
			continue

		section_cards.setdefault(item.section, []).append(
			{
				"label": _(item.label),
				"description": _(item.description or ""),
				"icon": getattr(item, "icon", None) or "",
				"route": route,
			}
		)

	section_limits = get_section_limits(settings)
	configs_by_section: dict[str, list] = {}
	for (_section, _doctype), config in merge_doctype_contributions(settings).items():
		configs_by_section.setdefault(config["section"], []).append(config)

	section_lists: dict[str, dict] = {}
	for section_name, configs in configs_by_section.items():
		limit = section_limits.get(section_name, DEFAULT_SECTION_LIST_LIMIT)
		lists = build_section_personal_lists(section_name, configs, limit=limit)
		if lists:
			section_lists[section_name] = lists

	section_names = list(dict.fromkeys([*section_cards.keys(), *section_lists.keys()]))
	sections = []
	for section in section_names:
		cards = section_cards.get(section) or []
		lists = section_lists.get(section)
		if not cards and not lists:
			continue
		sections.append(
			{
				"label": _(section),
				"items": cards,
				"lists": lists,
				"list_limit": section_limits.get(section, DEFAULT_SECTION_LIST_LIMIT),
			}
		)

	return {"sections": sections}


@frappe.whitelist()
def get_document_titles(doctype: str, names: list | str | None = None) -> list[dict]:
	"""Permission-aware title enrichment for client-side recent lists."""
	if isinstance(names, str):
		names = frappe.parse_json(names)
	names = names or []
	if not doctype or not frappe.db.exists("DocType", doctype):
		return []
	if not frappe.has_permission(doctype, "read"):
		return []

	from dinext_common.workspace_hub_lists import format_records

	# Preserve caller order
	unique_names = []
	seen = set()
	for name in names:
		if name and name not in seen:
			seen.add(name)
			unique_names.append(name)

	return format_records(doctype, unique_names, limit=len(unique_names) or 1)


@frappe.whitelist()
def get_settings_hub() -> dict:
	"""Return Settings Workspace navigation for authorised administrators only."""
	if not SETTINGS_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	workspace_items = []
	for label, description, icon in SETTINGS_CHILDREN:
		route = _get_workspace_route(label)
		if not route:
			continue
		workspace_items.append(
			{
				"label": _(label),
				"description": _(description),
				"icon": icon,
				"route": route,
			}
		)

	configuration_items = []
	for doctype, description, icon in SETTINGS_CONFIGURATION:
		route = _get_configuration_doctype_route(doctype)
		if not route:
			continue
		configuration_items.append(
			{
				"label": _(doctype),
				"description": _(description),
				"icon": icon,
				"route": route,
			}
		)

	sections = []
	if workspace_items:
		sections.append({"label": _("Workspaces"), "items": workspace_items})
	if configuration_items:
		sections.append({"label": _("Configuration"), "items": configuration_items})
	return {"sections": sections}


def _get_configuration_doctype_route(doctype: str) -> str | None:
	"""Desk route for a settings Single when installed and readable."""
	if not frappe.db.exists("DocType", doctype):
		return None
	if not frappe.has_permission(doctype, "read"):
		return None
	return _desk_route(doctype)


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
