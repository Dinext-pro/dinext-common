"""Run-owned Workflow form fixture for local email-profile acceptance."""

import frappe
from unittest.mock import patch
from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_user, _ensure_role

NAME = '_Cypress Workflow Email Profiles'
EDITOR = 'cy.workflow.email@example.com'
ROLE = NAME + ' Reader'


def _guard():
    frappe.only_for('System Manager')
    if frappe.local.site != 'localhost' and not frappe.conf.get('workflow_email_test_site'):
        raise frappe.PermissionError('Workflow email fixtures require a local test site')


def cleanup():
    _guard()
    if frappe.db.exists('Workflow', NAME):
        frappe.delete_doc('Workflow', NAME, force=True, ignore_permissions=True)
    if frappe.db.exists('User', EDITOR):
        frappe.delete_doc('User', EDITOR, force=True, ignore_permissions=True)
    frappe.db.delete('Custom DocPerm', {'name': NAME})
    for dt in ('DocPerm','Custom DocPerm','DocType Permission Condition'):
        frappe.db.delete(dt,{'role':ROLE})
    if frappe.db.exists('Role',ROLE):frappe.delete_doc('Role',ROLE,force=True,ignore_permissions=True)
    frappe.cache.delete_value('doctype_permission_map')
    frappe.clear_cache()
    return {'cleaned': True}


def seed():
    _guard()
    cleanup()
    from dinext_common.tests import approval_workspace_ui
    _ensure_role(ROLE)
    with patch.object(approval_workspace_ui,'READER_ROLE',ROLE):
        approval_workspace_ui._grant_fixture_read('Kanban Board')
    _ensure_user(EDITOR, 'Workflow Email Editor', ['System Manager', 'Desk User', 'Dinext_UT_Full_Access',ROLE])
    frappe.db.set_value('User', EDITOR, 'language', 'ru')
    permission = frappe.get_doc({'doctype':'Custom DocPerm','name':NAME,'parent':'Workflow',
        'parenttype':'DocType','parentfield':'permissions','role':'System Manager',
        'permlevel':0,'read':1,'write':1,'create':1,'delete':1})
    permission.db_insert()
    frappe.get_doc({'doctype':'Workflow','workflow_name':NAME,'document_type':'User Timesheet Position',
        'workflow_state_field':'workflow_state','is_active':0,'send_email_alert':1,
        'custom_group_workflow_action_emails':1,'custom_group_interval_unit':'Days',
        'custom_group_interval_value':1,'custom_group_send_times':'08:00, 17:00',
        'custom_group_email_template':'Dinext Workflow Digest',
        'states':[{'state':'Editing','doc_status':'0','allow_edit':'All','send_email':1},
            {'state':'Rejected','doc_status':'0','allow_edit':'All','send_email':1,
             'custom_email_settings_override':1,'custom_group_workflow_action_emails':0,
             'next_action_email_template':'Dinext Workflow Correction'}],
    }).insert(ignore_permissions=True)
    frappe.clear_cache()
    return {'workflow':NAME,'editor':EDITOR,'password':PASSWORD}
