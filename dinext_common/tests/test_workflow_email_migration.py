import unittest
from types import SimpleNamespace as Row
from unittest.mock import Mock, patch


class TestWorkflowEmailMigration(unittest.TestCase):
    def test_approval_inherits_and_rejection_overrides(self):
        from dinext_common.workflow_approval.email_migration import configure_workflow

        workflow = Row(states=[Row(state="Editing"), Row(state="Review"), Row(state="Rejected")],
            transitions=[Row(state="Rejected", allow_self_approval=1)])
        configure_workflow(workflow, profile={"approval_states": ("Review",)}, now="2026-01-01 00:00:00")
        self.assertEqual(workflow.custom_group_send_times, "08:00, 17:00")
        self.assertEqual(workflow.states[0].send_email, 0)
        self.assertEqual(workflow.states[1].send_email, 1)
        self.assertEqual(workflow.states[2].custom_email_settings_override, 1)
        self.assertEqual(workflow.states[2].custom_group_workflow_action_emails, 0)
        self.assertEqual(workflow.transitions[0].send_email_to_creator, 1)

    def test_owner_callbacks_run_once_around_configuration(self):
        from dinext_common.workflow_approval import email_migration as migration, metadata

        workflow = Mock()
        workflow.get.side_effect = [0, 1]
        before_save, after_save = Mock(), Mock()
        profile = {"workflow": "Review", "before_configure": before_save, "after_save": after_save}
        with patch.object(migration.frappe.utils, "now_datetime", return_value="2026-11-07 10:00:00"), \
                patch.object(migration.frappe, "db", Mock()), \
                patch.object(migration.frappe, "get_doc", return_value=workflow), \
                patch.object(migration, "domain_email_profiles", return_value={"Document": profile}), \
                patch.object(metadata, "ensure_workflow_approval_email_templates"), \
                patch.object(migration, "configure_workflow") as configure, \
                patch.object(migration, "_suppress_existing_corrections"):
            migration.ensure_email_profiles()
            migration.ensure_email_profiles()
        before_save.assert_called_once_with(workflow)
        configure.assert_called_once_with(workflow, profile=profile, now="2026-11-07 10:00:00")
        workflow.save.assert_called_once_with(ignore_permissions=True)
        after_save.assert_called_once_with(workflow)
