"""Validate Workflow choices and their union with the existing hook."""

import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from dinext_common.workflow_approval import engine, exclusions


def field(name, kind="Data", **values):
	return {"fieldname": name, "fieldtype": kind, **values}


class TestWorkflowFingerprintSettings(unittest.TestCase):
	def setUp(self):
		self.meta = {
			"Source": SimpleNamespace(
				fields=[
					field("title"),
					field("amount", "Float"),
					field("other", "Table", options="Child"),
					field("table", "Table", options="Child"),
					field("workflow_state"),
					field("status"),
					field("secret", "Password"),
					field("virtual", virtual=1),
					field("non_db", non_db=1),
					field("heading", "Section Break"),
					field("modified"),
					field("hidden", is_virtual=1),
				]
			),
			"Child": SimpleNamespace(
				fields=[
					field("hours", "Float"),
					field("description"),
					field("utilized_hours", "Float"),
					field("name"),
					field("owner"),
					field("secret", "Password"),
					field("calculated", virtual=1),
				]
			),
		}
		self.workflow = {
			"document_type": "Source",
			"workflow_state_field": "workflow_state",
			"states": [{"update_field": "status", "state": "Pending"}],
			exclusions.EXCLUSIONS_FIELD: [{"field_path": "table.utilized_hours"}],
		}
		self.enterContext(patch.object(exclusions.frappe, "get_meta", side_effect=lambda dt: self.meta[dt]))
		self.enterContext(patch.object(exclusions, "_", side_effect=lambda value: value))

	def test_catalog_contains_only_persisted_paths_and_whole_tables(self):
		self.assertEqual(
			exclusions.selectable_paths(self.workflow),
			{
				"title",
				"amount",
				"table",
				"other",
				"table.hours",
				"table.description",
				"table.utilized_hours",
				"other.hours",
				"other.description",
				"other.utilized_hours",
			},
		)

	def test_invalid_duplicate_empty_and_wrong_doctype_paths_are_rejected(self):
		for paths in [
			["missing"],
			["table.missing"],
			["table.hours.more"],
			["amount", "amount"],
			[""],
			["modified"],
			["secret"],
			["table.name"],
			["status"],
			["workflow_state"],
		]:
			with self.subTest(paths=paths), self.assertRaises(ValueError):
				exclusions.validate_exclusions(
					{**self.workflow, exclusions.EXCLUSIONS_FIELD: [{"field_path": path} for path in paths]}
				)
		changed = {**self.workflow, "document_type": "Child"}
		with self.assertRaises(ValueError):
			exclusions.validate_exclusions(changed)
		self.assertEqual(changed[exclusions.EXCLUSIONS_FIELD][0]["field_path"], "table.utilized_hours")

	def test_empty_config_and_trimmed_values(self):
		exclusions.validate_exclusions({"document_type": "Unknown"})
		doc = deepcopy(self.workflow)
		doc[exclusions.EXCLUSIONS_FIELD][0]["field_path"] = " table.utilized_hours "
		exclusions.validate_exclusions(doc)
		self.assertEqual(exclusions.configured_exclusions(doc), {"table.utilized_hours"})

	def test_union_with_hooks_is_scoped_and_independent_of_duplicates(self):
		with patch.object(
			engine.frappe,
			"get_hooks",
			return_value=[
				{"Source": ["title", "table.utilized_hours"]},
				{"Other Source": ["amount"]},
			],
		):
			self.assertEqual(
				engine._fingerprint_exclusions("Source", self.workflow), {"title", "table.utilized_hours"}
			)
			other = {**self.workflow, exclusions.EXCLUSIONS_FIELD: [{"field_path": "amount"}]}
			self.assertEqual(
				engine._fingerprint_exclusions("Source", other), {"title", "amount", "table.utilized_hours"}
			)
			self.assertEqual(engine._fingerprint_exclusions("Other Source"), {"amount"})

	def test_setting_preserves_non_excluded_business_changes(self):
		values = {
			"doctype": "Source",
			"workflow_state": "Pending",
			"title": "Work",
			"amount": 8,
			"table": [{"hours": 8, "description": "Work", "utilized_hours": 8}],
			"other": [{"hours": 8, "description": "Work", "utilized_hours": 8}],
		}

		def digest(data, workflow=self.workflow):
			return engine.get_content_fingerprint(
				SimpleNamespace(**data, meta=self.meta["Source"]), workflow
			).digest

		with patch.object(engine.frappe, "get_hooks", return_value=[{"Source": ["title"]}]):
			base = digest(values)
			changed = deepcopy(values)
			changed["title"] = "Renamed"
			changed["table"][0]["utilized_hours"] = 0
			self.assertEqual(base, digest(changed))
			for table, key, value in [
				("table", "hours", 7),
				("table", "description", "Other"),
				("other", "utilized_hours", 0),
			]:
				changed = deepcopy(values)
				changed[table][0][key] = value
				self.assertNotEqual(base, digest(changed))
			configured = {**self.workflow, exclusions.EXCLUSIONS_FIELD: [{"field_path": "table"}]}
			base = digest(values, configured)
			changed = deepcopy(values)
			changed["table"] = [{"hours": 123}]
			self.assertEqual(base, digest(changed, configured))

	def test_validation_runs_when_engine_is_disabled(self):
		from dinext_common.workflow_approval.metadata import validate_workflow_doc

		with (
			patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=False),
			patch("dinext_common.workflow_approval.metadata.frappe.throw", side_effect=ValueError),
		):
			with self.assertRaises(ValueError):
				validate_workflow_doc(
					SimpleNamespace(
						document_type="Source", custom_fingerprint_excluded_fields=[{"field_path": "missing"}]
					)
				)
