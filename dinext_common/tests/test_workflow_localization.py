"""Regression coverage for rename-only migration of active approvals."""

from unittest import TestCase

from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.policy import transition_semantic_hash


class TestWorkflowLocalization(TestCase):
	def setUp(self):
		self.workflow = "UTP Workflow"
		self.previous = engine._transition_dict(
			{
				"state": "Pending Approval",
				"action": "Согласовано",
				"next_state": "Approved",
				"allowed": "Dinext_UTP_Appoval",
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

	def test_reapplying_canonical_values_is_a_noop(self):
		from dinext_common.workflow_approval.localization import renamed_transition

		self.assertIsNone(renamed_transition(self.workflow, self.current, self.current))

	def test_stale_utp_manifest_requires_evidence_from_every_eligible_approver(self):
		from dinext_common.workflow_approval.localization import _utp_personal_evidence, _verified_utp_rename
		from frappe import _dict

		source = {
			**self.previous,
			"action": "Согласовано",
			"state": "На согласовании",
			"next_state": "Согласовано",
		}
		old_hash = transition_semantic_hash(source)
		uuid = self.current["transition_uuid"]
		tasks = []
		for approver in ("alex@example.com", "elena@example.com"):
			option = _dict({**source, "action": "Approve", "transition_semantic_hash": old_hash, "threshold": 2})
			option.as_dict = lambda option=option: option
			tasks.append(
				_dict(
					workflow=self.workflow,
					approver=approver,
					status="Working",
					round_manifest="the same snapshot",
					available_workflow_transitions=[option],
				)
			)
		manifest = {
			**self.previous,
			"transition_semantic_hash": "a stale manifest hash",
			"eligible_approvers": [t.approver for t in tasks],
			"threshold": 2,
		}
		self.assertIsNone(_verified_utp_rename(manifest, self.current, {}))
		proven = _utp_personal_evidence(tasks, {uuid: self.current})[uuid]
		self.assertEqual(
			_verified_utp_rename(manifest, self.current, proven)["transition_semantic_hash"],
			self.current["transition_semantic_hash"],
		)
		carried = _dict(
			workflow=self.workflow,
			approver="former@example.com",
			status="Completed",
			transition_uuid=uuid,
			round_manifest="the same snapshot",
			available_workflow_transitions=[],
		)
		self.assertNotIn(uuid, _utp_personal_evidence([*tasks, carried], {uuid: self.current}))
		tasks[0].available_workflow_transitions[0].transition_semantic_hash = "unproven"
		proven = _utp_personal_evidence(tasks, {uuid: self.current})[uuid]
		self.assertIsNone(_verified_utp_rename(manifest, self.current, proven))
