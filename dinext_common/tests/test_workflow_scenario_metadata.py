"""Scenario settings reject invalid routes before they can affect documents."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class Workflow(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def set(self, key, value):
		setattr(self, key, value)


class TestWorkflowScenarioMetadata(unittest.TestCase):
	def settings(self, **values):
		return Workflow(name="Schema A", document_type="Issue", custom_selection_order=1,
			custom_activation_condition=values.pop("condition", "doc.priority == 'High'"), **values)

	def test_invalid_expression_is_rejected_without_evaluating_it(self):
		from dinext_common.workflow_approval.scenarios import metadata
		with patch.object(metadata, "_", side_effect=lambda text: text), self.assertRaisesRegex(ValueError, "condition"):
			metadata.validate_condition("doc.priority ==")

	def test_unsafe_expression_is_rejected_on_save(self):
		from dinext_common.workflow_approval.scenarios import metadata
		for expression in ("(value := True)", "lambda: True", "doc.__class__"):
			with self.subTest(expression=expression), patch.object(metadata, "_", side_effect=lambda text: text), self.assertRaises(ValueError):
				metadata.validate_condition(expression)

	def test_blank_and_valid_conditions_compile_without_running_queries(self):
		from dinext_common.workflow_approval.scenarios import metadata
		for expression in ("", "  ", "doc.priority == 'High'", "frappe.db.get_value('User', doc.owner, 'enabled')"):
			metadata.validate_condition(expression)

	def test_nonpositive_fractional_or_boolean_order_rejected(self):
		from dinext_common.workflow_approval.scenarios import metadata
		for order in (-1, 0, 1.5, "1.5", True):
			with self.subTest(order=order), patch.object(metadata, "_", side_effect=lambda text: text), self.assertRaises(ValueError):
				metadata.normalized_order(order)

	def test_order_of_an_inactive_schema_still_blocks_duplicate(self):
		from dinext_common.workflow_approval.scenarios import metadata
		db = Mock()
		db.get_value.return_value = "Inactive Schema"
		with patch.object(metadata.frappe, "db", db), patch.object(metadata, "_", side_effect=lambda text: text), self.assertRaisesRegex(ValueError, "Inactive Schema"):
			metadata.validate_settings(self.settings())
		filters = db.get_value.call_args.args[1]
		self.assertNotIn("is_active", filters)
		self.assertEqual(filters["document_type"], "Issue")

	def test_omitted_order_gets_next_free_value(self):
		from dinext_common.workflow_approval.scenarios import metadata
		workflow = self.settings()
		workflow.custom_selection_order = None
		with patch.object(metadata, "next_selection_order", return_value=7), patch.object(metadata.frappe, "db", Mock(get_value=Mock(return_value=None))):
			metadata.validate_settings(workflow)
		self.assertEqual(workflow.custom_selection_order, 7)

	def test_import_keeps_existing_route_and_number(self):
		from dinext_common.workflow_approval.scenarios import metadata
		incoming = self.settings()
		previous = Workflow(custom_activation_condition="doc.priority == 'Low'", custom_selection_order=5)
		with patch.object(metadata.frappe, "flags", Workflow(in_fixtures=True)), patch.object(metadata.frappe, "db", Mock(exists=Mock(return_value=True))), patch.object(metadata.frappe, "get_doc", return_value=previous):
			metadata.preserve_fixture_settings(incoming)
		self.assertEqual(incoming.custom_selection_order, 5)
		self.assertEqual(incoming.custom_activation_condition, "doc.priority == 'Low'")

	def test_unique_constraint_covers_type_and_order(self):
		from dinext_common.workflow_approval.scenarios import metadata
		with patch.object(metadata.frappe, "db", Mock()) as db:
			metadata.ensure_constraints()
		db.add_unique.assert_any_call("Workflow", ["document_type", "custom_selection_order"], constraint_name="workflow_scenario_selection_order")

	def test_workflow_override_does_not_deactivate_siblings_or_mass_update_sources(self):
		from dinext_common.workflow_approval.scenarios.workflow import DinextWorkflow
		workflow = object.__new__(DinextWorkflow)
		with patch("frappe.db", Mock()) as db:
			workflow.set_active()
			workflow.update_default_workflow_status()
		self.assertEqual(db.mock_calls, [])
