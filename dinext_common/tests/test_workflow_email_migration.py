import unittest
from types import SimpleNamespace as Row


class Workflow(Row):
    def append(self, table, values):
        getattr(self, table).append(Row(**values))


class TestWorkflowEmailMigration(unittest.TestCase):
    def test_approval_inherits_and_rejection_overrides(self):
        from dinext_common.workflow_approval.email_migration import configure_workflow
        w = Workflow(name='AFL Workflow', states=[Row(state='Editing'), Row(state='Pending Approval'), Row(state='Rejected')],
            transitions=[Row(state='Rejected', allow_self_approval=1)])
        configure_workflow(w, now='2026-01-01 00:00:00')
        self.assertEqual(w.custom_group_send_times,'08:00, 17:00')
        self.assertEqual(w.states[0].send_email,0)
        self.assertEqual(w.states[1].custom_email_settings_override,0)
        self.assertEqual(w.states[2].custom_email_settings_override,1)
        self.assertEqual(w.states[2].custom_group_workflow_action_emails,0)
        self.assertEqual(w.transitions[0].send_email_to_creator,1)

    def test_goal_has_rejected_and_creator_only_return(self):
        from dinext_common.workflow_approval.email_migration import configure_workflow
        w = Workflow(name='Goal Approval', states=[Row(state='Draft'),Row(state='Parent Approval'),Row(state='Finance Approval')],
            transitions=[Row(state='Parent Approval',action='Reject',next_state='Draft'),Row(state='Finance Approval',action='Reject',next_state='Draft')])
        configure_workflow(w,now='2026-01-01 00:00:00')
        self.assertEqual([t.next_state for t in w.transitions[:2]],['Rejected','Rejected'])
        returns=[t for t in w.transitions if t.state=='Rejected']
        self.assertEqual(len(returns),1)
        self.assertEqual(returns[0].next_state,'Draft')
        self.assertEqual(returns[0].condition,'doc.owner == frappe.session.user')
        self.assertEqual(returns[0].send_email_to_creator,1)
