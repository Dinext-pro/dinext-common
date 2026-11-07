import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestRebuildRoundConflict(unittest.TestCase):
	def test_live_configuration_drift_is_described_without_mutating_the_round(self):
		from dinext_common.workflow_approval import engine

		old = {
			"transition_uuid": "approve",
			"idx": 1,
			"state": "Pending",
			"action": "Approve",
			"next_state": "Approved",
			"allowed": "Manager",
			"policy": "All",
			"eligible_approvers": ["alice@example.com", "bob@example.com"],
		}
		old_row = engine._transition_dict(
			{**old, "custom_transition_uuid": "approve", "custom_parallel_approval_policy": "All"}
		)
		old_row["eligible_approvers"] = old["eligible_approvers"]
		manifest, _tasks = engine.build_round_manifest([old_row])
		snapshot = manifest["transitions"][0]
		current = {
			**old,
			"next_state": "Changed",
			"custom_transition_uuid": "approve",
			"custom_parallel_approval_policy": "All",
		}
		task = SimpleNamespace(
			reference_doctype="ToDo",
			reference_name="DOC-1",
			workflow="WF",
			workflow_state="Pending",
			round_status="Open",
			approval_round_id="ROUND-1",
			round_manifest=engine.serialize_manifest(manifest),
		)
		vote = {
			"transition_uuid": "approve",
			"transition_semantic_hash": snapshot["transition_semantic_hash"],
			"approver": "alice@example.com",
			"action": "Approve",
		}
		workflow = SimpleNamespace(transitions=[current])
		with (
			patch.object(engine, "_workflow_context", return_value=("WF", workflow, "status", "Pending")),
			patch.object(engine, "_completed_vote_rows", return_value=[vote]),
			patch.object(engine, "_mark_conflicted") as mark,
		):
			result = engine.preview_configuration_conflict(task, source=object())
			self.assertEqual(result["reason"], "configuration_changed")
			self.assertEqual(result["void"][0]["approvers"], ["alice@example.com"])
			self.assertEqual(task.round_status, "Open")
			mark.assert_not_called()
			current["next_state"] = "Approved"
			self.assertIsNone(engine.preview_configuration_conflict(task, source=object()))

	def test_descriptor_includes_live_conflict_and_omits_healthy_open_round(self):
		from dinext_common.workflow_approval import api

		rows = [
			SimpleNamespace(
				name=name,
				approval_round_id=round_id,
				round_status="Open",
				reference_name=reference,
				source_title=reference,
				failure_metadata=None,
			)
			for name, round_id, reference in (("WT-1", "R1", "DOC-1"), ("WT-2", "R2", "DOC-2"))
		]
		metadata = {"reason": "configuration_changed", "void": [{"action": "Approve"}], "stable": []}
		with (
			patch.object(api.frappe, "get_all", return_value=rows),
			patch.object(api.frappe, "get_doc"),
			patch.object(api, "_caller_is_system_manager", return_value=True),
			patch.object(api.engine, "preview_configuration_conflict", side_effect=[metadata, None]),
		):
			result = api.describe_rebuild_rounds("ToDo", ["DOC-1", "DOC-2"])
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["round_status"], "Conflicted")
		self.assertEqual(result[0]["configuration_change"], metadata)
		self.assertTrue(result[0]["can_reset"])

	def test_reset_of_an_open_live_conflict_uses_vote_carrying_rebuild(self):
		from dinext_common.workflow_approval import api

		task = SimpleNamespace(reference_doctype="ToDo", reference_name="DOC-1", round_status="Open")
		source = MagicMock()
		with (
			patch.object(api, "_require_post"),
			patch.object(api, "_require_system_manager"),
			patch.object(api.engine, "normalize_comment", return_value="Reason"),
			patch.object(api.engine, "_round_task_names", return_value=["WT-1"]),
			patch.object(api.frappe, "get_doc", side_effect=[task, source, task]),
			patch.object(api.engine, "_lock_domain_dependencies"),
			patch.object(api.engine, "configuration_metadata", return_value=None),
			patch.object(
				api.engine, "preview_configuration_conflict", return_value={"reason": "configuration_changed"}
			),
			patch.object(
				api.engine,
				"rebuild_configuration_conflict",
				return_value={"carried": [], "dropped": [], "new_tasks": ["NEW"]},
			) as rebuild,
			patch.object(api.engine, "_cancel_round") as cancel,
		):
			result = api.reset_round("R1", "Reason")
		self.assertEqual(result["new_tasks"], ["NEW"])
		rebuild.assert_called_once()
		cancel.assert_not_called()

	def test_batch_reset_keeps_successes_and_continues_after_a_failure(self):
		from dinext_common.workflow_approval import api

		with (
			patch.object(api, "_require_post"),
			patch.object(api, "_require_system_manager"),
			patch.object(api.engine, "normalize_comment", return_value="Reason"),
			patch.object(api, "_reset_round", side_effect=[{}, ValueError("Cannot rebuild"), {}]) as reset,
			patch.object(api.frappe.db, "commit") as commit,
			patch.object(api.frappe.db, "rollback") as rollback,
		):
			result = api.reset_rounds(["R1", "R2", "R1", "R3"], "Reason")
		self.assertEqual(
			result,
			{
				"succeeded": ["R1", "R3"],
				"failed": [{"round_id": "R2", "error": "Cannot rebuild"}],
			},
		)
		self.assertEqual([call.args[0] for call in reset.call_args_list], ["R1", "R2", "R3"])
		self.assertEqual(commit.call_count, 2)
		rollback.assert_called_once()
