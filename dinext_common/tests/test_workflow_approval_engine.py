import json
import unittest


class TestWorkflowApprovalEngine(unittest.TestCase):
	def engine(self):
		try:
			from dinext_common.workflow_approval import engine
		except (ImportError, ModuleNotFoundError) as exc:
			self.fail(f"workflow approval engine module is missing: {exc}")
		return engine

	def test_manifest_snapshots_thresholds_and_per_user_transitions(self):
		engine = self.engine()
		transitions = [
			{
				"transition_uuid": "t-any",
				"idx": 2,
				"state": "Pending",
				"action": "Approve",
				"next_state": "Approved",
				"allowed": "Manager",
				"policy": "Any",
				"minimum_approvals": None,
				"eligible_approvers": ["alice@example.com", "bob@example.com"],
			},
			{
				"transition_uuid": "t-all",
				"idx": 3,
				"state": "Pending",
				"action": "Reject",
				"next_state": "Rejected",
				"allowed": "Manager",
				"policy": "All",
				"minimum_approvals": None,
				"eligible_approvers": ["bob@example.com", "cara@example.com"],
			},
		]

		manifest, tasks = engine.build_round_manifest(transitions)

		self.assertEqual([row["threshold"] for row in manifest["transitions"]], [1, 2])
		self.assertEqual(
			set(tasks),
			{"alice@example.com", "bob@example.com", "cara@example.com"},
		)
		self.assertEqual(
			[row["transition_uuid"] for row in tasks["bob@example.com"]],
			["t-any", "t-all"],
		)
		self.assertEqual(
			json.loads(engine.serialize_manifest(manifest)),
			manifest,
		)

	def test_manifest_rejects_transition_without_eligible_approvers(self):
		engine = self.engine()
		with self.assertRaises(engine.ZeroEligibleApproversError):
			engine.build_round_manifest(
				[
					{
						"transition_uuid": "t-1",
						"idx": 1,
						"policy": "Any",
						"eligible_approvers": [],
					}
				]
			)

	def test_automatic_winner_prefers_latest_reused_completion_then_idx_uuid(self):
		engine = self.engine()
		rows = [
			{
				"transition_uuid": "t-1",
				"idx": 1,
				"votes": 1,
				"threshold": 1,
				"latest_reused_completed_at": "2025-01-01",
			},
			{
				"transition_uuid": "t-2",
				"idx": 2,
				"votes": 1,
				"threshold": 1,
				"latest_reused_completed_at": "2025-02-01",
			},
		]
		self.assertEqual(engine.select_automatic_winner(rows)["transition_uuid"], "t-2")

		tied = [
			{**rows[1], "transition_uuid": "z", "idx": 3},
			{**rows[1], "transition_uuid": "b", "idx": 2},
			{**rows[1], "transition_uuid": "a", "idx": 2},
		]
		self.assertEqual(engine.select_automatic_winner(tied)["transition_uuid"], "a")

	def test_manifest_semantic_drift_is_fail_closed(self):
		engine = self.engine()
		manifest = {
			"transitions": [
				{"transition_uuid": "t-1", "transition_semantic_hash": "old"}
			]
		}

		self.assertFalse(
			engine.manifest_matches_configuration(
				manifest,
				{"t-1": "new"},
			)
		)
		self.assertTrue(
			engine.manifest_matches_configuration(
				manifest,
				{"t-1": "old"},
			)
		)

	def test_empty_uuid_does_not_conflict_the_same_semantic_hash(self):
		engine = self.engine()
		empty_snapshot = {
			"transitions": [
				{"transition_uuid": "", "transition_semantic_hash": "same"}
			]
		}
		self.assertTrue(engine.manifest_matches_configuration(empty_snapshot, {"": "same"}))
		self.assertTrue(
			engine.manifest_matches_configuration(empty_snapshot, {"filled-once": "same"})
		)
		self.assertFalse(
			engine.manifest_matches_configuration(
				{
					"transitions": [
						{"transition_uuid": "old", "transition_semantic_hash": "same"}
					]
				},
				{"new": "same"},
			)
		)

	def test_cycle_guard_is_keyed_by_workflow_state_and_fingerprint(self):
		engine = self.engine()
		guard = engine.AutomationCycleGuard(max_transitions=2)
		guard.visit("WF", "Pending", "abc")
		with self.assertRaises(engine.AutomationCycleError):
			guard.visit("WF", "Pending", "abc")

		guard = engine.AutomationCycleGuard(max_transitions=1)
		guard.visit("WF", "Pending", "abc")
		with self.assertRaises(engine.AutomationCycleError):
			guard.visit("WF", "Approved", "abc")
