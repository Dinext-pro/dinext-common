"""Use the platform's existing email notification-type allowlist."""

import frappe

MIGRATION_KEY="dinext_workflow_email_preferences_v1"


def ensure_type():
    if not frappe.db.exists("Notification Type","Workflow"):
        frappe.get_doc(dict(doctype="Notification Type",type_name="Workflow",enabled=1)).insert(ignore_permissions=True)


def email_allowed(user):
    from frappe.desk.doctype.notification_settings.notification_settings import is_email_notifications_enabled_for_type
    return bool(is_email_notifications_enabled_for_type(user,"Workflow"))


def migrate_preferences():
    ensure_type()
    if frappe.db.get_default(MIGRATION_KEY):
        return
    # Trusted one-time data migration, preserving deliberate empty allowlists/master off.
    for name in frappe.get_all("Notification Settings",filters={"enable_email_notifications":1},pluck="name"):
        settings=frappe.get_doc("Notification Settings",name)
        chosen={row.notification_type for row in settings.email_notification_types}
        if chosen and "Workflow" not in chosen:
            settings.append("email_notification_types",{"notification_type":"Workflow"})
            settings.save(ignore_permissions=True)
    frappe.db.set_default(MIGRATION_KEY,1)
