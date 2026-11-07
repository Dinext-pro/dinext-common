import copy
import unittest
from datetime import datetime, time, timezone
from types import SimpleNamespace as Row


def workflow(**values):
	defaults = dict(
		send_email_alert=1, custom_group_workflow_action_emails=1,
		custom_group_interval_unit="Days", custom_group_interval_value=1,
		custom_group_send_times="08:00, 17:00", custom_group_schedule_anchor="2026-01-01 00:00:00",
		custom_group_email_template="Digest", custom_workflow_action_email_template="Action",
		custom_attach_document_pdf=0, states=[],
	)
	return Row(**(defaults | values))


class TestWorkflowEmailSettings(unittest.TestCase):
	def settings(self):
		from dinext_common.workflow_approval import email_settings
		return email_settings

	def test_inherited_profile_and_both_gates(self):
		s = self.settings()
		state = Row(state="Pending", send_email=1, custom_email_settings_override=0)
		w = workflow(states=[state])
		self.assertEqual(s.profile_for_state(w, "Pending").mode, "Digest")
		self.assertEqual(s.profile_for_state(w, "Pending").send_times, (time(8), time(17)))
		state.send_email = 0
		self.assertFalse(s.profile_for_state(w, "Pending").enabled)
		state.send_email, w.send_email_alert = 1, 0
		self.assertFalse(s.profile_for_state(w, "Pending").enabled)
		self.assertFalse(s.profile_for_state(w, "Missing").enabled)

	def test_explicit_immediate_overrides_grouped_parent_and_template(self):
		s = self.settings()
		state = Row(state="Rejected", send_email=1, custom_email_settings_override=1,
			custom_group_workflow_action_emails=0, next_action_email_template="Correction")
		profile = s.profile_for_state(workflow(states=[state]), "Rejected")
		self.assertEqual(profile.mode, "Immediate")
		self.assertEqual(profile.template, "Correction")
		state.next_action_email_template = ""
		self.assertEqual(s.profile_for_state(workflow(states=[state]), "Rejected").template, "Action")

	def test_times_normalize_and_reject_invalid_values(self):
		s = self.settings()
		self.assertEqual(s.normalize_send_times("17:00,08:00, 17:00"), "08:00, 17:00")
		for bad in ("25:00", "08:61", "tomorrow", "08:00,,17:00"):
			with self.subTest(bad=bad), self.assertRaises(ValueError):
				s.normalize_send_times(bad)

	def test_inherited_refresh_and_global_change_do_not_create_override(self):
		s = self.settings()
		w = workflow(states=[Row(state="Pending", send_email=1, custom_email_settings_override=0)])
		s.prepare_email_profiles(w, now="2026-01-01 00:00:00")
		previous = copy.deepcopy(w)
		w.custom_group_send_times = "09:00"
		s.prepare_email_profiles(w, previous, now="2026-01-02 00:00:00")
		self.assertEqual(w.states[0].custom_email_settings_override, 0)
		self.assertEqual(w.states[0].custom_group_send_times, "09:00")
		self.assertEqual(w.custom_group_schedule_anchor, "2026-01-02 00:00:00")

	def test_first_state_edit_freezes_parent_and_reset_preserves_gate(self):
		s = self.settings()
		w = workflow(states=[Row(state="Rejected", send_email=1, custom_email_settings_override=0)])
		s.prepare_email_profiles(w, now="2026-01-01 00:00:00")
		before = copy.deepcopy(w)
		w.states[0].custom_group_workflow_action_emails = 0
		s.prepare_email_profiles(w, before, now="2026-01-02 00:00:00")
		self.assertEqual(w.states[0].custom_email_settings_override, 1)
		self.assertEqual(w.states[0].custom_group_send_times, "08:00, 17:00")
		before = copy.deepcopy(w)
		w.states[0].custom_email_settings_override = 0
		w.states[0].send_email = 0
		s.prepare_email_profiles(w, before, now="2026-01-03 00:00:00")
		self.assertEqual(w.states[0].custom_group_workflow_action_emails, 1)
		self.assertEqual(w.states[0].send_email, 0)

	def test_daily_two_slots_and_single_latest_catchup(self):
		from dinext_common.workflow_approval.notifications import latest_due_digest_slot
		args = dict(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
			timezone_name="Europe/Moscow", unit="Days", interval=1,
			send_times=(time(8), time(17)), anchor=datetime(2026, 1, 1, tzinfo=timezone.utc))
		self.assertEqual(latest_due_digest_slot(now=datetime(2026, 1, 2, 5, 0, tzinfo=timezone.utc), **args),
			datetime(2026, 1, 2, 5, 0, tzinfo=timezone.utc))
		self.assertEqual(latest_due_digest_slot(now=datetime(2026, 1, 2, 14, 0, tzinfo=timezone.utc), **args),
			datetime(2026, 1, 2, 14, 0, tzinfo=timezone.utc))
		self.assertEqual(latest_due_digest_slot(now=datetime(2026, 1, 4, 20, 0, tzinfo=timezone.utc), **args),
			datetime(2026, 1, 4, 14, 0, tzinfo=timezone.utc))

	def test_metadata_keeps_global_settings_and_adds_child_profile(self):
		from dinext_common.workflow_approval.metadata import get_workflow_approval_custom_fields
		fields = get_workflow_approval_custom_fields()
		state = {r["fieldname"]: r for r in fields["Workflow Document State"]}
		parent = {r["fieldname"]: r for r in fields["Workflow"]}
		self.assertIn("custom_group_send_times", parent)
		self.assertIn("custom_group_send_times", state)
		self.assertEqual(state["custom_email_settings_override"]["hidden"], 1)
		self.assertIn("custom_email_settings_reset", state)
		self.assertFalse(any(r["fieldtype"] == "Table" for r in state.values()))
