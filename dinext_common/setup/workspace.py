# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import json
from pathlib import Path

import frappe

DINEXT_WORKSPACE = "Dinext"
SETTINGS_WORKSPACE = "Settings"
LEGACY_SETTINGS_WORKSPACE = "Настройки"
SETTINGS_CHILDREN = ("Integrations", "Tools", "Users", "Build")
DINEXT_APP_PREFIX = "dinext_"
DINEXT_MODULE = "Dinext Common"
SETTINGS_ROLES = ("System Manager", "Workspace Manager")
DINEXT_HUB_BLOCK = "Dinext Hub"
SETTINGS_HUB_BLOCK = "Dinext Settings Hub"
WORKSPACE_HUB_BLOCKS = {
	DINEXT_WORKSPACE: (DINEXT_HUB_BLOCK, "dinext-hub"),
	SETTINGS_WORKSPACE: (SETTINGS_HUB_BLOCK, "dinext-settings-hub"),
}

DEFAULT_DINEXT_HUB_ITEMS = (
	(
		"My Work",
		"Workspace",
		"Мои задачи",
		"My Tasks",
		"Personal dashboard for your Issues and Tasks: assigned, overdue, and paused items, milestone quick lists, and shortcuts to create new requests.",
		"assign",
	),
	(
		"My Work",
		"Workspace",
		"Моя доска",
		"My Board",
		"Personal Kanban workspace with the My Kanban board for tracking your work visually.",
		"kanban",
	),
	(
		"My Work",
		"Workspace",
		"Мои Таймшиты",
		"My Timesheets",
		"Personal time-tracking hub: your timesheets, leave and expense requests, pending approvals, utilization reports, and related settings.",
		"hr",
	),
	(
		"Project Management",
		"Workspace",
		"Мои проекты",
		"My Projects",
		"Portfolio overview, project directories, status breakdowns, workload and budget reports, and cost-center allocation links.",
		"project",
	),
	(
		"Project Management",
		"Workspace",
		"Аналитика",
		"Analytics",
		"Project and company analytics: revenue, expenses, P&L, revenue by client, and shortcuts to Sales Analytics and Profitability Analysis.",
		"chart",
	),
	(
		"Project Management",
		"Workspace",
		"Скоринг проектов",
		"Project Scoring",
		"Project evaluation hub: scorecards in progress, review or approval, gate failures, scoring profiles, and portfolio reporting.",
		"quality",
	),
	(
		"Project Management",
		"Workspace",
		"Фин. Контроль",
		"Financial Control",
		"Project financial control: cost levels, cost-center allocation approvals, and time-and-material rate reporting.",
		"money-coins-1",
	),
	(
		"Project Management",
		"Workspace",
		"Разработки",
		"Development",
		"GitLab-linked development operations: task and issue status, discrepancies, pipeline failures, traceability exceptions, releases, and artifacts.",
		"stock",
	),
	(
		"Project Management",
		"DocType",
		"Project Portfolio",
		"Project Portfolio",
		"Groups related projects into portfolios for portfolio-level tracking and scoring.",
		"organization",
	),
	(
		"Scope & Governance",
		"DocType",
		"Project Scope",
		"Project Scope",
		"Defines project boundaries through scope items, types, descriptions, and linked records.",
		"list",
	),
	(
		"Scope & Governance",
		"DocType",
		"Project Deliverable",
		"Project Deliverable",
		"Tracks deliverables by type, category, status, progress, related scope, requirements, and responsible parties.",
		"file",
	),
	(
		"Scope & Governance",
		"DocType",
		"Project Change Request",
		"Project Change Request",
		"Manages submittable change requests with initiator, justification, alternatives, and linked project objects.",
		"change",
	),
	(
		"Scope & Governance",
		"DocType",
		"Project Risk",
		"Project Risk",
		"Tracks risk category, impact, probability, response strategy, ownership, and financial reserves.",
		"solid-warning",
	),
	(
		"Scope & Governance",
		"DocType",
		"Project Governance Model",
		"Project Governance Model",
		"Defines lifecycle stages, entry and exit criteria, expected duration, and checkpoint templates.",
		"review",
	),
	(
		"Scope & Governance",
		"DocType",
		"Stage Gate Template",
		"Stage Gate Template",
		"Reusable stage-gate checkpoint templates with mandatory checklist items and evidence requirements.",
		"milestone",
	),
	(
		"Scope & Governance",
		"DocType",
		"Project Stage",
		"Project Stage",
		"Master list of lifecycle stages with code, sequence, description, and gate requirement.",
		"gantt",
	),
	(
		"Scope & Governance",
		"DocType",
		"User Delegate",
		"User Delegate",
		"Temporarily delegates a user's duties to another user for a defined date range.",
		"users",
	),
)


