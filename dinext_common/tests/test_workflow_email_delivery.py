import unittest
from types import SimpleNamespace as Row
from unittest.mock import patch


class TestWorkflowEmailDelivery(unittest.TestCase):
	def test_creator_uses_current_uuid_flags_and_filters_actions(self):
		from dinext_common.workflow_approval import notifications as n
		a, b = Row(transition_uuid="a", action="Approve"), Row(transition_uuid="b", action="Edit")
		task = Row(approver="owner", source_owner="owner", available_workflow_transitions=[a,b])
		workflow = Row(transitions=[Row(custom_transition_uuid="a", send_email_to_creator=0),
			Row(custom_transition_uuid="b", send_email_to_creator=1)])
		self.assertEqual(n.notification_transitions(task, workflow), [b])
		workflow.transitions[0].send_email_to_creator = 1
		workflow.transitions[1].send_email_to_creator = 0
		self.assertEqual(n.notification_transitions(task, workflow), [a])
		workflow.transitions[0].send_email_to_creator = 0
		self.assertEqual(n.notification_transitions(task, workflow), [])
		task.approver = "reviewer"
		self.assertEqual(n.notification_transitions(task, workflow), [a,b])

	def test_digest_identity_separates_states(self):
		from dinext_common.workflow_approval import notifications as n
		self.assertNotEqual(n.make_delivery_key("Digest", "WF", "user", "slot", state="Pending"),
			n.make_delivery_key("Digest", "WF", "user", "slot", state="Finance"))

	def test_digest_uses_only_allowed_creator_actions(self):
		from dinext_common.workflow_approval import notifications as n
		task = Row(name="T", reference_doctype="Project", reference_name="P", source_title="Project")
		with patch.object(n, "_task_actions", return_value=[{"action_name":"Edit"}]) as actions, \
			patch.object(n, "get_url_to_form", return_value="/app/project/P"), \
			patch.object(n.frappe, "get_hooks", return_value=[]):
			rows = n._digest_rows([task], permitted={"T": ["allowed"]})
		self.assertEqual(rows[0]["actions"], [{"action_name":"Edit"}])
		self.assertEqual(actions.call_args.kwargs["transitions"], ["allowed"])

	def test_entry_context_uses_only_the_winning_round(self):
		from dinext_common.workflow_approval import email_context
		votes = [Row(approver="reviewer", vote_comment="Fix the dates", completed_at="2026-01-01 12:00:00")]
		with patch.object(email_context.frappe, "get_all", return_value=votes) as get_all:
			context = email_context.entry_context_for_round("round-1", {"transition_uuid":"reject", "action":"Reject", "next_state":"Rejected"})
		self.assertEqual(context["comments"][0]["text"], "Fix the dates")
		self.assertEqual(get_all.call_args.kwargs["filters"]["approval_round_id"], "round-1")
		self.assertEqual(get_all.call_args.kwargs["filters"]["transition_uuid"], "reject")
