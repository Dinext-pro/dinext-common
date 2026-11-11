# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from dinext_common.setup.hub_catalog import (
	ensure_workspace_settings,
	register_hub_doctype_items,
	register_hub_items,
	register_hub_sections,
)

REFERENCE = json.loads(
	(Path(__file__).parent / "fixtures" / "workspace_install_defaults.json").read_text()
)


class TestHubCatalogDefaults(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.settings = ensure_workspace_settings(f"Test install defaults {random_string(8)}")
		self.addCleanup(
			frappe.delete_doc, "Dinext Workspace Settings", self.settings.name,
			force=True, ignore_permissions=True,
		)
		selector = patch("dinext_common.setup.hub_catalog.ensure_workspace_settings", return_value=self.settings)
		selector.start()
		self.addCleanup(selector.stop)

	def test_new_cards_follow_reference_order_in_reverse_registration(self):
		for item in reversed(REFERENCE["items"]):
			register_hub_items([item], source_app=item["source_app"])
		self.settings.reload()
		self.assertEqual(
			[(r.element_type, r.target) for r in self.settings.items],
			[(r["element_type"], r["target"]) for r in REFERENCE["items"]],
		)
		for item in REFERENCE["items"]:
			register_hub_items([item], source_app=item["source_app"])
		self.assertEqual(len(self.settings.items), 10)

	def test_registration_retains_existing_custom_order_and_edits(self):
		cards = deepcopy(REFERENCE["items"])
		register_hub_items([cards[7], cards[0]])
		self.settings.items = list(reversed(self.settings.items))
		for idx, row in enumerate(self.settings.items, 1):
			row.idx = idx
		self.settings.items[0].label = "Custom task entry"
		self.settings.items[0].enabled = 0
		self.settings.save(ignore_permissions=True)
		before = [r.target for r in self.settings.items]
		register_hub_items(cards)
		self.settings.reload()
		self.assertEqual([r.target for r in self.settings.items if r.target in before], before)
		row = next(r for r in self.settings.items if r.target == before[0])
		self.assertEqual(row.label, "Custom task entry")
		self.assertFalse(row.enabled)

	def test_settings_and_custom_cards_retain_append_order(self):
		cards = list(reversed(REFERENCE["items"]))
		register_hub_items(cards, settings_name="Settings")
		self.assertEqual([r.target for r in self.settings.items], [r["target"] for r in cards])
		custom = {"section": "Custom", "element_type": "URL", "target": "https://example.com"}
		register_hub_items([custom, {**custom, "target": "https://example.org"}])
		self.assertEqual([r.target for r in self.settings.items[-2:]], ["https://example.com", "https://example.org"])

	def test_duplicate_input_is_inserted_once(self):
		card = REFERENCE["items"][0]
		register_hub_items([card, card])
		self.settings.reload()
		self.assertEqual(len(self.settings.items), 1)

	def test_new_sections_follow_reference_order(self):
		register_hub_sections(reversed(REFERENCE["sections"]))
		self.assertEqual([r.section for r in self.settings.sections], ["My Work", "Project Management"])

	def test_projects_adopts_unchanged_kanban_fallback(self):
		payload = self._task_with_fallback()
		register_hub_doctype_items([payload["fallback_defaults"]], source_app="dinext_kanban")
		register_hub_doctype_items([payload], source_app="dinext_projects")
		self.settings.reload()
		self.assertEqual(len(self.settings.doctype_items), 1)
		row = self.settings.doctype_items[0]
		self.assertEqual(row.source_app, "dinext_projects")
		self.assertTrue(row.show_liked)
		self.assertEqual(json.loads(row.list_filter), json.loads(REFERENCE["doctype_items"][1]["list_filter"]))

	def test_projects_adoption_preserves_edited_flags_and_empty_filter_on_replay(self):
		payload = self._task_with_fallback()
		register_hub_doctype_items([payload["fallback_defaults"]], source_app="dinext_kanban")
		row = self.settings.doctype_items[0]
		for field in ("enabled", "show_quick_create", "show_assigned", "show_attention"):
			row.set(field, 0)
		row.list_filter = ""
		row.attention_filter = '[["Task", "priority", "=", "High"]]'
		self.settings.save(ignore_permissions=True)
		for _ in range(2):
			register_hub_doctype_items([payload], source_app="dinext_projects")
		self.settings.reload()
		self.assertEqual(len(self.settings.doctype_items), 1)
		row = self.settings.doctype_items[0]
		for field in ("enabled", "show_quick_create", "show_assigned", "show_attention"):
			self.assertFalse(row.get(field), field)
		self.assertFalse(row.list_filter)
		self.assertEqual(json.loads(row.attention_filter), [["Task", "priority", "=", "High"]])

	def test_new_issue_precedes_adopted_task_without_reordering_existing_rows(self):
		payload = self._task_with_fallback()
		register_hub_doctype_items([payload["fallback_defaults"]], source_app="dinext_kanban")
		register_hub_doctype_items([REFERENCE["doctype_items"][0], payload], source_app="dinext_projects")
		self.settings.reload()
		self.assertEqual([r.document_type for r in self.settings.doctype_items], ["Issue", "Task"])

	def _task_with_fallback(self):
		payload = deepcopy(REFERENCE["doctype_items"][1])
		fallback = {**payload, "show_liked": 0}
		fallback.pop("source_app")
		payload["fallback_source_app"] = "dinext_kanban"
		payload["fallback_defaults"] = fallback
		return payload
