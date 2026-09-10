import unittest


class TestWorkflowApprovalPolicy(unittest.TestCase):
	def policy(self):
		try:
			from dinext_common.workflow_approval import policy
		except ModuleNotFoundError as exc:
			self.fail(f"workflow approval policy module is missing: {exc}")
		return policy

	def test_blank_policy_is_any(self):
		policy = self.policy()

		self.assertEqual(policy.normalize_policy(None), "Any")
		self.assertEqual(policy.normalize_policy(""), "Any")
		self.assertEqual(policy.normalize_policy("Any"), "Any")

	def test_unknown_policy_is_rejected(self):
		policy = self.policy()

		with self.assertRaises(ValueError):
			policy.normalize_policy("Standard")

	def test_thresholds_follow_policy_and_clamp_minimum(self):
		policy = self.policy()

		self.assertEqual(policy.required_approvals("Any", None, 4), 1)
		self.assertEqual(policy.required_approvals("All", None, 4), 4)
		self.assertEqual(policy.required_approvals("Minimum", 3, 4), 3)
		self.assertEqual(policy.required_approvals("Minimum", 7, 4), 4)

	def test_zero_candidates_and_non_positive_minimum_are_rejected(self):
		policy = self.policy()

		with self.assertRaises(policy.ZeroEligibleApproversError):
			policy.required_approvals("Any", None, 0)
		with self.assertRaises(ValueError):
			policy.required_approvals("Minimum", 0, 3)

	def test_threshold_reachability_counts_remaining_cohort(self):
		policy = self.policy()

		self.assertTrue(policy.is_threshold_reachable(threshold=3, votes=1, remaining=2))
		self.assertFalse(policy.is_threshold_reachable(threshold=3, votes=1, remaining=1))

	def test_reached_transition_tie_break_is_idx_then_uuid(self):
		policy = self.policy()
		reached = [
			{"transition_uuid": "z", "idx": 2, "votes": 2, "threshold": 2},
			{"transition_uuid": "b", "idx": 1, "votes": 1, "threshold": 1},
			{"transition_uuid": "a", "idx": 1, "votes": 1, "threshold": 1},
		]

		self.assertEqual(policy.select_reached_transition(reached)["transition_uuid"], "a")

	def test_legacy_all_users_flag_maps_to_parallel_policy(self):
		policy = self.policy()

		self.assertEqual(policy.policy_from_legacy_flag(0), "Any")
		self.assertEqual(policy.policy_from_legacy_flag("0"), "Any")
		self.assertEqual(policy.policy_from_legacy_flag(1), "All")
		self.assertEqual(policy.policy_from_legacy_flag("1"), "All")

	def test_semantic_hash_is_stable_and_changes_with_transition_behavior(self):
		policy = self.policy()
		transition = {
			"state": "Pending",
			"action": "Approve",
			"next_state": "Approved",
			"allowed": "Manager",
			"condition": "doc.total > 0",
			"allow_self_approval": 0,
			"policy": "Any",
			"minimum_approvals": None,
		}

		first = policy.transition_semantic_hash(transition)
		second = policy.transition_semantic_hash(dict(reversed(list(transition.items()))))
		changed = policy.transition_semantic_hash({**transition, "next_state": "Rejected"})

		self.assertEqual(first, second)
		self.assertNotEqual(first, changed)

	def test_comment_normalization_removes_controls_and_zero_width(self):
		policy = self.policy()

		self.assertEqual(policy.normalize_comment("  reason\u200b\u0000\n"), "reason")
		with self.assertRaises(ValueError):
			policy.normalize_comment("\u200b \t", required=True)
		with self.assertRaises(ValueError):
			policy.normalize_comment("x" * 4001)

	def test_task_names_are_deterministic_bounded_and_manifest_repair_is_exact(self):
		policy = self.policy()
		approvers = ["alice@example.com", "bob@example.com"]

		alice = policy.make_task_name("round-001", approvers[0])
		bob = policy.make_task_name("round-001", approvers[1])

		self.assertEqual(alice, policy.make_task_name("round-001", approvers[0]))
		self.assertNotEqual(alice, bob)
		self.assertLessEqual(len(alice), 140)
		self.assertEqual(
			policy.missing_task_names("round-001", approvers, {alice}),
			{bob},
		)
