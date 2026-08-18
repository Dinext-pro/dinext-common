# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from dinext_common.setup.hub_catalog import (
	DEFAULT_SECTION_CARD_COLUMNS,
	DINEXT_HUB_SETTINGS,
	SETTINGS_HUB_SETTINGS,
	SETTINGS_SECTION_CARD_COLUMNS,
	ensure_workspace_settings,
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
	get_workspace_sidebar_items,
	omit_replaced_workspaces,
	set_default_workspace_for_new_user,
)
from dinext_common.workspace_hub import (
	SETTINGS_CHILDREN as HUB_SETTINGS_CHILDREN,
	SETTINGS_CONFIGURATION,
	_get_route,
	_get_safe_url,
	get_dinext_hub,
	get_settings_hub,
	get_workspace_hub,
)
from dinext_common.workspace_hub_lists import parse_attention_filter, parse_list_filter

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


def _snapshot_hub_settings(name=DINEXT_HUB_SETTINGS):
	settings = frappe.get_doc("Dinext Workspace Settings", name)

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


def _restore_hub_settings(snapshot, name=DINEXT_HUB_SETTINGS):
	settings = frappe.get_doc("Dinext Workspace Settings", name)
	for fieldname in ("items", "sections", "doctype_items"):
		if not settings.meta.has_field(fieldname):
			continue
		settings.set(fieldname, [])
		for row in snapshot.get(fieldname) or []:
			settings.append(fieldname, row)
	settings.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Dinext Workspace Settings")


def _clear_hub_settings(test_case=None, name=DINEXT_HUB_SETTINGS):
	snapshot = _snapshot_hub_settings(name)
	if test_case is not None:
		test_case.addCleanup(_restore_hub_settings, snapshot, name)
	settings = frappe.get_doc("Dinext Workspace Settings", name)
	settings.items = []
	if settings.meta.has_field("sections"):
		settings.sections = []
	if settings.meta.has_field("doctype_items"):
		settings.doctype_items = []
	settings.save(ignore_permissions=True)
	settings.reload()
	return settings


def _delete_scratch_hub_settings(name):
	if name in (DINEXT_HUB_SETTINGS, SETTINGS_HUB_SETTINGS):
		return
	if frappe.db.exists("Dinext Workspace Settings", name):
		frappe.delete_doc("Dinext Workspace Settings", name, force=True, ignore_permissions=True)


