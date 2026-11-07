"""Preserve administrator email settings at Frappe's forced fixture-import boundary."""

import frappe

from dinext_common.workflow_approval.email_settings import PROFILE_FIELDS, value

PARENT_FIELDS = tuple("custom_workflow_action_email_template" if name == "next_action_email_template" else name for name in PROFILE_FIELDS) + (
    "send_email_alert", "custom_group_schedule_anchor", "custom_group_send_time", "custom_email_profile_version",
)
STATE_FIELDS = PROFILE_FIELDS + (
    "send_email", "custom_email_settings_override", "custom_email_settings_source", "custom_group_schedule_anchor",
)


def preserve_workflow_email_settings(doc, method=None):
    if not frappe.flags.in_fixtures or not doc.meta.has_field("custom_email_profile_version"):
        return
    if not frappe.db.exists("Workflow", doc.name):
        return
    existing = frappe.get_doc("Workflow", doc.name)
    if existing.get("custom_email_profile_version") != 1:
        from dinext_common.workflow_approval.email_migration import APPROVAL_STATES, _suppress_existing_corrections
        if doc.name in APPROVAL_STATES:
            # A fixture's version describes its defaults, not this site's completed upgrade.
            doc.custom_email_profile_version = 0
            _suppress_existing_corrections(doc.name)
        return
    for field in PARENT_FIELDS:
        doc.set(field, existing.get(field))
    states = {row.state: row for row in existing.states}
    for row in doc.states:
        if original := states.get(row.state):
            for field in STATE_FIELDS:
                row.set(field, original.get(field))
    transitions = {row.custom_transition_uuid: row for row in existing.transitions}
    for row in doc.transitions:
        if original := transitions.get(row.custom_transition_uuid):
            row.send_email_to_creator = original.send_email_to_creator


def preserve_email_template(doc, method=None):
    if not frappe.flags.in_fixtures or not frappe.db.exists("Email Template", doc.name):
        return
    from dinext_common.workflow_approval.email_templates import is_known_default_template
    existing = frappe.get_doc("Email Template", doc.name)
    if is_known_default_template(doc.name, existing):
        return
    for field in ("subject", "response", "response_html", "use_html"):
        doc.set(field, existing.get(field))
