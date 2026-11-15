"""Regression coverage for rename-only migration of active approvals."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.policy import transition_semantic_hash


class TestWorkflowLocalization(TestCase):
	def setUp(self):
		self.workflow = "AFL Workflow"
		self.previous = engine._transition_dict(
			{
				"state": "Pending Approval",
				"action": "Согласовано",
				"next_state": "Approved",
				"allowed": "All",
				"condition": "doc.user != frappe.session.user",
				"custom_transition_uuid": "approval-transition",
				"custom_parallel_approval_policy": "All",
			}
		)
		self.current = {**self.previous, "action": "Approve"}
		self.current["transition_semantic_hash"] = transition_semantic_hash(self.current)

	def rename(self, current=None, workflow=None):
		from dinext_common.workflow_approval.localization import renamed_transition

		return renamed_transition(workflow or self.workflow, self.previous, current or self.current)

	def test_renames_only_labels_and_proven_hash(self):
		self.assertEqual(
			self.rename(),
			{
				"state": "Pending Approval",
				"action": "Approve",
				"next_state": "Approved",
				"transition_semantic_hash": self.current["transition_semantic_hash"],
			},
		)

	def test_changed_condition_or_uuid_is_incompatible(self):
		changed = {**self.current, "condition": "doc.owner == frappe.session.user"}
		changed["transition_semantic_hash"] = transition_semantic_hash(changed)
		self.assertIsNone(self.rename(current=changed))
		self.assertIsNone(self.rename(current={**self.current, "transition_uuid": "another"}))

	def test_changed_comment_rule_is_incompatible(self):
		self.assertIsNone(self.rename(current={**self.current, "comment_is_required": True}))

	def test_other_workflows_keep_russian_labels(self):
		self.assertIsNone(self.rename(workflow="Project Approval"))

	def test_registered_localization_is_selected_by_workflow(self):
		from dinext_common.workflow_approval.localization import state_name

		with (
			patch.object(frappe, "local", SimpleNamespace(site="test")),
			patch.object(frappe, "get_hooks", return_value={"Review Workflow": ["example.workflow_labels"]}),
			patch.object(frappe, "get_attr", return_value=lambda: {"states": {"Review old": "Review new"}}),
		):
			self.assertEqual(state_name("Review Workflow", "Review old"), "Review new")
			self.assertEqual(state_name("Other Workflow", "Review old"), "Review old")

	def test_reapplying_canonical_values_is_a_noop(self):
		from dinext_common.workflow_approval.localization import renamed_transition

		self.assertIsNone(renamed_transition(self.workflow, self.current, self.current))