def configure_workspace_menu() -> None:
	"""Hide public non-Dinext workspaces and build the Dinext menu."""
	migrate_legacy_settings_workspace()
	ensure_dinext_roots()
	hide_non_dinext_workspaces()
	nest_settings_children()
	ensure_default_dinext_hub_settings()
	ensure_workspace_hub_blocks()
	frappe.clear_cache()


def ensure_dinext_roots() -> None:
	for title, icon, sequence_id in (
		(DINEXT_WORKSPACE, "organization", 1.0),
		(SETTINGS_WORKSPACE, "setting", 2.0),
	):
		_ensure_public_workspace(title=title, icon=icon, sequence_id=sequence_id)
	ensure_settings_workspace_roles()


def sync_workspace_hub_block_fixtures() -> None:
	"""Force-refresh hub Custom HTML Blocks from app fixtures (script/style/html)."""
	path = Path(frappe.get_app_path("dinext_common")) / "fixtures" / "custom_html_block.json"
	if not path.exists():
		return

	for row in json.loads(path.read_text()):
		name = row.get("name")
		if not name:
			continue
		if frappe.db.exists("Custom HTML Block", name):
			doc = frappe.get_doc("Custom HTML Block", name)
		else:
			doc = frappe.new_doc("Custom HTML Block")
			doc.name = name

		changed = False
		for fieldname in ("html", "script", "style"):
			value = row.get(fieldname) or ""
			if doc.get(fieldname) != value:
				doc.set(fieldname, value)
				changed = True

		wanted_roles = [role_row["role"] for role_row in row.get("roles") or []]
		current_roles = [role_row.role for role_row in doc.roles]
		if current_roles != wanted_roles:
			doc.roles = []
			for role in wanted_roles:
				doc.append("roles", {"role": role})
			changed = True

		if changed or doc.is_new():
			doc.save(ignore_permissions=True)


def ensure_workspace_hub_blocks() -> None:
	"""Keep Custom HTML Block attachments on root Workspaces after migrate/rename."""
	sync_workspace_hub_block_fixtures()

	for workspace_name, (block_name, content_id) in WORKSPACE_HUB_BLOCKS.items():
		if not frappe.db.exists("Workspace", workspace_name):
			continue
		if not frappe.db.exists("Custom HTML Block", block_name):
			continue

		workspace = frappe.get_doc("Workspace", workspace_name)
		changed = False

		if workspace_name == SETTINGS_WORKSPACE:
			if workspace.title != SETTINGS_WORKSPACE:
				workspace.title = SETTINGS_WORKSPACE
				changed = True
			if workspace.label != SETTINGS_WORKSPACE:
				workspace.label = SETTINGS_WORKSPACE
				changed = True

		if _ensure_hub_content_widget(workspace, block_name=block_name, content_id=content_id):
			changed = True

		current_blocks = {row.custom_block_name for row in workspace.custom_blocks}
		if block_name not in current_blocks:
			workspace.append(
				"custom_blocks",
				{"custom_block_name": block_name, "label": block_name},
			)
			changed = True

		if changed:
			workspace.save(ignore_permissions=True)


def _ensure_hub_content_widget(workspace, *, block_name: str, content_id: str) -> bool:
	"""Add the hub custom block widget without replacing existing Workspace content."""
	hub_widget = {
		"id": content_id,
		"type": "custom_block",
		"data": {"custom_block_name": block_name, "col": 12},
	}

	raw = (workspace.content or "").strip()
	if not raw or raw == "[]":
		workspace.content = json.dumps([hub_widget], separators=(",", ":"))
		return True

	try:
		widgets = json.loads(raw)
	except (TypeError, ValueError):
		workspace.content = json.dumps([hub_widget], separators=(",", ":"))
		return True

	if not isinstance(widgets, list):
		workspace.content = json.dumps([hub_widget], separators=(",", ":"))
		return True

	for widget in widgets:
		if not isinstance(widget, dict):
			continue
		data = widget.get("data") or {}
		if widget.get("type") == "custom_block" and data.get("custom_block_name") == block_name:
			return False
		if widget.get("id") == content_id:
			return False

	widgets.append(hub_widget)
	workspace.content = json.dumps(widgets, separators=(",", ":"))
	return True


def migrate_legacy_settings_workspace() -> None:
	"""Rename the former Russian root before ensuring the English replacement."""
	if not frappe.db.exists("Workspace", LEGACY_SETTINGS_WORKSPACE):
		return

	if frappe.db.exists("Workspace", SETTINGS_WORKSPACE):
		frappe.delete_doc("Workspace", LEGACY_SETTINGS_WORKSPACE, force=True, ignore_permissions=True)
		return

	frappe.rename_doc("Workspace", LEGACY_SETTINGS_WORKSPACE, SETTINGS_WORKSPACE, force=True)


