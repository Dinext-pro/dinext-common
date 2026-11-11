"""Migration preserves routing settings and approval identities without replay."""

import unittest
from unittest.mock import Mock, patch

import frappe


class TestWorkflowScenarioMigration(unittest.TestCase):
	def setUp(self):
		translator = patch("dinext_common.workflow_approval.scenarios.metadata._", side_effect=lambda text: text)
		translator.start()
		self.addCleanup(translator.stop)

	def test_orders_are_stable_unique_and_prefer_existing_active_definition(self):
		from dinext_common.workflow_approval.scenarios.migration import planned_orders
		rows = [
			frappe._dict(name="Inactive", document_type="Issue", is_active=0, custom_selection_order=0),
			frappe._dict(name="Active B", document_type="Issue", is_active=1, custom_selection_order=0),
			frappe._dict(name="Active A", document_type="Issue", is_active=1, custom_selection_order=0),
			frappe._dict(name="Other", document_type="Task", is_active=1, custom_selection_order=0),
		]
		self.assertEqual(planned_orders(rows), {"Active A": 1, "Active B": 2, "Inactive": 3, "Other": 1})

	def test_existing_unique_values_survive_a_repeated_migration(self):
		from dinext_common.workflow_approval.scenarios.migration import planned_orders
		rows = [
			frappe._dict(name="A", document_type="Issue", is_active=1, custom_selection_order=4),
			frappe._dict(name="B", document_type="Issue", is_active=0, custom_selection_order=9),
		]
		self.assertEqual(planned_orders(rows), {})
		rows.append(frappe._dict(name="C", document_type="Issue", is_active=1, custom_selection_order=0))
		self.assertEqual(planned_orders(rows), {"C": 1})

	def test_duplicate_legacy_numbers_do_not_displace_valid_unique_numbers(self):
		from dinext_common.workflow_approval.scenarios.migration import planned_orders
		rows = [
			frappe._dict(name="A", document_type="Issue", is_active=1, custom_selection_order=1),
			frappe._dict(name="B", document_type="Issue", is_active=0, custom_selection_order=1),
			frappe._dict(name="C", document_type="Issue", is_active=0, custom_selection_order=2),
		]
		self.assertEqual(planned_orders(rows), {"B": 3})

	def test_adoption_preserves_complete_rows_and_never_reconciles_source(self):
		from dinext_common.workflow_approval.scenarios import migration, service
		tasks = [frappe._dict(name="task-1", reference_doctype="Issue", reference_name="ISS-1", source_created_at="2026-01-02 03:04:05", workflow="Old", status="Working", approval_round_id="old-round", vote_comment="comment", completed_at=None)]
		source = frappe._dict(doctype="Issue", name="ISS-1", creation="2026-01-02 03:04:05")
		with patch.object(migration.frappe, "db", Mock(table_exists=Mock(return_value=True), has_column=Mock(return_value=True))), patch.object(migration.frappe, "get_all", return_value=tasks), patch.object(migration.frappe, "get_doc", return_value=source), patch.object(service, "adopt_legacy_source", return_value="process-1") as adopt:
			count = migration.adopt_legacy_sources()
		self.assertEqual(count, 1)
		adopt.assert_called_once_with(source, tasks)
		self.assertEqual(tasks[0].name, "task-1")
		self.assertEqual(tasks[0].approval_round_id, "old-round")
		self.assertEqual(tasks[0].vote_comment, "comment")

	def test_recreated_or_unidentified_sources_are_never_adopted(self):
		from dinext_common.workflow_approval.scenarios import migration, service
		tasks = [frappe._dict(name="task-1", reference_doctype="Issue", reference_name="ISS-1", source_created_at="2025-01-02 03:04:05", workflow="Old")]
		source = frappe._dict(doctype="Issue", name="ISS-1", creation="2026-01-02 03:04:05")
		with patch.object(migration.frappe, "db", Mock(table_exists=Mock(return_value=True), has_column=Mock(return_value=True))), patch.object(migration.frappe, "get_all", return_value=tasks), patch.object(migration.frappe, "get_doc", return_value=source), patch.object(service, "adopt_legacy_source") as adopt:
			self.assertEqual(migration.adopt_legacy_sources(), 0)
		adopt.assert_not_called()
