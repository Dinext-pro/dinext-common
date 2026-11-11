"""Scenario routing contracts; lifecycle integration is exercised on a private site."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval.scenarios import service


class TestWorkflowScenarioRouting(unittest.TestCase):
	def setUp(self):
		self.translations = patch.object(service, "_", side_effect=lambda text: text)
		self.translations.start()
		self.addCleanup(self.translations.stop)
		globals_patch = patch("frappe.model.workflow.get_workflow_safe_globals", return_value={})
		globals_patch.start()
		self.addCleanup(globals_patch.stop)

	def definition(self, name, order, condition="", **kwargs):
		return frappe._dict(
			name=name,
			custom_selection_order=order,
			custom_activation_condition=condition,
			states=[],
			transitions=[],
			**kwargs,
		)

	def test_lowest_matching_order_wins(self):
		workflows = [self.definition("B", 2), self.definition("A", 1, 'doc.subject == "urgent"')]
		with patch.object(service, "_definitions", return_value=workflows):
			self.assertEqual(
				service.select_workflow(frappe._dict(doctype="Issue", subject="urgent")).name, "A"
			)
			self.assertEqual(
				service.select_workflow(frappe._dict(doctype="Issue", subject="normal")).name, "B"
			)

	def test_all_false_means_no_workflow(self):
		with patch.object(service, "_definitions", return_value=[self.definition("A", 1, "False")]):
			self.assertIsNone(service.select_workflow(frappe._dict(doctype="Issue")))

	def test_expression_error_stops_selection(self):
		definitions = [self.definition("A", 1, "1 / 0"), self.definition("B", 2)]
		with patch.object(service, "_definitions", return_value=definitions):
			with self.assertRaisesRegex(service.WorkflowScenarioError, "A"):
				service.select_workflow(frappe._dict(doctype="Issue"))

	def test_source_creation_is_part_of_identity(self):
		a = frappe._dict(doctype="Issue", name="same", creation="2026-11-11 01:02:03.123456")
		b = frappe._dict(a, creation="2026-11-11 01:02:03.123457")
		self.assertNotEqual(service.source_key(a), service.source_key(b))
		self.assertEqual(service.source_key(a), service.source_key(frappe._dict(a)))

	def test_terminality_uses_configured_edges_not_available_actions(self):
		workflow = self.definition("A", 1)
		workflow.transitions = [frappe._dict(state="Approved", action="Edit", condition="False")]
		self.assertFalse(service.is_terminal(workflow, "Approved"))
		self.assertTrue(service.is_terminal(workflow, "Done"))

	def test_initial_state_must_match_docstatus(self):
		workflow = self.definition("A", 1)
		workflow.states = [frappe._dict(state="Draft", doc_status=0)]
		with self.assertRaisesRegex(service.WorkflowScenarioError, "A"):
			service.initial_state(workflow, frappe._dict(docstatus=1))

	def test_context_has_one_explicit_nullable_shape(self):
		with patch.object(service, "is_ready", return_value=False):
			self.assertEqual(
				service.get_context(frappe._dict(doctype="Issue")),
				{
					"workflow": None,
					"state_field": None,
					"state": None,
					"process_id": None,
					"process_status": None,
					"definition_revision": None,
				},
			)
