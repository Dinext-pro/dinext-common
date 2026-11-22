import unittest
from types import SimpleNamespace as Row
from unittest.mock import Mock, patch

import frappe

from dinext_common.workflow_approval import email_import, email_migration, metadata


POLICY = {
    "workflow_fields": {
        "send_email_alert": 1,
        "custom_group_workflow_action_emails": 1,
        "custom_group_interval_unit": "Days",
        "custom_group_interval_value": 1,
        "custom_group_send_times": "09:30",
    },
    "enabled_states": ("Review", "Revise"),
    "state_overrides": {"Revise": {"custom_group_workflow_action_emails": 0,
                                   "next_action_email_template": "Owner Correction"}},
    "creator_notification_states": ("Revise",),
    "suppress_open_tasks_in_states": ("Revise",),
}
NOW = "2026-01-01 00:00:00"


class TestWorkflowEmailMigration(unittest.TestCase):
    def test_policy_is_supplied_by_owner(self):
        workflow = Row(
            states=[Row(state=name, send_email=1) for name in ("Editing", "Review", "Rejected", "Revise")],
            transitions=[Row(state=name, allow_self_approval=1) for name in ("Rejected", "Revise")],
        )
        email_migration.configure_workflow(workflow, profile={"migration": POLICY}, now=NOW)
        self.assertEqual(workflow.custom_group_send_times, "09:30")
        self.assertEqual([row.send_email for row in workflow.states], [0, 1, 0, 1])
        self.assertEqual(workflow.states[3].custom_email_settings_override, 1)
        self.assertEqual(workflow.states[3].next_action_email_template, "Owner Correction")
        self.assertFalse(hasattr(workflow.transitions[0], "send_email_to_creator"))
        self.assertEqual(workflow.transitions[1].send_email_to_creator, 1)

    def test_framework_legacy_time_does_not_skip_initial_policy(self):
        workflow = Row(
            send_email_alert=0, custom_group_send_time="13:42:27",
            states=[Row(state="Review")], transitions=[],
        )
        email_migration.configure_workflow(workflow, profile={"migration": POLICY}, now=NOW)
        self.assertEqual(workflow.send_email_alert, 1)
        self.assertEqual(workflow.custom_group_send_times, "09:30")
        self.assertEqual(workflow.custom_group_schedule_anchor, NOW)
        self.assertEqual(workflow.states[0].send_email, 1)
        self.assertEqual(workflow.custom_email_profile_version, 1)

    def test_preserves_legacy_time_for_an_active_digest(self):
        workflow = Row(
            send_email_alert=1, custom_group_workflow_action_emails=1,
            custom_group_interval_unit="Days", custom_group_interval_value=2, custom_group_send_time="13:42:00",
            states=[Row(state="Review", send_email=0)], transitions=[],
        )
        email_migration.configure_workflow(workflow, profile={"migration": POLICY}, now=NOW)
        self.assertEqual(workflow.custom_group_send_time, "13:42:00")
        self.assertEqual(workflow.custom_group_interval_value, 2)
        self.assertEqual(workflow.states[0].send_email, 0)
        self.assertEqual(workflow.custom_email_profile_version, 1)

    def test_preserves_existing_schedule_and_explicit_state_override(self):
        workflow = Row(
            custom_group_workflow_action_emails=1, custom_group_send_times="13:00",
            states=[Row(state="Review", send_email=0), Row(state="Revise", send_email=1,
                custom_email_settings_override=1, next_action_email_template="My Correction")],
            transitions=[],
        )
        email_migration.configure_workflow(workflow, profile={"migration": POLICY}, now=NOW)
        self.assertEqual(workflow.custom_group_send_times, "13:00")
        self.assertEqual(workflow.states[0].send_email, 0)
        self.assertEqual(workflow.states[1].next_action_email_template, "My Correction")
        self.assertEqual(workflow.custom_email_profile_version, 1)

    def test_preserves_native_template_on_unversioned_state(self):
        state = Row(state="Editing", send_email=1, next_action_email_template="Administrator Template")
        workflow = Row(states=[state], transitions=[])
        email_migration.configure_workflow(workflow, profile={"migration": POLICY}, now=NOW)
        self.assertEqual(state.next_action_email_template, "Administrator Template")
        self.assertEqual(state.send_email, 1)
        self.assertEqual(state.custom_email_settings_override, 1)
        self.assertEqual(state.custom_group_workflow_action_emails, 0)

    def test_missing_policy_leaves_existing_workflow_untouched(self):
        workflow = Row(custom_group_send_times="13:00")
        email_migration.configure_workflow(workflow, profile={}, now=NOW)
        self.assertEqual(vars(workflow), {"custom_group_send_times": "13:00"})

    def test_owner_callbacks_run_once_around_configuration(self):
        workflow = Mock()
        workflow.get.side_effect = [0, 1]
        before_save, after_save = Mock(), Mock()
        profile = {"workflow": "Review", "migration": POLICY,
                   "before_configure": before_save, "after_save": after_save}
        with (
            patch.object(email_migration.frappe.utils, "now_datetime", return_value=NOW),
            patch.object(email_migration.frappe, "db", Mock()),
            patch.object(email_migration.frappe, "get_doc", return_value=workflow),
            patch.object(email_migration, "domain_email_profiles", return_value={"Document": profile}),
            patch.object(metadata, "ensure_workflow_approval_email_templates"),
            patch.object(email_migration, "configure_workflow") as configure,
            patch.object(email_migration, "suppress_existing_notifications") as suppress,
        ):
            email_migration.ensure_email_profiles()
            email_migration.ensure_email_profiles()
        before_save.assert_called_once_with(workflow)
        configure.assert_called_once_with(workflow, profile=profile, now=NOW)
        workflow.save.assert_called_once_with(ignore_permissions=True)
        after_save.assert_called_once_with(workflow)
        self.assertEqual(suppress.call_count, 2)
        suppress.assert_called_with(workflow.name, ("Revise",))

    def test_fixture_import_keeps_existing_unversioned_settings(self):
        class Document(frappe._dict):
            def set(self, key, value):
                self[key] = value

        incoming = Document(
            name="Review", meta=Mock(), flags=frappe._dict(), custom_email_profile_version=1,
            custom_group_send_times="09:30",
            states=[Document(state="Review", send_email=1)], transitions=[],
        )
        existing = Document(
            custom_email_profile_version=0, custom_group_send_times="13:00",
            states=[Document(state="Review", send_email=0, next_action_email_template="Custom State")],
            transitions=[],
        )
        with (
            patch.object(email_import.frappe, "flags", frappe._dict(in_fixtures=True)),
            patch.object(email_import.frappe, "db", Mock()),
            patch.object(email_import.frappe, "get_doc", return_value=existing),
            patch.object(email_migration, "domain_email_profiles", return_value={}),
        ):
            email_import.preserve_workflow_email_settings(incoming)
        self.assertEqual(incoming.custom_email_profile_version, 0)
        self.assertEqual(incoming.custom_group_send_times, "13:00")
        self.assertEqual(incoming.states[0].send_email, 0)
        self.assertEqual(incoming.states[0].next_action_email_template, "Custom State")
        self.assertEqual(incoming.states[0].custom_email_settings_override, 1)
        self.assertIs(incoming.flags.workflow_before_fixture_import, existing)
