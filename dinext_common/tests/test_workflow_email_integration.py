import json
from datetime import datetime, timezone
from unittest.mock import patch

import frappe
from dinext_common.tests import test_workflow_approval_integration as base
from dinext_common.workflow_approval import notifications, engine


class TestWorkflowEmailIntegration(base.TestWorkflowApprovalIntegration):
    workflow_name = '_Test State Email Integration'

    def setUp(self):
        super().setUp()
        role='_Test State Email Approver'
        if not frappe.db.exists('Role',role):
            frappe.get_doc({'doctype':'Role','role_name':role}).insert(ignore_permissions=True)
        user=frappe.get_doc('User',self.user)
        if role not in [row.role for row in user.roles]:
            user.append('roles',{'role':role});user.save(ignore_permissions=True)
        if not frappe.db.exists('Custom DocPerm',{'parent':'Issue','role':role,'permlevel':0}):
            frappe.get_doc({'doctype':'Custom DocPerm','parent':'Issue','role':role,'permlevel':0,'read':1,'write':1}).insert(ignore_permissions=True)
        workflow=frappe.get_doc('Workflow',self.workflow_name)
        for row in workflow.transitions:row.allowed=role
        workflow.save(ignore_permissions=True)
        frappe.clear_cache()

    def _profile(self, *, grouped=False, creator=False):
        workflow = frappe.get_doc('Workflow', self.workflow_name)
        workflow.send_email_alert = 1
        workflow.custom_group_workflow_action_emails = int(grouped)
        workflow.custom_group_interval_unit = 'Days'
        workflow.custom_group_interval_value = 1
        workflow.custom_group_send_times = '08:00, 17:00'
        workflow.custom_workflow_action_email_template = 'Dinext Workflow Action'
        for row in workflow.states:
            row.send_email = 1
        for row in workflow.transitions:
            row.send_email_to_creator = int(creator)
        workflow.save(ignore_permissions=True)
        return workflow

    def _source_and_task(self, *, owner=False):
        if owner:
            frappe.set_user(self.user)
        source=frappe.get_doc({'doctype':'Issue','subject':'State email integration','status':'Open'}).insert(ignore_permissions=True)
        frappe.set_user('Administrator')
        name=frappe.db.get_value('Workflow Task',{'reference_doctype':'Issue','reference_name':source.name,'approver':self.user,'status':'Working'},'name')
        self.assertTrue(name)
        return source,frappe.get_doc('Workflow Task',name)

    def test_current_creator_flag_controls_existing_task_and_retry(self):
        source, task=self._source_and_task(owner=True)
        self._profile(creator=False)
        with patch.object(notifications,'_sendmail_for_user') as send, patch.object(notifications,'_queued_delivery',return_value=False):
            notifications.send_immediate_notification(task.name)
            send.assert_not_called()
            self._profile(creator=True)
            notifications.send_immediate_notification(task.name)
            self.assertEqual(send.call_count,1)
            self.assertEqual(send.call_args.kwargs['reply_to'],'ikhmel@dinext.ru')
            notifications.send_immediate_notification(task.name)
            self.assertEqual(send.call_count,1)

    def test_global_and_state_gates_are_rechecked(self):
        source,task=self._source_and_task()
        workflow=self._profile()
        workflow.states[0].send_email=0
        workflow.save(ignore_permissions=True)
        with patch.object(notifications,'_sendmail_for_user') as send:
            notifications.send_immediate_notification(task.name)
            send.assert_not_called()
        workflow.states[0].send_email=1
        workflow.send_email_alert=0
        workflow.save(ignore_permissions=True)
        with patch.object(notifications,'_sendmail_for_user') as send:
            notifications.send_immediate_notification(task.name)
            send.assert_not_called()

    def test_closed_task_does_not_send(self):
        source,task=self._source_and_task()
        self._profile()
        frappe.db.set_value('Workflow Task',task.name,'status','Cancelled',update_modified=False)
        with patch.object(notifications,'_sendmail_for_user') as send:
            notifications.send_immediate_notification(task.name)
            send.assert_not_called()

    def test_digest_repeats_next_slot_but_not_same_slot(self):
        source,task=self._source_and_task()
        workflow=self._profile(grouped=True)
        action=frappe.get_doc('Workflow Action',frappe.db.get_value('Workflow Action',{'custom_workflow_task':task.name},'name'))
        first=datetime(2039,1,3,5,0,tzinfo=timezone.utc)
        second=datetime(2039,1,3,14,0,tzinfo=timezone.utc)
        with patch.object(notifications,'_sendmail_for_user') as send, patch.object(notifications,'_queued_delivery',return_value=False):
            notifications.send_digest(workflow,self.user,[action],first,state='Open')
            self.assertEqual(send.call_count,1)
            notifications.send_digest(workflow,self.user,[action],first,state='Open')
            self.assertEqual(send.call_count,1)
            notifications.send_digest(workflow,self.user,[action],second,state='Open')
            self.assertEqual(send.call_count,2)

    def test_finished_transition_supplies_exact_entry_comment(self):
        source,task=self._source_and_task()
        frappe.set_user(task.approver)
        result=engine.cast_vote(task.name,transition_uuid=task.available_workflow_transitions[0].transition_uuid,
            comment='Correct this source only',request_id='email-entry-context')
        self.assertTrue(result['transitioned'],(result,frappe.flags.workflow_finalization_errors))
        next_name=frappe.db.get_value('Workflow Task',{'reference_name':source.name,'workflow_state':'Closed','status':'Working'},'name')
        self.assertTrue(next_name)
        manifest=json.loads(frappe.db.get_value('Workflow Task',next_name,'round_manifest'))
        self.assertEqual(manifest['entry_context']['comments'][0]['text'],'Correct this source only')
        self.assertEqual(manifest['entry_context']['round_id'],task.approval_round_id)

    def test_custom_template_is_preserved(self):
        from dinext_common.workflow_approval.metadata import ensure_workflow_approval_email_templates
        template=frappe.get_doc('Email Template','Dinext Workflow Correction')
        original={field:template.get(field) for field in ('subject','response_html')}
        try:
            template.subject='Customer-specific correction'
            template.response_html='<p>Keep my text</p>'
            template.save(ignore_permissions=True)
            ensure_workflow_approval_email_templates()
            self.assertEqual(frappe.db.get_value('Email Template',template.name,'subject'),'Customer-specific correction')
        finally:
            frappe.db.set_value('Email Template',template.name,original)

    def test_creator_flag_filters_digest_and_changes_before_next_slot(self):
        source,task=self._source_and_task(owner=True)
        workflow=self._profile(grouped=True,creator=False)
        action=frappe.get_doc('Workflow Action',frappe.db.get_value('Workflow Action',{'custom_workflow_task':task.name},'name'))
        first=datetime(2039,1,3,5,0,tzinfo=timezone.utc)
        second=datetime(2039,1,3,14,0,tzinfo=timezone.utc)
        with patch.object(notifications,'_sendmail_for_user') as send, patch.object(notifications,'_queued_delivery',return_value=False):
            notifications.send_digest(workflow,self.user,[action],first,state='Open')
            send.assert_not_called()
            workflow=self._profile(grouped=True,creator=True)
            notifications.send_digest(workflow,self.user,[action],first,state='Open')
            self.assertEqual(send.call_count,1)
            workflow=self._profile(grouped=True,creator=False)
            notifications.send_digest(workflow,self.user,[action],second,state='Open')
            self.assertEqual(send.call_count,1)

    def test_one_workflow_can_send_digest_and_immediate_for_different_states(self):
        source,task=self._source_and_task()
        workflow=self._profile(grouped=True)
        state=workflow.states[1]
        state.custom_email_settings_override=1
        state.custom_group_workflow_action_emails=0
        state.next_action_email_template='Dinext Workflow Correction'
        workflow.save(ignore_permissions=True)
        with patch.object(frappe,'enqueue'):
            frappe.set_user(task.approver)
            result=engine.cast_vote(task.name,transition_uuid=task.available_workflow_transitions[0].transition_uuid,
                comment='Mixed mode correction',request_id='email-mixed-mode')
        self.assertTrue(result['transitioned'],(result,frappe.flags.workflow_finalization_errors))
        frappe.set_user('Administrator')
        closed=frappe.db.get_value('Workflow Task',{'reference_name':source.name,'workflow_state':'Closed','approver':self.user,'status':'Working'},'name')
        other,open_task=self._source_and_task()
        action=frappe.get_doc('Workflow Action',frappe.db.get_value('Workflow Action',{'custom_workflow_task':open_task.name},'name'))
        with patch.object(notifications,'_sendmail_for_user') as send,patch.object(notifications,'_queued_delivery',return_value=False):
            notifications.send_immediate_notification(closed)
            notifications.send_digest(workflow,self.user,[action],datetime(2039,1,3,5,tzinfo=timezone.utc),state='Open')
            self.assertEqual(send.call_count,2)
            self.assertIn('Mixed mode correction',send.call_args_list[0].kwargs['args']['message'])
            self.assertIn('Open',send.call_args_list[1].kwargs['subject'])

    def test_transaction_rollback_drops_pending_email_dispatch(self):
        self._profile()
        with patch('frappe.utils.background_jobs.get_queue') as get_queue, patch.object(notifications,'_sendmail_for_user') as send:
            with patch.dict(frappe.flags,{'in_test':False}):
                source=frappe.get_doc({'doctype':'Issue','subject':'Rollback state email','status':'Open'}).insert(ignore_permissions=True)
                name=source.name
                send.assert_not_called()
                frappe.db.rollback()
                frappe.db.after_commit.run()
            send.assert_not_called()
            self.assertFalse(frappe.db.exists('Email Queue',{'reference_name':name}))
            mail_jobs=[call for call in get_queue.return_value.enqueue_call.call_args_list if 'send_immediate_notification' in repr(call)]
            self.assertEqual(mail_jobs,[])

    def test_domain_cascade_records_its_own_reason(self):
        source,task=self._source_and_task()
        engine.apply_domain_transition('Issue',source.name,'Closed',reason='Cascade from parent test',actor=self.user)
        task_name=frappe.db.get_value('Workflow Task',{'reference_name':source.name,'workflow_state':'Closed','status':'Working'},'name')
        manifest=json.loads(frappe.db.get_value('Workflow Task',task_name,'round_manifest'))
        self.assertEqual(manifest['entry_context']['kind'],'domain')
        self.assertEqual(manifest['entry_context']['comments'][0]['text'],'Cascade from parent test')
        self.assertTrue(manifest['entry_context']['comments'][0]['system'])
