import csv
import json
import re
import unittest
from pathlib import Path


class TestWorkspaceLocalization(unittest.TestCase):
	def test_export_resolves_translated_labels_and_links(self):
		app = Path(__file__).resolve().parents[1]
		documents = {
			"dinext_common": ("My Approvals", "my_approvals", 8),
			"dinext_timesheets": ("My Timesheets", "my_timesheets", 20),
		}
		name, slug, card_count = documents[app.name]
		path = app / app.name / "workspace" / slug / f"{slug}.json"
		self.assertTrue(path.is_file(), f"Expected English Workspace export at {path}")
		workspace = json.loads(path.read_text())
		with (app / "translations" / "ru.csv").open() as stream:
			translations = {row[0]: row[1] for row in csv.reader(stream) if len(row) > 1 and row[1]}
		self.assertEqual([workspace[k] for k in ("name", "label", "title")], [name] * 3)
		self.assertEqual(len(workspace["number_cards"]), card_count)
		widgets = {
			"number_card": ("number_cards", "number_card_name"),
			"chart": ("charts", "chart_name"),
			"shortcut": ("shortcuts", "shortcut_name"),
		}
		for block in json.loads(workspace["content"]):
			kind, data = block["type"], block["data"]
			if kind == "header":
				label = re.sub(r"<[^>]+>", "", data["text"])
			elif kind in widgets:
				table, field = widgets[kind]
				label = data[field]
				self.assertEqual(sum(row["label"] == label for row in workspace[table]), 1, label)
				russian = translations[label]
				self.assertEqual(sum(translations[row["label"]] == russian for row in workspace[table]), 1, label)
			else:
				continue
			self.assertTrue(label.isascii(), label)
			self.assertRegex(translations[label], r"[А-Яа-яЁё]")

	def test_saving_the_visible_layout_does_not_delete_the_hidden_control_section(self):
		from types import SimpleNamespace
		from unittest.mock import patch

		from dinext_common.setup import workspace

		previous = [
			{"id": "approvals-header", "type": "header", "data": {"text": "My Approvals"}},
			{"id": "control-header", "type": "header", "data": {"text": "Approval Control"}},
			{"id": "control-open", "type": "number_card", "data": {"number_card_name": "Open Approval Rounds"}},
		]
		edited = [
			previous[0],
			{"id": "local-heading", "type": "header", "data": {"text": "Site Guide"}},
		]
		doc = SimpleNamespace(
			name="My Approvals", content=json.dumps(edited),
			get_doc_before_save=lambda: SimpleNamespace(content=json.dumps(previous)),
		)
		with (
			patch("frappe.get_roles", return_value=["Workspace Manager"]),
			patch("dinext_common.workflow_approval.permissions.get_monitorable_workflows", return_value=[]),
		):
			workspace.preserve_approval_control_blocks(doc)
		self.assertEqual(json.loads(doc.content), [*edited, *previous[1:]])