def _scratch_hub_settings(test_case):
	name = f"Test Hub {random_string(8)}"
	doc = ensure_workspace_settings(name)
	test_case.addCleanup(_delete_scratch_hub_settings, name)
	return doc


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

	def test_omit_replaced_workspaces_drops_home(self):
		pages = omit_replaced_workspaces(
			[
				{"name": "Home", "title": "Home"},
				{"name": "Dinext", "title": "Dinext"},
				{"name": "Settings", "title": "Settings"},
			]
		)
		self.assertEqual([page["name"] for page in pages], ["Dinext", "Settings"])

	def test_sidebar_wrapper_omits_home(self):
		from unittest.mock import patch

		payload = {
			"pages": [
				{"name": "Home", "title": "Home"},
				{"name": DINEXT_WORKSPACE, "title": DINEXT_WORKSPACE},
			],
			"has_access": True,
		}
		with patch("frappe.desk.desktop.get_workspace_sidebar_items", return_value=payload):
			result = get_workspace_sidebar_items()
		names = {page["name"] for page in result["pages"]}
		self.assertNotIn("Home", names)
		self.assertIn(DINEXT_WORKSPACE, names)

	def test_configure_keeps_home_hidden_in_database(self):
		configure_workspace_menu()
		if not frappe.db.exists("Workspace", "Home"):
			self.skipTest("ERPNext Home workspace is not installed")
		ws = frappe.db.get_value(
			"Workspace",
			"Home",
			["name", "title", "is_hidden"],
			as_dict=True,
		)
		self.assertEqual(ws.name, "Home")
		self.assertEqual(ws.title, "Home")
		self.assertEqual(ws.is_hidden, 1)

	def test_home_slug_redirects_to_dinext(self):
		path = Path(frappe.get_app_path("dinext_common")) / "public" / "js" / "workspace_slug_redirects.js"
		script = path.read_text()
		self.assertIn('home: "dinext"', script)
		self.assertIn('Home: "Dinext"', script)

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
				"first_name": "Administrator",
				"last_name": "",
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
				"first_name": "Administrator",
				"last_name": "",
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
				"first_name": "Administrator",
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
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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

		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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
		original = _get_route

		def fake_route(element_type, target):
			if element_type == "DocType" and target == "Domain Settings":
				return None
			return original(element_type, target)

		with patch("dinext_common.workspace_hub._get_route", side_effect=fake_route):
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
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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
				"first_name": "Administrator",
				"last_name": "",
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
				"/app/query-report/Database%20Storage%20Usage%20By%20Tables",
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
		self.assertEqual(
			blocks["Dinext Hub"]["html"],
			'<div class="dinext-workspace-hub" data-settings-name="Dinext"></div>',
		)
		self.assertEqual(
			blocks["Dinext Settings Hub"]["html"],
			'<div class="dinext-workspace-hub" data-settings-name="Settings"></div>',
		)
		for name in ("Dinext Hub", "Dinext Settings Hub"):
			script = blocks[name]["script"]
			self.assertIn("frappe.require", script)
			self.assertIn("/assets/dinext_common/js/workspace_hub.js", script)
			self.assertIn("dinext_common.workspace_hub.mount(root_element)", script)
			self.assertNotIn("svg.style.width", script)

		js_path = Path(frappe.get_app_path("dinext_common")) / "public" / "js" / "workspace_hub.js"
		css_path = Path(frappe.get_app_path("dinext_common")) / "public" / "css" / "workspace_hub.css"
		script = js_path.read_text()
		style = css_path.read_text()
		self.assertIn("frappe.set_route", script)
		self.assertIn("navigate_route", script)
		self.assertIn("/assets/frappe/icons/timeless/icons.svg", script)
		self.assertIn("get_workspace_hub", script)
		self.assertIn("frappe.new_doc", script)
		self.assertIn("make_section_lists", script)
		self.assertIn("make_create_bar", script)
		self.assertIn("make_column_heading", script)
		self.assertIn("make_type_badge", script)
		self.assertIn("section.lists", script)
		self.assertIn("lists.attention", script)
		self.assertIn("make_page_lists", script)
		self.assertIn("make_page_row", script)
		self.assertIn("make_page_chip", script)
		self.assertIn("dinext-workspace-hub__page-chip", script)
		self.assertIn("dinext-workspace-hub__page-rows", script)
		self.assertIn("dinext-workspace-hub__create-buttons", script)
		self.assertIn("dinext-workspace-hub__create-btn", script)
		self.assertIn("dinext-workspace-hub__record", script)
		self.assertIn('make_icon("add"', script)
		self.assertIn("is_font_icon", script)
		self.assertIn("fa ", script)
		self.assertIn("aria-label", script)
		self.assertNotIn("make_create_column", script)
		self.assertNotIn("es-line-time", script)
		self.assertNotIn("es-line-alert-triangle", script)
		self.assertNotIn("__('Quick Create')", script)
		self.assertNotIn("__('No records')", script)
		self.assertNotIn("list-empty", script)
		self.assertNotIn("action.icon", script)
		self.assertNotIn("make_doctype_block", script)
		self.assertIn("frappe.route_history", script)
		self.assertIn("frequently_visited_links", script)
		self.assertIn("show_frequent_pages", script)
		self.assertIn("show_recent_pages", script)
		self.assertIn("Frequent Pages", script)
		self.assertIn("Recent Pages", script)
		self.assertLess(script.index("Recent Pages"), script.index("Frequent Pages"))
		self.assertIn("allowed_workspaces", script)
		self.assertIn("title_field", script)
		self.assertIn("get_value", script)
		self.assertIn('classList.add("dinext-workspace-hub__page-chip-icon")', script)
		self.assertIn("frappe.router.on", script)
		self.assertIn("refresh_connected_hubs", script)
		self.assertIn("card-border-1", script)
		self.assertNotIn('__("{0} Workspace"', script)
		self.assertNotIn("Recently Opened", script)
		self.assertNotIn("recent_doctypes", script)
		self.assertNotIn("get_document_titles", script)
		self.assertNotIn("recent_from_route_history", script)
		self.assertNotIn("dropdown-toggle", script)
		self.assertNotIn("__('My Items')", script)
		self.assertNotIn("dinext-workspace-hub__personal-header", script)
		self.assertNotIn("label.className = 'dinext-workspace-hub__type-label'", script)
		self.assertNotIn("dinext-workspace-hub__chip", script)
		self.assertNotIn("dinext-workspace-hub__chip-label", script)
		self.assertIn("--dinext-hub-card-columns", script)
		self.assertIn("Math.min(columns, Math.max(1, items.length))", script)
		self.assertIn("card_columns", script)
		self.assertIn("?v=", script)
		self.assertIn(".dinext-workspace-hub__card-icon .icon", style)
		self.assertIn(
			".dinext-workspace-hub__card {\n\tdisplay: flex;\n\tgap: 0.75rem;\n\talign-items: flex-start;\n\tpadding: 1rem;\n\tborder: 1px solid var(--dark-border-color, var(--border-color));",
			style,
		)
		self.assertIn(".dinext-workspace-hub__card:focus-visible", style)
		self.assertIn(
			".dinext-workspace-hub__card:hover,\n.dinext-workspace-hub__card:focus-visible {\n\tborder-color: var(--border-primary, var(--btn-primary));\n\tbox-shadow: 0 0 0 1px var(--border-primary, var(--btn-primary));",
			style,
		)
		self.assertNotIn(
			".dinext-workspace-hub__card:hover {\n\tborder-color: var(--primary);",
			style,
		)
		self.assertIn(
			".dinext-workspace-hub__card:hover .dinext-workspace-hub__card-title",
			style,
		)
		self.assertIn("font-size: var(--text-tiny, 11px)", style)
		self.assertIn(".dinext-workspace-hub__lists", style)
		self.assertIn(".dinext-workspace-hub__pages", style)
		self.assertIn(".dinext-workspace-hub__page-rows", style)
		self.assertIn(".dinext-workspace-hub__page-chip:hover", style)
		self.assertIn("var(--border-radius-full, 999px)", style)
		self.assertIn("overflow: visible", style)
		self.assertIn("repeat(auto-fit, minmax(min(100%, 16rem), 1fr))", style)
		self.assertIn(".dinext-workspace-hub__list-items > li", style)
		self.assertIn(".dinext-workspace-hub__chip:hover", style)
		self.assertIn(".dinext-workspace-hub__create-btn:hover", style)
		self.assertIn(".dinext-workspace-hub__record", style)
		self.assertIn("gap: 0.12rem", style)
		self.assertIn("padding: 0.05rem 0", style)
		self.assertIn("var(--border-primary, var(--btn-primary))", style)
		self.assertIn("0 0 0 1px var(--border-primary, var(--btn-primary))", style)
		self.assertIn("var(--dark-border-color, var(--border-color))", style)
		self.assertIn("text-transform: none", style)
		self.assertIn(".dinext-workspace-hub__type-badge", style)
		self.assertIn(".dinext-workspace-hub__create-buttons", style)
		self.assertIn(".dinext-workspace-hub__type-icon .fa", style)
		self.assertIn(".dinext-workspace-hub__type-icon .octicon", style)
		self.assertIn("--dinext-hub-card-columns", style)
		self.assertIn("min(2, var(--dinext-hub-card-columns, 4))", style)
		self.assertNotIn("repeat(2, minmax(0, 1fr))", style)
		self.assertNotIn("repeat(auto-fit, minmax(220px, 1fr))", style)
		self.assertNotIn(".dinext-workspace-hub__doctypes", style)
		self.assertNotIn(".dinext-workspace-hub__create-menu", style)
		self.assertNotIn("repeat(5, minmax(0, 1fr))", style)
		self.assertNotIn(".dinext-workspace-hub__list-title-icon", style)
		self.assertNotIn("max-width: 5.5rem", style)
		self.assertNotIn(
			".dinext-workspace-hub__personal { margin-top: .75rem; border: 1px solid var(--border-color)",
			style,
		)

	def test_named_settings_records_are_isolated(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		register_hub_items(
			[
				{
					"section": "Isolation",
					"element_type": "Workspace",
					"target": DINEXT_WORKSPACE,
					"label": "Only on Dinext",
					"enabled": 1,
				}
			],
			source_app="dinext_common",
			settings_name=DINEXT_HUB_SETTINGS,
		)
		dinext_labels = {
			card["label"] for section in get_workspace_hub(DINEXT_HUB_SETTINGS)["sections"] for card in section["items"]
		}
		settings_labels = {
			card["label"]
			for section in get_workspace_hub(SETTINGS_HUB_SETTINGS)["sections"]
			for card in section["items"]
		}
		self.assertIn("Only on Dinext", dinext_labels)
		self.assertNotIn("Only on Dinext", settings_labels)

	def test_register_hub_items_can_target_settings_record(self):
		configure_workspace_menu()
		_clear_hub_settings(self, name=SETTINGS_HUB_SETTINGS)
		register_hub_items(
			[
				{
					"section": "Workspaces",
					"element_type": "Workspace",
					"target": DINEXT_WORKSPACE,
					"label": "Extra Settings Card",
					"description": "Added by another app.",
					"icon": "setting",
					"enabled": 1,
				}
			],
			source_app="dinext_common",
			settings_name=SETTINGS_HUB_SETTINGS,
		)
		labels = {
			card["label"] for section in get_settings_hub()["sections"] for card in section["items"]
		}
		self.assertIn("Extra Settings Card", labels)
		dinext_labels = {
			card["label"] for section in get_dinext_hub()["sections"] for card in section["items"]
		}
		self.assertNotIn("Extra Settings Card", dinext_labels)

	def test_unknown_settings_name_returns_empty_hub(self):
		configure_workspace_menu()
		payload = get_workspace_hub("Does Not Exist")
		self.assertEqual(
			payload,
			{
				"show_frequent_pages": False,
				"show_recent_pages": False,
				"page_list_limit": 5,
				"sections": [],
			},
		)

	def test_standard_settings_records_exist_after_configure(self):
		configure_workspace_menu()
		self.assertTrue(frappe.db.exists("Dinext Workspace Settings", DINEXT_HUB_SETTINGS))
		self.assertTrue(frappe.db.exists("Dinext Workspace Settings", SETTINGS_HUB_SETTINGS))
		settings = frappe.get_doc("Dinext Workspace Settings", SETTINGS_HUB_SETTINGS)
		self.assertEqual({row.role for row in settings.roles}, set(SETTINGS_ROLES))
		self.assertEqual(settings.settings_name, SETTINGS_HUB_SETTINGS)
		self.assertFalse(settings.show_frequent_pages)
		self.assertFalse(settings.show_recent_pages)
		settings_payload = get_settings_hub()
		self.assertFalse(settings_payload["show_frequent_pages"])
		self.assertFalse(settings_payload["show_recent_pages"])

	def test_settings_hub_page_lists_stay_disabled_after_reconfigure(self):
		configure_workspace_menu()
		settings = frappe.get_doc("Dinext Workspace Settings", SETTINGS_HUB_SETTINGS)
		settings.show_frequent_pages = 1
		settings.show_recent_pages = 1
		settings.save(ignore_permissions=True)
		dinext = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
		dinext.show_frequent_pages = 1
		dinext.show_recent_pages = 1
		dinext.save(ignore_permissions=True)
		configure_workspace_menu()
		settings.reload()
		dinext.reload()
		self.assertFalse(settings.show_frequent_pages)
		self.assertFalse(settings.show_recent_pages)
		self.assertTrue(dinext.show_frequent_pages)
		self.assertTrue(dinext.show_recent_pages)

	def test_settings_sections_use_five_card_columns(self):
		configure_workspace_menu()
		settings = frappe.get_doc("Dinext Workspace Settings", SETTINGS_HUB_SETTINGS)
		by_section = {row.section: int(row.card_columns) for row in settings.sections}
		self.assertEqual(by_section.get("Workspaces"), SETTINGS_SECTION_CARD_COLUMNS)
		self.assertEqual(by_section.get("Configuration"), SETTINGS_SECTION_CARD_COLUMNS)
		for section in get_settings_hub()["sections"]:
			self.assertEqual(section["card_columns"], SETTINGS_SECTION_CARD_COLUMNS)

	def test_hub_card_columns_default_without_section_row(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		register_hub_items(
			[
				{
					"section": "No Section Row",
					"element_type": "Workspace",
					"target": DINEXT_WORKSPACE,
					"label": "Default columns card",
					"enabled": 1,
				}
			],
			source_app="dinext_common",
		)
		section = next(
			row for row in get_dinext_hub()["sections"] if row["label"] == "No Section Row"
		)
		self.assertEqual(section["card_columns"], DEFAULT_SECTION_CARD_COLUMNS)

	def test_register_hub_sections_preserves_card_columns(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		register_hub_sections(
			[{"section": "My Work", "list_limit": 5, "card_columns": 3}],
			source_app="dinext_projects",
		)
		register_hub_sections(
			[{"section": "My Work", "list_limit": 9, "card_columns": 6}],
			source_app="dinext_kanban",
		)
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
		self.assertEqual(int(settings.sections[0].card_columns), 3)

	def test_hub_payload_has_typed_section_keys(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		register_hub_items(
			[
				{
					"section": "Typed Contract",
					"element_type": "Workspace",
					"target": DINEXT_WORKSPACE,
					"label": "Typed card",
					"description": "Contract keys",
					"icon": "organization",
					"enabled": 1,
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		previous = dict(frappe.form_dict)

		def restore_form_dict():
			frappe.form_dict.clear()
			frappe.form_dict.update(previous)

		self.addCleanup(restore_form_dict)
		frappe.form_dict.clear()
		frappe.form_dict["settings_name"] = settings.name
		payload = get_workspace_hub()
		self.assertEqual(
			set(payload.keys()),
			{"sections", "show_frequent_pages", "show_recent_pages", "page_list_limit"},
		)
		self.assertTrue(payload["sections"])
		self.assertTrue(
			any(card["label"] == "Typed card" for section in payload["sections"] for card in section["items"])
		)
		for section in payload["sections"]:
			self.assertEqual(
				set(section.keys()),
				{"label", "items", "lists", "list_limit", "card_columns"},
			)
			for card in section["items"]:
				self.assertEqual(set(card.keys()), {"label", "description", "icon", "route"})
		ignored_form_input = get_workspace_hub("Does Not Exist")
		self.assertEqual(ignored_form_input["sections"], [])

	def test_ensure_workspace_settings_creates_named_record(self):
		name = f"Test Hub {random_string(8)}"
		self.addCleanup(
			lambda: frappe.db.exists("Dinext Workspace Settings", name)
			and frappe.delete_doc("Dinext Workspace Settings", name, force=True, ignore_permissions=True)
		)
		self.assertFalse(frappe.db.exists("Dinext Workspace Settings", name))
		doc = ensure_workspace_settings(name)
		self.assertIsNotNone(doc)
		self.assertEqual(doc.name, name)
		self.assertEqual(doc.settings_name, name)
		self.assertTrue(frappe.db.exists("Dinext Workspace Settings", name))
		self.assertNotEqual(name, DINEXT_HUB_SETTINGS)
		self.assertNotEqual(name, SETTINGS_HUB_SETTINGS)

	def test_settings_bootstrap_preserves_admin_edits(self):
		configure_workspace_menu()
		_clear_hub_settings(self, name=SETTINGS_HUB_SETTINGS)
		ensure_default_dinext_hub_settings()
		settings = frappe.get_doc("Dinext Workspace Settings", SETTINGS_HUB_SETTINGS)
		users = next(row for row in settings.items if row.target == "Users")
		users.label = "Admin Users Label"
		users.description = "Admin description"
		settings.save(ignore_permissions=True)

		ensure_default_dinext_hub_settings()
		settings.reload()
		users = next(row for row in settings.items if row.target == "Users")
		self.assertEqual(users.label, "Admin Users Label")
		self.assertEqual(users.description, "Admin description")

	def test_legacy_single_children_reparent_and_restore_from_dump(self):
		from dinext_common.patches.v1_0.migrate_workspace_settings_single import (
			_reparent_legacy_children,
			_restore_dump_if_empty,
		)
		from dinext_common.patches.v1_0.workspace_settings_migrate import LEGACY_PARENT, dump_path

		configure_workspace_menu()
		_clear_hub_settings(self)
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
		settings.append(
			"items",
			{
				"section": "Legacy",
				"element_type": "Workspace",
				"target": DINEXT_WORKSPACE,
				"label": "Migrated card",
				"description": "Kept from Single",
				"icon": "organization",
				"enabled": 1,
			},
		)
		settings.save(ignore_permissions=True)
		row_name = settings.items[0].name
		frappe.db.set_value("Dinext Workspace Settings Item", row_name, "parent", LEGACY_PARENT, update_modified=False)

		dinext = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
		_reparent_legacy_children(dinext)
		self.assertEqual(
			frappe.db.get_value("Dinext Workspace Settings Item", row_name, "parent"),
			DINEXT_HUB_SETTINGS,
		)

		_clear_hub_settings(self)
		path = dump_path()
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(
			json.dumps(
				{
					"items": [
						{
							"idx": 1,
							"section": "Legacy",
							"element_type": "Workspace",
							"target": DINEXT_WORKSPACE,
							"label": "Dump restored card",
							"description": "From dump file",
							"icon": "organization",
							"enabled": 1,
						}
					],
					"sections": [],
					"doctype_items": [],
				}
			),
			encoding="utf-8",
		)
		self.addCleanup(lambda: path.exists() and path.unlink())
		dinext = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
		_restore_dump_if_empty(dinext)
		dinext.reload()
		self.assertEqual(dinext.items[0].label, "Dump restored card")
		self.assertEqual(dinext.items[0].description, "From dump file")

	def test_register_sections_and_doctype_items_merge(self):
		configure_workspace_menu()
		_clear_hub_settings(self)
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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
		self.assertNotIn("show_recently_opened", lists)
		self.assertNotIn("recent_doctypes", lists)
		self.assertNotIn("recent", lists)
		self.assertTrue(lists["show_assigned"])
		self.assertTrue(lists["show_liked"])
		self.assertTrue(lists["show_attention"])
		self.assertEqual(section["list_limit"], 5)
		self.assertEqual(lists["list_limit"], 5)
		self.assertIn("show_frequent_pages", payload)
		self.assertIn("show_recent_pages", payload)
		self.assertEqual(payload["page_list_limit"], 5)

		create_doctypes = {row["doctype"] for row in lists["create_actions"]}
		if frappe.has_permission("Task", "create"):
			self.assertIn("Task", create_doctypes)
		if issue_registered and frappe.has_permission("Issue", "create"):
			self.assertIn("Issue", create_doctypes)
		self.assertEqual(len(lists["create_actions"]), len(create_doctypes))

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
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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
		settings = frappe.get_doc("Dinext Workspace Settings", DINEXT_HUB_SETTINGS)
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

	def test_page_list_flags_ignore_doctype_recently_opened(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		self.assertTrue(settings.meta.has_field("show_frequent_pages"))
		self.assertTrue(settings.meta.has_field("show_recent_pages"))
		self.assertFalse(
			frappe.get_meta("Dinext Workspace Settings DocType").has_field("show_recently_opened")
		)

		register_hub_sections(
			[{"section": "Page Lists", "list_limit": 2}],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		register_hub_doctype_items(
			[
				{
					"section": "Page Lists",
					"document_type": "Note",
					"show_recently_opened": 1,
					"show_assigned": 1,
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)

		settings.reload()
		self.assertEqual(len(settings.doctype_items), 1)
		payload = get_workspace_hub(settings.name)
		self.assertTrue(payload["show_frequent_pages"])
		self.assertTrue(payload["show_recent_pages"])
		self.assertEqual(payload["page_list_limit"], 5)
		section = next(s for s in payload["sections"] if s["label"] == "Page Lists")
		lists = section["lists"]
		self.assertNotIn("show_recently_opened", lists)
		self.assertNotIn("recent_doctypes", lists)
		self.assertNotIn("recent", lists)
		self.assertTrue(lists["show_assigned"])

	def _insert_public_note(self, title):
		note = frappe.get_doc({"doctype": "Note", "title": title, "public": 1})
		note.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Note", note.name, force=True, ignore_permissions=True))
		return note

	def _assign_note(self, note):
		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": f"hub assign {note.name}",
				"allocated_to": frappe.session.user,
				"reference_type": "Note",
				"reference_name": note.name,
				"status": "Open",
			}
		)
		todo.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("ToDo", todo.name, force=True, ignore_permissions=True))
		return todo

	def test_parse_list_filter_and_invalid(self):
		parsed = parse_list_filter(
			'[["Note","public","=",1,false]]',
			"Note",
		)
		self.assertEqual(parsed, [["public", "=", 1]])
		self.assertEqual(parse_list_filter("", "Note"), [])
		self.assertIsNone(parse_list_filter("{not-json", "Note"))

	def test_assigned_and_liked_apply_list_filter(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		keep = self._insert_public_note(f"hub-keep-{random_string(6)}")
		drop = self._insert_public_note(f"hub-drop-{random_string(6)}")
		self._assign_note(keep)
		self._assign_note(drop)
		for note in (keep, drop):
			frappe.db.set_value("Note", note.name, "_liked_by", json.dumps([frappe.session.user]))

		register_hub_sections(
			[{"section": "Filter Lists", "list_limit": 5}],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		register_hub_doctype_items(
			[
				{
					"section": "Filter Lists",
					"document_type": "Note",
					"show_assigned": 1,
					"show_liked": 1,
					"show_attention": 1,
					"attention_filter": [["Note", "public", "=", 1]],
					"list_filter": [["Note", "title", "like", f"%{keep.title}%"]],
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)

		payload = get_workspace_hub(settings.name)
		section = next(s for s in payload["sections"] if s["label"] == "Filter Lists")
		lists = section["lists"]
		assigned_names = {row["name"] for row in lists["assigned"]}
		liked_names = {row["name"] for row in lists["liked"]}
		attention_names = {row["name"] for row in lists["attention"]}
		self.assertIn(keep.name, assigned_names)
		self.assertNotIn(drop.name, assigned_names)
		self.assertIn(keep.name, liked_names)
		self.assertNotIn(drop.name, liked_names)
		self.assertIn(keep.name, attention_names)
		self.assertIn(drop.name, attention_names)

	def test_empty_list_filter_does_not_narrow_assigned(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		note = self._insert_public_note(f"hub-empty-filter-{random_string(6)}")
		self._assign_note(note)
		register_hub_sections(
			[{"section": "Empty Filter", "list_limit": 5}],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		register_hub_doctype_items(
			[
				{
					"section": "Empty Filter",
					"document_type": "Note",
					"show_assigned": 1,
					"list_filter": "",
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		payload = get_workspace_hub(settings.name)
		section = next(s for s in payload["sections"] if s["label"] == "Empty Filter")
		self.assertIn(note.name, {row["name"] for row in section["lists"]["assigned"]})

	def test_invalid_list_filter_does_not_break_hub(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		note = self._insert_public_note(f"hub-bad-filter-{random_string(6)}")
		self._assign_note(note)
		register_hub_sections(
			[{"section": "Bad Filter", "list_limit": 5}],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		register_hub_doctype_items(
			[
				{
					"section": "Bad Filter",
					"document_type": "Note",
					"show_assigned": 1,
					"list_filter": "{not-json",
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		payload = get_workspace_hub(settings.name)
		section = next(s for s in payload["sections"] if s["label"] == "Bad Filter")
		self.assertTrue(section["lists"]["show_assigned"])
		self.assertIn(note.name, {row["name"] for row in section["lists"]["assigned"]})

	def test_register_doctype_items_preserves_admin_list_filter(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		register_hub_doctype_items(
			[
				{
					"section": "Preserve Filter",
					"document_type": "Note",
					"show_assigned": 1,
					"list_filter": [["public", "=", 1]],
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		settings.reload()
		settings.doctype_items[0].list_filter = '[["public","=",0]]'
		settings.save(ignore_permissions=True)
		register_hub_doctype_items(
			[
				{
					"section": "Preserve Filter",
					"document_type": "Note",
					"show_assigned": 1,
					"list_filter": [["public", "=", 1]],
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		settings.reload()
		self.assertEqual(len(settings.doctype_items), 1)
		self.assertEqual(settings.doctype_items[0].list_filter, '[["public","=",0]]')

	def test_register_doctype_items_backfills_empty_list_filter_and_enables_flags(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		register_hub_doctype_items(
			[
				{
					"section": "Backfill Filter",
					"document_type": "Note",
					"show_assigned": 0,
					"show_quick_create": 0,
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		register_hub_doctype_items(
			[
				{
					"section": "Backfill Filter",
					"document_type": "Note",
					"show_assigned": 1,
					"show_quick_create": 1,
					"list_filter": [["public", "=", 1]],
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		settings.reload()
		self.assertEqual(len(settings.doctype_items), 1)
		self.assertTrue(settings.doctype_items[0].show_assigned)
		self.assertTrue(settings.doctype_items[0].show_quick_create)
		self.assertIn("public", settings.doctype_items[0].list_filter)

	def test_register_doctype_items_does_not_disable_flags_from_payload(self):
		configure_workspace_menu()
		settings = _scratch_hub_settings(self)
		register_hub_doctype_items(
			[
				{
					"section": "Keep Flags",
					"document_type": "Note",
					"show_assigned": 1,
					"show_quick_create": 1,
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		register_hub_doctype_items(
			[
				{
					"section": "Keep Flags",
					"document_type": "Note",
					"show_assigned": 0,
					"show_quick_create": 0,
				}
			],
			source_app="dinext_common",
			settings_name=settings.name,
		)
		settings.reload()
		self.assertTrue(settings.doctype_items[0].show_assigned)
		self.assertTrue(settings.doctype_items[0].show_quick_create)

