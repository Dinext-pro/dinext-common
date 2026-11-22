"""Bulk actions retain each schema's own immutable task/transition identity."""

import unittest

import frappe

from dinext_common.workflow_approval import api


class TestWorkflowScenarioBulk(unittest.TestCase):
	def target(self, name, workflow, uuid, *, comment=False, action="Approve"):
		task = frappe._dict(
			name="task-" + name, reference_name=name, workflow=workflow, workflow_process="process-" + name
		)
		transition = {
			"transition_uuid": uuid,
			"action": action,
			"next_state": "Done-" + workflow,
			"allowed": "All",
			"comment_is_required": comment,
		}
		return task, transition

	def test_mixed_workflows_intersect_action_with_individual_targets(self):
		a, ta = self.target("A", "W1", "u1")
		b, tb = self.target("B", "W2", "u2", comment=True)
		rows = api._common_transition_targets([a, b], {a.name: [ta], b.name: [tb]})
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["action"], "Approve")
		self.assertTrue(rows[0]["comment_is_required"])
		self.assertIsNone(rows[0]["transition_uuid"])
		self.assertEqual([row["transition_uuid"] for row in rows[0]["targets"]], ["u1", "u2"])
		self.assertEqual([row["process_id"] for row in rows[0]["targets"]], ["process-A", "process-B"])

	def test_same_workflow_preserves_uuid_intersection(self):
		a, ta = self.target("A", "W", "u1")
		b, tb = self.target("B", "W", "u2")
		self.assertEqual(api._common_transition_targets([a, b], {a.name: [ta], b.name: [tb]}), [])

	def test_mixed_ambiguous_action_is_not_offered(self):
		a, ta = self.target("A", "W1", "u1")
		b, tb = self.target("B", "W2", "u2")
		self.assertEqual(
			api._common_transition_targets(
				[a, b], {a.name: [ta, {**ta, "transition_uuid": "u3"}], b.name: [tb]}
			),
			[],
		)

	def test_missing_task_transition_is_not_offered(self):
		a, ta = self.target("A", "W1", "u1")
		b, _tb = self.target("B", "W2", "u2")
		self.assertEqual(api._common_transition_targets([a, b], {a.name: [ta], b.name: []}), [])
