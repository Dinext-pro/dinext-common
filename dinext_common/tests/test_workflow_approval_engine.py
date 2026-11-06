import json
import unittest
from unittest.mock import Mock, patch


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


class TestAutomaticVoteReuse(unittest.TestCase):
	def setUp(self):
		import frappe

		from dinext_common.workflow_approval import engine

		self.engine = engine
		self.identity = {
			"reference_doctype": "Issue",
			"reference_name": "ISSUE-1",
			"source_created_at": "2026-01-01 12:00:00",
			"workflow": "Issue Review",
			"workflow_state": "Pending",
		}
		self.approve = frappe._dict(
			transition_uuid="approve",
			transition_semantic_hash="approve-hash",
			action="Approve",
			auto_complete_unchanged=1,
			transition_idx=1,
		)
		self.reject = frappe._dict(
			transition_uuid="reject",
			transition_semantic_hash="reject-hash",
			action="Reject",
			auto_complete_unchanged=0,
			transition_idx=2,
		)
		self.tasks = {}
		self.snapshots = []
		self.alice = self.working_task("alice")
		self.fingerprint = engine.ContentFingerprint("1", "current-content", "")

	def working_task(self, approver):
		task = self.engine.frappe._dict(
			**self.identity,
			name=f"current-{approver}",
			approver=approver,
			approval_round_id="current-round",
			status="Working",
			available_workflow_transitions=[self.approve.copy(), self.reject.copy()],
		)
		task.reload = lambda: None
		self.tasks[task.name] = task
		return task

	def prior_decision(self, name, completed_at, *, transition=None, saved_flag=1, **overrides):
		transition = self.approve if transition is None else transition
		task = self.engine.frappe._dict(
			**self.identity,
			name=name,
			approver="alice",
			status="Completed",
			completion_source="Manual",
			completed_at=completed_at,
			transition_uuid=transition.transition_uuid,
			transition_semantic_hash=transition.transition_semantic_hash,
			content_fingerprint="current-content",
			content_fingerprint_version="1",
		)
		task.update(overrides)
		self.tasks[name] = task
		if saved_flag is not None:
			self.snapshots.append(
				self.engine.frappe._dict(
					parent=name,
					parenttype="Workflow Task",
					parentfield="available_workflow_transitions",
					transition_uuid=task.transition_uuid,
					transition_semantic_hash=task.transition_semantic_hash,
					auto_complete_unchanged=saved_flag,
				)
			)

	def get_all(self, doctype, *, filters, fields=None, pluck=None, order_by=None):
		rows = self.tasks.values() if doctype == "Workflow Task" else self.snapshots
		for field, condition in filters.items():
			if isinstance(condition, (list, tuple)):
				operator, values = condition
				self.assertEqual(operator, "in")
				rows = [row for row in rows if row.get(field) in values]
			else:
				rows = [row for row in rows if row.get(field) == condition]
		for clause in reversed((order_by or "").split(", ")):
			if clause:
				field, direction = clause.split()
				rows = sorted(rows, key=lambda row: row.get(field) or "", reverse=direction == "desc")
		if pluck:
			return [row.get(pluck) for row in rows]
		return [self.engine.frappe._dict({field: row.get(field) for field in fields}) for row in rows]

	def apply(self, *tasks):
		engine = self.engine
		db = Mock()
		db.get_value.side_effect = lambda _doctype, name, field: self.tasks[name][field]
		db.set_value.side_effect = lambda _doctype, name, values, **kwargs: self.tasks[name].update(values)
		manifest = {"transitions": [{"transition_uuid": "approve", "idx": 1, "threshold": 1}]}
		with (
			patch.object(engine.frappe, "get_all", side_effect=self.get_all),
			patch.object(engine.frappe, "db", db),
			patch.object(engine.frappe, "get_hooks", return_value=[]),
			patch.object(engine, "now_datetime", return_value="2026-02-01"),
			patch.object(engine, "_", side_effect=lambda message: message),
		):
			return engine._apply_automatic_votes(Mock(), list(tasks), manifest, self.fingerprint)

	def test_newer_reject_supersedes_older_approve_and_its_automatic_copy(self):
		self.prior_decision("old-approve", "2026-01-02")
		self.prior_decision("manual-reject", "2026-01-03", transition=self.reject, saved_flag=0)
		self.prior_decision("automatic-approve", "2026-01-04", completion_source="Automatic Unchanged")
		self.prior_decision("bob-approve", "2026-01-02", approver="bob", completion_source="Signed Link")
		bob = self.working_task("bob")

		self.apply(self.alice, bob)

		self.assertEqual(self.alice.status, "Working")
		self.assertEqual(bob.status, "Completed")
		self.assertEqual(bob.reused_from_workflow_task, "bob-approve")

	def test_carried_and_automatic_votes_do_not_replace_the_personal_decision(self):
		self.prior_decision("personal-approve", "2026-01-02", completion_source="Bulk")
		self.prior_decision("auto-approve", "2026-01-03", completion_source="Automatic Unchanged")
		self.prior_decision("carried-approve", "2026-01-04", completion_source="Carried")

		self.apply(self.alice)

		self.assertEqual(self.alice.reused_from_workflow_task, "personal-approve")

	def test_latest_decision_with_invalid_snapshot_does_not_allow_older_vote(self):
		self.prior_decision("old-approve", "2026-01-02")
		for snapshot, changes in (
			("unchecked", {"saved_flag": 0}),
			("missing", {"saved_flag": None}),
			("changed UUID", {"transition_uuid": "replaced"}),
			("changed semantic hash", {"transition_semantic_hash": "changed"}),
			("changed content", {"content_fingerprint": "edited"}),
			("changed version", {"content_fingerprint_version": "2"}),
			("missing content", {"content_fingerprint": ""}),
		):
			with self.subTest(snapshot=snapshot):
				self.snapshots = [row for row in self.snapshots if row.parent != "latest"]
				self.prior_decision("latest", "2026-01-03", **changes)
				task = self.working_task("alice")

				self.apply(task)

				self.assertEqual(task.status, "Working")

	def test_other_source_instances_workflows_and_states_do_not_supersede_vote(self):
		self.prior_decision("matching", "2026-01-02")
		for field, value in (
			("reference_doctype", "Other DocType"),
			("reference_name", "ISSUE-2"),
			("source_created_at", "2026-01-03 12:00:00"),
			("workflow", "Other Workflow"),
			("workflow_state", "Other State"),
		):
			self.prior_decision(field, "2026-01-03", **{field: value})

		self.apply(self.alice)

		self.assertEqual(self.alice.reused_from_workflow_task, "matching")

	def test_current_transition_must_also_allow_automatic_completion(self):
		self.prior_decision("approved", "2026-01-02")
		self.alice.available_workflow_transitions[0]["auto_complete_unchanged"] = 0

		self.apply(self.alice)

		self.assertEqual(self.alice.status, "Working")

	def test_tied_completion_times_choose_by_task_name(self):
		self.prior_decision("b-approve", "2026-01-02")
		self.prior_decision("a-reject", "2026-01-02", transition=self.reject, saved_flag=0)

		self.apply(self.alice)

		self.assertEqual(self.alice.status, "Working")
