# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from dinext_common.setup.hub_catalog import (
	register_hub_doctype_items,
	register_hub_items,
	register_hub_sections,
)
from dinext_common.setup.workspace import (
	DINEXT_HUB_BLOCK,
	DINEXT_WORKSPACE,
	SETTINGS_CHILDREN,
	SETTINGS_ROLES,
	SETTINGS_WORKSPACE,
	configure_workspace_menu,
	ensure_default_dinext_hub_settings,
	set_default_workspace_for_new_user,
)
from dinext_common.workspace_hub import (
	SETTINGS_CHILDREN as HUB_SETTINGS_CHILDREN,
	SETTINGS_CONFIGURATION,
	_get_route,
	_get_safe_url,
	get_dinext_hub,
	get_settings_hub,
)
from dinext_common.workspace_hub_lists import parse_attention_filter

SAMPLE_HUB_ITEM = {
	"section": "My Work",
	"element_type": "Workspace",
	"target": "Мои задачи",
	"label": "My Tasks",
	"description": (
		"Personal dashboard for your Issues and Tasks: assigned, overdue, and paused items, "
		"milestone quick lists, and shortcuts to create new requests."
	),
	"icon": "assign",
	"enabled": 1,
}

_HUB_SNAPSHOT_SKIP = {
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


def _snapshot_hub_settings():
	settings = frappe.get_single("Dinext Workspace Settings")

	def rows(fieldname):
		if not settings.meta.has_field(fieldname):
			return []
		return [
			{key: value for key, value in row.as_dict().items() if key not in _HUB_SNAPSHOT_SKIP}
			for row in settings.get(fieldname) or []
		]

	return {
		"items": rows("items"),
		"sections": rows("sections"),
		"doctype_items": rows("doctype_items"),
	}


def _restore_hub_settings(snapshot):
	settings = frappe.get_single("Dinext Workspace Settings")
	for fieldname in ("items", "sections", "doctype_items"):
		if not settings.meta.has_field(fieldname):
			continue
		settings.set(fieldname, [])
		for row in snapshot.get(fieldname) or []:
			settings.append(fieldname, row)
	settings.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Dinext Workspace Settings")


def _clear_hub_settings(test_case=None):
	snapshot = _snapshot_hub_settings()
	if test_case is not None:
		test_case.addCleanup(_restore_hub_settings, snapshot)
	settings = frappe.get_single("Dinext Workspace Settings")
	settings.items = []
	if settings.meta.has_field("sections"):
		settings.sections = []
	if settings.meta.has_field("doctype_items"):
		settings.doctype_items = []
	settings.save(ignore_permissions=True)
	settings.reload()
	return settings


class TestDinextWorkspaceMenu(FrappeTestCase):
	def test_configure_ensures_roots_hides_standard_and_nests_children(self):
		configure_workspace_menu()

		for name in (DINEXT_WORKSPACE, SETTINGS_WORKSPACE):
			self.assertTrue(frappe.db.exists("Workspace", name))
			ws = frappe.db.get_value(
				"Workspace",
				name,
				["public", "is_hidden", "parent_page", "module", "for_user"],
				as_dict=True,
			)
			self.assertEqual(ws.public, 1)
			self.assertEqual(ws.is_hidden, 0)
			self.assertEqual(ws.parent_page or "", "")
			self.assertEqual(ws.module, "Dinext Common")
			self.assertEqual(ws.for_user or "", "")

		for name in SETTINGS_CHILDREN:
			if not frappe.db.exists("Workspace", name):
				continue
			ws = frappe.db.get_value(
				"Workspace",
				name,
				["parent_page", "is_hidden", "public"],
				as_dict=True,
			)
			self.assertEqual(ws.parent_page, SETTINGS_WORKSPACE)
			self.assertEqual(ws.is_hidden, 0)
			self.assertEqual(ws.public, 1)

		dinext_modules = set(
			frappe.get_all(
				"Module Def",
				filters={"app_name": ["like", "dinext_%"]},
				pluck="name",
			)
		)
		workspaces = frappe.get_all(
			"Workspace",
			filters={"public": 1},
			fields=["name", "module", "is_hidden", "for_user"],
		)
		for ws in workspaces:
			if ws.for_user or ws.name in (
				DINEXT_WORKSPACE,
				SETTINGS_WORKSPACE,
				*SETTINGS_CHILDREN,
			):
				continue

			if ws.module in dinext_modules:
				continue

			self.assertEqual(
				ws.is_hidden,
				1,
				msg=f"public non-Dinext workspace {ws.name!r} must be hidden",
			)

	def test_configure_is_idempotent(self):
		configure_workspace_menu()
		configure_workspace_menu()

		self.assertEqual(
			frappe.db.get_value("Workspace", SETTINGS_WORKSPACE, "parent_page") or "",
			"",
		)
		if frappe.db.exists("Workspace", "Tools"):
			self.assertEqual(
				frappe.db.get_value("Workspace", "Tools", "parent_page"),
				SETTINGS_WORKSPACE,
			)

	def test_new_user_gets_default_workspace(self):
		configure_workspace_menu()
		email = f"ws-menu-{random_string(8).lower()}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Workspace",
				"last_name": "Menu",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", user.name, force=True, ignore_permissions=True))

		self.assertEqual(
			frappe.db.get_value("User", user.name, "default_workspace"),
			DINEXT_WORKSPACE,
		)

	def test_existing_user_default_workspace_untouched_by_configure(self):
		email = f"ws-keep-{random_string(8).lower()}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Keep",
				"last_name": "Workspace",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		# after_insert still runs and may set default_workspace; clear it afterwards
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", user.name, force=True, ignore_permissions=True))

		# Simulate a pre-existing empty preference that configure must not touch
		frappe.db.set_value("User", user.name, "default_workspace", "", update_modified=False)
		configure_workspace_menu()
		self.assertFalse(frappe.db.get_value("User", user.name, "default_workspace"))

	def test_user_after_insert_hook_is_registered(self):
		hooks = frappe.get_doc_hooks().get("User", {}).get("after_insert", [])
		self.assertIn(
			"dinext_common.setup.workspace.set_default_workspace_for_new_user",
			hooks,
		)

	def test_handler_skips_when_default_already_set(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"ws-preset-{random_string(8).lower()}@example.com",
				"first_name": "Preset",
				"default_workspace": "Build" if frappe.db.exists("Workspace", "Build") else DINEXT_WORKSPACE,
				"send_welcome_email": 0,
			}
		)
		# Call handler directly with a doc that already has default_workspace
		before = user.default_workspace
		set_default_workspace_for_new_user(user)
		self.assertEqual(user.default_workspace, before)

	def test_workspace_hubs_and_settings_roles(self):
		configure_workspace_menu()

		dinext = frappe.get_doc("Workspace", DINEXT_WORKSPACE)
		settings = frappe.get_doc("Workspace", SETTINGS_WORKSPACE)
		self.assertEqual(dinext.custom_blocks[0].custom_block_name, "Dinext Hub")
		self.assertEqual(settings.custom_blocks[0].custom_block_name, "Dinext Settings Hub")
		self.assertEqual({row.role for row in settings.roles}, set(SETTINGS_ROLES))
		self.assertEqual(settings.label, "Settings")
		self.assertEqual(settings.title, "Settings")

	def test_dinext_hub_reflects_enabled_configuration(self):
		configure_workspace_menu()
		settings = frappe.get_single("Dinext Workspace Settings")
		item = settings.append(
			"items",
			{
				"section": "Test",
				"element_type": "Workspace",
				"target": DINEXT_WORKSPACE,
				"label": "Portfolio for test",
				"description": "Updated test description",
				"icon": "organization",
				"enabled": 1,
			},
		)
		settings.save(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Dinext Workspace Settings Item", item.name, force=True))

		cards = [card for section in get_dinext_hub()["sections"] for card in section["items"]]
		card = next(card for card in cards if card["label"] == "Portfolio for test")
		self.assertEqual(card["description"], "Updated test description")
		self.assertEqual(card["route"], "/app/dinext")
		self.assertEqual(card["icon"], "organization")

	def test_dinext_hub_omits_unavailable_target(self):
		configure_workspace_menu()
		settings = frappe.get_single("Dinext Workspace Settings")
		item = settings.append(
			"items",
			{
				"section": "Test",
				"element_type": "DocType",
				"target": "Not Installed Dinext Target",
				"label": "Unavailable target",
				"enabled": 1,
			},
		)
		settings.save(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Dinext Workspace Settings Item", item.name, force=True))

		cards = [card for section in get_dinext_hub()["sections"] for card in section["items"]]
		self.assertNotIn("Unavailable target", {card["label"] for card in cards})

	def test_common_does_not_seed_domain_hub_cards(self):
		configure_workspace_menu()
		settings = _clear_hub_settings(self)
		ensure_default_dinext_hub_settings()
		settings.reload()
		self.assertEqual(len(settings.items), 0)

	def test_register_hub_items_appends_and_is_idempotent(self):
		configure_workspace_menu()
		_clear_hub_settings(self)

		register_hub_items([SAMPLE_HUB_ITEM], source_app="dinext_projects")
		settings = frappe.get_single("Dinext Workspace Settings")
		self.assertEqual(len(settings.items), 1)
		row = settings.items[0]
		self.assertEqual(row.label, "My Tasks")
		self.assertEqual(row.icon, "assign")
		self.assertEqual(row.source_app, "dinext_projects")

		row.label = "Admin override"
		row.icon = ""
		settings.save(ignore_permissions=True)

		register_hub_items(
			[{**SAMPLE_HUB_ITEM, "label": "Should not overwrite", "icon": "assign"}],
			source_app="dinext_projects",
		)
		settings.reload()
		self.assertEqual(len(settings.items), 1)
		self.assertEqual(settings.items[0].label, "Admin override")
		self.assertEqual(settings.items[0].icon, "assign")

	def test_get_dinext_hub_localizes_english_and_russian(self):
		from unittest.mock import patch

		from frappe.translate import get_full_dict

		configure_workspace_menu()
		_clear_hub_settings(self)

		ru_messages = get_full_dict("ru")
		self.assertEqual(
			ru_messages.get("Manage users, roles, and permissions."),
			"Управление пользователями, ролями и правами доступа.",
		)

		settings = frappe.get_single("Dinext Workspace Settings")
		item = settings.append(
			"items",
			{
				"section": "My Work",
				"element_type": "Workspace",
				"target": DINEXT_WORKSPACE,
				"label": "My Tasks",
				"description": (
					"Personal dashboard for your Issues and Tasks: assigned, overdue, and paused items, "
					"milestone quick lists, and shortcuts to create new requests."
				),
				"icon": "assign",
				"enabled": 1,
			},
		)
		settings.save(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Dinext Workspace Settings Item", item.name, force=True))

		previous_lang = frappe.local.lang
		self.addCleanup(lambda: setattr(frappe.local, "lang", previous_lang))

		frappe.local.lang = "en"
		en_sections = get_dinext_hub()["sections"]
		en_section_labels = {section["label"] for section in en_sections}
		en_cards = {card["label"]: card for section in en_sections for card in section["items"]}
		self.assertIn("My Work", en_section_labels)
		self.assertIn("My Tasks", en_cards)
		self.assertTrue(
			en_cards["My Tasks"]["description"].startswith("Personal dashboard for your Issues and Tasks")
		)

		translations = {
			"My Work": "Моя работа",
			"My Tasks": "Мои задачи",
			(
				"Personal dashboard for your Issues and Tasks: assigned, overdue, and paused items, "
				"milestone quick lists, and shortcuts to create new requests."
			): (
				"Персональная панель запросов и задач: назначенные, просроченные и приостановленные, "
				"быстрые списки по вехам и ярлыки создания новых запросов."
			),
		}

		def fake_translate(msg, *args, **kwargs):
			return translations.get(msg, msg)

		frappe.local.lang = "ru"
		with patch("dinext_common.workspace_hub._", side_effect=fake_translate):
			ru_sections = get_dinext_hub()["sections"]
		ru_section_labels = {section["label"] for section in ru_sections}
		ru_cards = {card["label"]: card for section in ru_sections for card in section["items"]}
		self.assertIn("Моя работа", ru_section_labels)
		self.assertIn("Мои задачи", ru_cards)
		self.assertTrue(
			ru_cards["Мои задачи"]["description"].startswith("Персональная панель запросов и задач")
		)

	def test_settings_hub_returns_children_and_rejects_non_admin(self):
		configure_workspace_menu()
		payload = get_settings_hub()
		sections = {section["label"]: section["items"] for section in payload["sections"]}
		self.assertIn("Workspaces", sections)
		self.assertIn("Configuration", sections)

		workspace_items = sections["Workspaces"]
		expected_workspace_labels = {label for label, _description, _icon in HUB_SETTINGS_CHILDREN}
		self.assertEqual({item["label"] for item in workspace_items}, expected_workspace_labels)
		self.assertEqual(
			{item["label"]: item["icon"] for item in workspace_items},
			{label: icon for label, _description, icon in HUB_SETTINGS_CHILDREN},
		)
		for item in workspace_items:
			self.assertTrue(item["description"])

		configuration_items = sections["Configuration"]
		expected_config = {doctype for doctype, _description, _icon in SETTINGS_CONFIGURATION}
		actual_config = {item["label"] for item in configuration_items}
		self.assertTrue(actual_config)
		self.assertTrue(actual_config.issubset(expected_config))
		for item in configuration_items:
			self.assertTrue(item["description"])
			self.assertTrue(item["route"])
			self.assertIn(item["label"], expected_config)

		current_user = frappe.session.user
		frappe.set_user("Guest")
		self.addCleanup(lambda: frappe.set_user(current_user))
		with self.assertRaises(frappe.PermissionError):
			get_settings_hub()

	def test_settings_hub_omits_missing_configuration_doctype(self):
		from unittest.mock import patch

		configure_workspace_menu()
		with patch(
			"dinext_common.workspace_hub._get_configuration_doctype_route",
			side_effect=lambda doctype: None
			if doctype == "Domain Settings"
			else f"/app/{frappe.scrub(doctype).replace('_', '-')}",
		):
			payload = get_settings_hub()
		labels = {
			item["label"]
			for section in payload["sections"]
			if section["label"] == "Configuration"
			for item in section["items"]
		}
		self.assertNotIn("Domain Settings", labels)
		self.assertIn("System Settings", labels)
	def test_hub_attachment_preserves_existing_workspace_content(self):
		configure_workspace_menu()
		workspace = frappe.get_doc("Workspace", DINEXT_WORKSPACE)
		existing = {
			"id": "keep-me",
			"type": "header",
			"data": {"text": "Keep this widget", "col": 12},
		}
		workspace.content = json.dumps([existing], separators=(",", ":"))
		workspace.custom_blocks = []
		workspace.save(ignore_permissions=True)

		configure_workspace_menu()
		workspace.reload()
		widgets = json.loads(workspace.content or "[]")
		self.assertEqual(widgets[0]["id"], "keep-me")
		self.assertEqual(
			sum(
				1
				for widget in widgets
				if isinstance(widget, dict)
				and widget.get("type") == "custom_block"
				and (widget.get("data") or {}).get("custom_block_name") == DINEXT_HUB_BLOCK
			),
			1,
		)

		before = workspace.content
		configure_workspace_menu()
		workspace.reload()
		self.assertEqual(workspace.content, before)

	def test_dinext_hub_omits_disabled_and_role_restricted_items(self):
		configure_workspace_menu()
		settings = frappe.get_single("Dinext Workspace Settings")
		disabled = settings.append(
			"items",
			{
				"section": "Test",
				"element_type": "Workspace",
				"target": DINEXT_WORKSPACE,
				"label": "Disabled hub card",
				"enabled": 0,
			},
		)
		restricted = settings.append(
			"items",
			{
				"section": "Test",
				"element_type": "Workspace",
				"target": DINEXT_WORKSPACE,
				"label": "Role restricted hub card",
				"required_role": "System Manager",
				"enabled": 1,
			},
		)
		settings.save(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Dinext Workspace Settings Item", disabled.name, force=True))
		self.addCleanup(lambda: frappe.delete_doc("Dinext Workspace Settings Item", restricted.name, force=True))

		email = f"ws-hub-{random_string(8).lower()}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Hub",
				"last_name": "Viewer",
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": "Desk User"}],
			}
		)
		user.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", user.name, force=True, ignore_permissions=True))

		current_user = frappe.session.user
		frappe.set_user(user.name)
		self.addCleanup(lambda: frappe.set_user(current_user))

		labels = {card["label"] for section in get_dinext_hub()["sections"] for card in section["items"]}
		self.assertNotIn("Disabled hub card", labels)
		self.assertNotIn("Role restricted hub card", labels)

		frappe.set_user("Administrator")
		labels = {card["label"] for section in get_dinext_hub()["sections"] for card in section["items"]}
		self.assertIn("Role restricted hub card", labels)

	def test_hub_route_helpers(self):
		configure_workspace_menu()
		self.assertEqual(_get_route("Workspace", DINEXT_WORKSPACE), "/app/dinext")
		self.assertEqual(_get_route("DocType", "User"), "/app/user")
		if frappe.db.exists("Report", "Database Storage Usage By Tables"):
			self.assertEqual(
				_get_route("Report", "Database Storage Usage By Tables"),
				"/app/query-report/database-storage-usage-by-tables",
			)
		if frappe.db.exists("Page", "permission-manager"):
			self.assertEqual(_get_route("Page", "permission-manager"), "/app/permission-manager")
		self.assertEqual(_get_route("URL", "https://example.com/path"), "https://example.com/path")
		self.assertEqual(_get_route("URL", "/app/user"), "/app/user")
		self.assertIsNone(_get_safe_url("javascript:alert(1)"))
		self.assertIsNone(_get_route("DocType", "Not Installed Dinext Target"))

	def test_hub_fixture_scripts_use_set_route_and_sprite_urls(self):
		path = Path(frappe.get_app_path("dinext_common")) / "fixtures" / "custom_html_block.json"
		blocks = {row["name"]: row for row in json.loads(path.read_text())}
		for name in ("Dinext Hub", "Dinext Settings Hub"):
			script = blocks[name]["script"]
			style = blocks[name]["style"]
			self.assertIn("frappe.set_route", script)
			self.assertIn("navigate_route", script)
			self.assertIn("/assets/frappe/icons/timeless/icons.svg", script)
			self.assertNotIn("svg.style.width", script)
			self.assertIn(".dinext-workspace-hub__card-icon .icon", style)
			self.assertIn(
				".dinext-workspace-hub__card:hover .dinext-workspace-hub__card-title { text-decoration: underline; }",
				style,
			)
			self.assertIn(
				".dinext-workspace-hub__card-description { margin-top: .35rem; color: var(--text-muted); font-size: var(--text-tiny, 11px); text-decoration: none; }",
				style,
			)

		dinext_script = blocks["Dinext Hub"]["script"]
		dinext_style = blocks["Dinext Hub"]["style"]
		self.assertIn("frappe.new_doc", dinext_script)
		self.assertIn("make_section_lists", dinext_script)
		self.assertIn("make_create_column", dinext_script)
		self.assertIn("make_column_heading", dinext_script)
		self.assertIn("make_type_badge", dinext_script)
		self.assertIn("section.lists", dinext_script)
		self.assertIn("lists.recent", dinext_script)
		self.assertIn("dinext-workspace-hub__create-buttons", dinext_script)
		self.assertIn("es-line-time", dinext_script)
		self.assertIn("es-line-alert-triangle", dinext_script)
		self.assertNotIn("make_doctype_block", dinext_script)
		self.assertNotIn("frappe.route_history", dinext_script)
		self.assertNotIn("get_document_titles", dinext_script)
		self.assertNotIn("recent_from_route_history", dinext_script)
		self.assertNotIn("dropdown-toggle", dinext_script)
		self.assertNotIn("__('My Items')", dinext_script)
		self.assertNotIn("dinext-workspace-hub__personal-header", dinext_script)
		self.assertNotIn(".dinext-workspace-hub__doctypes", dinext_style)
		self.assertNotIn(".dinext-workspace-hub__create-menu", dinext_style)
		self.assertIn(".dinext-workspace-hub__lists", dinext_style)
		self.assertIn("repeat(5, minmax(0, 1fr))", dinext_style)
		self.assertIn("text-transform: none", dinext_style)
		self.assertIn(".dinext-workspace-hub__type-badge", dinext_style)
		self.assertIn(".dinext-workspace-hub__create-buttons", dinext_style)
		self.assertIn(".dinext-workspace-hub__list-title-icon", dinext_style)
		self.assertIn("is_font_icon", dinext_script)
		self.assertIn("fa ", dinext_script)
		self.assertIn("aria-label", dinext_script)
		self.assertNotIn("label.className = 'dinext-workspace-hub__type-label'", dinext_script)
		self.assertIn(".dinext-workspace-hub__type-icon .fa", dinext_style)
		self.assertIn(".dinext-workspace-hub__type-icon .octicon", dinext_style)
		self.assertNotIn("max-width: 5.5rem", dinext_style)

	def test_register_sections_and_doctype_items_merge(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		settings = frappe.get_single("Dinext Workspace Settings")
		settings.sections = []
		settings.doctype_items = []
		settings.save(ignore_permissions=True)

		register_hub_sections([{"section": "My Work", "list_limit": 5}], source_app="dinext_projects")
		register_hub_sections([{"section": "My Work", "list_limit": 9}], source_app="dinext_kanban")
		register_hub_doctype_items(
			[
				{
					"section": "My Work",
					"document_type": "Task",
					"show_assigned": 1,
					"show_liked": 1,
					"show_attention": 1,
					"attention_filter": [["Task", "status", "=", "Overdue"]],
				}
			],
			source_app="dinext_projects",
		)
		register_hub_doctype_items(
			[
				{
					"section": "My Work",
					"document_type": "Task",
					"show_quick_create": 1,
					"show_recently_opened": 1,
					"show_assigned": 1,
					"show_attention": 1,
					"attention_filter": [["Task", "type", "!=", "Issue"]],
				}
			],
			source_app="dinext_kanban",
		)

		issue_registered = False
		if frappe.db.exists("DocType", "Issue"):
			register_hub_doctype_items(
				[
					{
						"section": "My Work",
						"document_type": "Issue",
						"show_quick_create": 1,
						"show_assigned": 1,
						"show_liked": 1,
					}
				],
				source_app="dinext_projects",
			)
			issue_registered = True

		settings.reload()
		self.assertEqual(len(settings.sections), 1)
		self.assertEqual(settings.sections[0].list_limit, 5)
		self.assertEqual(len(settings.doctype_items), 3 if issue_registered else 2)

		payload = get_dinext_hub()
		section = next(s for s in payload["sections"] if s["label"] == "My Work")
		self.assertNotIn("doctypes", section)
		lists = section["lists"]
		self.assertIsNotNone(lists)
		self.assertTrue(lists["show_recently_opened"])
		self.assertTrue(lists["show_assigned"])
		self.assertTrue(lists["show_liked"])
		self.assertTrue(lists["show_attention"])
		self.assertEqual(section["list_limit"], 5)
		self.assertEqual(lists["list_limit"], 5)

		create_doctypes = {row["doctype"] for row in lists["create_actions"]}
		if frappe.has_permission("Task", "create"):
			self.assertIn("Task", create_doctypes)
		if issue_registered and frappe.has_permission("Issue", "create"):
			self.assertIn("Issue", create_doctypes)
		self.assertEqual(len(lists["create_actions"]), len(create_doctypes))

		self.assertTrue(isinstance(lists["recent"], list))
		# Without seeded Route History Form entries, recent stays empty but flag remains on.
		self.assertLessEqual(len(lists["recent"]), lists["list_limit"])
		for row in lists["create_actions"]:
			self.assertIn("label", row)
			self.assertIn("icon", row)

	def test_parse_attention_filter_and_invalid(self):
		parsed = parse_attention_filter(
			'[["Task","status","=","Overdue",false],["Task","type","!=","Issue",false]]',
			"Task",
		)
		self.assertEqual(parsed, [["status", "=", "Overdue"], ["type", "!=", "Issue"]])
		self.assertIsNone(parse_attention_filter("{not-json", "Task"))

	def test_assigned_list_includes_readable_todo(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		settings = frappe.get_single("Dinext Workspace Settings")
		settings.sections = []
		settings.doctype_items = []
		settings.save(ignore_permissions=True)

		note = frappe.get_doc({"doctype": "Note", "title": f"hub-assign-{random_string(6)}", "public": 1})
		note.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Note", note.name, force=True, ignore_permissions=True))

		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": "hub assign",
				"allocated_to": "Administrator",
				"reference_type": "Note",
				"reference_name": note.name,
				"status": "Open",
			}
		)
		todo.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("ToDo", todo.name, force=True, ignore_permissions=True))

		register_hub_sections([{"section": "Test Lists", "list_limit": 5}], source_app="dinext_common")
		register_hub_doctype_items(
			[
				{
					"section": "Test Lists",
					"document_type": "Note",
					"show_assigned": 1,
				}
			],
			source_app="dinext_common",
		)

		payload = get_dinext_hub()
		section = next(s for s in payload["sections"] if s["label"] == "Test Lists")
		lists = section["lists"]
		self.assertTrue(lists["show_assigned"])
		assigned = lists["assigned"]
		self.assertIn(note.name, {row["name"] for row in assigned})
		row = next(item for item in assigned if item["name"] == note.name)
		self.assertEqual(row["doctype"], "Note")
		self.assertIn("type_label", row)
		self.assertIn("icon", row)
		self.assertEqual(row["icon"], frappe.get_meta("Note").icon)
		self.assertIn("route", row)
		self.assertIn("modified", row)

	def test_section_assigned_merges_doctypes_and_applies_limit(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		settings = frappe.get_single("Dinext Workspace Settings")
		settings.sections = []
		settings.doctype_items = []
		settings.save(ignore_permissions=True)

		notes = []
		for idx in range(3):
			note = frappe.get_doc(
				{"doctype": "Note", "title": f"hub-merge-{idx}-{random_string(4)}", "public": 1}
			)
			note.insert(ignore_permissions=True)
			notes.append(note)
			self.addCleanup(
				lambda name=note.name: frappe.delete_doc("Note", name, force=True, ignore_permissions=True)
			)
			todo = frappe.get_doc(
				{
					"doctype": "ToDo",
					"description": f"hub merge {idx}",
					"allocated_to": "Administrator",
					"reference_type": "Note",
					"reference_name": note.name,
					"status": "Open",
				}
			)
			todo.insert(ignore_permissions=True)
			self.addCleanup(
				lambda name=todo.name: frappe.delete_doc("ToDo", name, force=True, ignore_permissions=True)
			)

		# Second DocType contribution: ToDo itself (self-assigned open ToDos)
		extra_todos = []
		for idx in range(2):
			todo = frappe.get_doc(
				{
					"doctype": "ToDo",
					"description": f"hub-merge-todo-{idx}-{random_string(4)}",
					"allocated_to": "Administrator",
					"status": "Open",
				}
			)
			todo.insert(ignore_permissions=True)
			extra_todos.append(todo)
			self.addCleanup(
				lambda name=todo.name: frappe.delete_doc("ToDo", name, force=True, ignore_permissions=True)
			)
			link = frappe.get_doc(
				{
					"doctype": "ToDo",
					"description": f"link for {todo.name}",
					"allocated_to": "Administrator",
					"reference_type": "ToDo",
					"reference_name": todo.name,
					"status": "Open",
				}
			)
			link.insert(ignore_permissions=True)
			self.addCleanup(
				lambda name=link.name: frappe.delete_doc("ToDo", name, force=True, ignore_permissions=True)
			)

		register_hub_sections([{"section": "Merged Lists", "list_limit": 2}], source_app="dinext_common")
		register_hub_doctype_items(
			[
				{"section": "Merged Lists", "document_type": "Note", "show_assigned": 1},
				{"section": "Merged Lists", "document_type": "ToDo", "show_assigned": 1, "show_quick_create": 1},
			],
			source_app="dinext_common",
		)

		payload = get_dinext_hub()
		section = next(s for s in payload["sections"] if s["label"] == "Merged Lists")
		lists = section["lists"]
		self.assertEqual(lists["list_limit"], 2)
		self.assertLessEqual(len(lists["assigned"]), 2)
		doctypes = {row["doctype"] for row in lists["assigned"]}
		self.assertTrue(doctypes.issubset({"Note", "ToDo"}))
		self.assertTrue(all("type_label" in row and "modified" in row for row in lists["assigned"]))
		create_doctypes = {row["doctype"] for row in lists["create_actions"]}
		if frappe.has_permission("ToDo", "create"):
			self.assertIn("ToDo", create_doctypes)
		self.assertNotIn("Note", create_doctypes)

	def test_recent_list_uses_route_history_with_dedupe_and_limit(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		settings = frappe.get_single("Dinext Workspace Settings")
		settings.sections = []
		settings.doctype_items = []
		settings.save(ignore_permissions=True)

		notes = []
		for idx in range(3):
			note = frappe.get_doc(
				{"doctype": "Note", "title": f"hub-recent-{idx}-{random_string(4)}", "public": 1}
			)
			note.insert(ignore_permissions=True)
			notes.append(note)
			self.addCleanup(
				lambda name=note.name: frappe.delete_doc("Note", name, force=True, ignore_permissions=True)
			)

		# Older duplicate visit for notes[0], then fresher unique visits.
		from frappe.utils import add_to_date, now_datetime

		history_routes = [
			f"Form/Note/{notes[0].name}",
			f"Form/Note/{notes[1].name}",
			f"Form/Note/{notes[0].name}",
			f"app/note/{notes[2].name}",
			"Workspaces/Dinext",
		]
		base = now_datetime()
		for idx, route in enumerate(history_routes):
			row = frappe.get_doc(
				{
					"doctype": "Route History",
					"route": route,
					"user": "Administrator",
				}
			)
			row.insert(ignore_permissions=True)
			frappe.db.set_value(
				"Route History",
				row.name,
				"creation",
				add_to_date(base, seconds=idx),
				update_modified=False,
			)
			self.addCleanup(
				lambda name=row.name: frappe.delete_doc(
					"Route History", name, force=True, ignore_permissions=True
				)
			)
		frappe.db.commit()

		register_hub_sections([{"section": "Recent Lists", "list_limit": 2}], source_app="dinext_common")
		register_hub_doctype_items(
			[
				{
					"section": "Recent Lists",
					"document_type": "Note",
					"show_recently_opened": 1,
				}
			],
			source_app="dinext_common",
		)

		payload = get_dinext_hub()
		section = next(s for s in payload["sections"] if s["label"] == "Recent Lists")
		lists = section["lists"]
		self.assertTrue(lists["show_recently_opened"])
		self.assertNotIn("recent_doctypes", lists)
		recent = lists["recent"]
		self.assertEqual(len(recent), 2)
		# Newest unique Form/app routes first: notes[2], then notes[0] (duplicate skipped).
		self.assertEqual([row["name"] for row in recent], [notes[2].name, notes[0].name])
		self.assertTrue(all(row["doctype"] == "Note" for row in recent))
		self.assertTrue(all("type_label" in row and "route" in row for row in recent))
		self.assertNotIn(notes[1].name, {row["name"] for row in recent})

