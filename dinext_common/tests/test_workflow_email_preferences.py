import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkflowEmailPreferences(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.user="workflow-preferences-"+frappe.generate_hash(length=8)+"@example.test"
        frappe.get_doc(dict(doctype="User",email=self.user,first_name="Workflow preferences",
            enabled=1,send_welcome_email=0)).insert(ignore_permissions=True)

    def test_standard_type_controls_all_workflow_mail_and_empty_is_optout(self):
        from dinext_common.workflow_approval.email_preferences import email_allowed
        settings=frappe.get_doc("Notification Settings",self.user)
        self.assertTrue(email_allowed(self.user))
        settings.set("email_notification_types",[]);settings.save(ignore_permissions=True)
        frappe.clear_document_cache("Notification Settings",self.user)
        self.assertFalse(email_allowed(self.user))
        settings.append("email_notification_types",{"notification_type":"Workflow"})
        settings.enable_email_notifications=0;settings.save(ignore_permissions=True)
        frappe.clear_document_cache("Notification Settings",self.user)
        self.assertFalse(email_allowed(self.user))

    def test_migration_does_not_reenable_empty_or_master_off(self):
        from dinext_common.workflow_approval.email_preferences import migrate_preferences
        settings=frappe.get_doc("Notification Settings",self.user)
        settings.set("email_notification_types",[]);settings.save(ignore_permissions=True)
        migrate_preferences()
        settings.reload()
        self.assertFalse(settings.email_notification_types)