def ensure_settings_workspace_roles() -> None:
	if not frappe.db.exists("Workspace", SETTINGS_WORKSPACE):
		return

	workspace = frappe.get_doc("Workspace", SETTINGS_WORKSPACE)
	current_roles = {row.role for row in workspace.roles}
	roles_changed = False
	for role in SETTINGS_ROLES:
		if role not in current_roles:
			workspace.append("roles", {"role": role})
			current_roles.add(role)
			roles_changed = True

	if current_roles != set(SETTINGS_ROLES):
		workspace.roles = [row for row in workspace.roles if row.role in SETTINGS_ROLES]
		roles_changed = True

	if roles_changed:
		workspace.save(ignore_permissions=True)


def ensure_default_dinext_hub_settings() -> None:
	"""Seed the singleton once and backfill missing default icons only."""
	if not frappe.db.exists("DocType", "Dinext Workspace Settings"):
		return

	settings = frappe.get_single("Dinext Workspace Settings")
	if not settings.items:
		for section, element_type, target, label, description, icon in DEFAULT_DINEXT_HUB_ITEMS:
			settings.append(
				"items",
				{
					"section": section,
					"element_type": element_type,
					"target": target,
					"label": label,
					"description": description,
					"icon": icon,
					"enabled": 1,
				},
			)
		settings.save(ignore_permissions=True)
		return

	default_icons = {
		(section, element_type, target): icon
		for section, element_type, target, _label, _description, icon in DEFAULT_DINEXT_HUB_ITEMS
	}
	changed = False
	for item in settings.items:
		if item.icon:
			continue
		icon = default_icons.get((item.section, item.element_type, item.target))
		if icon:
			item.icon = icon
			changed = True

	if changed:
		settings.save(ignore_permissions=True)


def hide_non_dinext_workspaces() -> None:
	dinext_modules = set(
		frappe.get_all(
			"Module Def",
			filters={"app_name": ["like", f"{DINEXT_APP_PREFIX}%"]},
			pluck="name",
		)
	)

	workspaces = frappe.get_all(
		"Workspace",
		filters={"public": 1},
		fields=["name", "is_hidden", "for_user", "module"],
	)

	keep_visible = set(SETTINGS_CHILDREN)
	for workspace in workspaces:
		if workspace.for_user:
			continue

		if workspace.name in keep_visible:
			if workspace.is_hidden:
				frappe.db.set_value(
					"Workspace",
					workspace.name,
					"is_hidden",
					0,
					update_modified=False,
				)
			continue

		if workspace.module not in dinext_modules and not workspace.is_hidden:
			frappe.db.set_value(
				"Workspace",
				workspace.name,
				"is_hidden",
				1,
				update_modified=False,
			)


def nest_settings_children() -> None:
	for name in SETTINGS_CHILDREN:
		if not frappe.db.exists("Workspace", name):
			continue

		values = frappe.db.get_value(
			"Workspace",
			name,
			["parent_page", "is_hidden", "public"],
			as_dict=True,
		)
		updates = {}
		if values.parent_page != SETTINGS_WORKSPACE:
			updates["parent_page"] = SETTINGS_WORKSPACE
		if values.is_hidden:
			updates["is_hidden"] = 0
		if not values.public:
			updates["public"] = 1

		if updates:
			frappe.db.set_value("Workspace", name, updates, update_modified=False)


def set_default_workspace_for_new_user(doc, method=None) -> None:
	"""Assign Dinext as default workspace for newly created users."""
	if doc.name in ("Administrator", "Guest"):
		return

	if doc.default_workspace:
		return

	if not frappe.db.exists("Workspace", DINEXT_WORKSPACE):
		return

	doc.db_set("default_workspace", DINEXT_WORKSPACE, update_modified=False)


def _ensure_public_workspace(*, title: str, icon: str, sequence_id: float) -> None:
	if frappe.db.exists("Workspace", title):
		current = frappe.db.get_value(
			"Workspace",
			title,
			["public", "is_hidden", "parent_page", "module", "for_user"],
			as_dict=True,
		)
		updates = {}
		if not current.public:
			updates["public"] = 1
		if current.is_hidden:
			updates["is_hidden"] = 0
		if current.parent_page:
			updates["parent_page"] = ""
		if current.module != DINEXT_MODULE:
			updates["module"] = DINEXT_MODULE
		if current.for_user:
			updates["for_user"] = ""
		if updates:
			frappe.db.set_value("Workspace", title, updates, update_modified=False)
		return

	doc = frappe.get_doc(
		{
			"doctype": "Workspace",
			"label": title,
			"title": title,
			"module": DINEXT_MODULE,
			"icon": icon,
			"content": "[]",
			"public": 1,
			"for_user": "",
			"parent_page": "",
			"is_hidden": 0,
			"sequence_id": sequence_id,
		}
	)
	doc.insert(ignore_permissions=True)
