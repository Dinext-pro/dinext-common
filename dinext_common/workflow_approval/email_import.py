"""Preserve administrator email settings at Frappe's forced fixture-import boundary."""

import frappe

from dinext_common.workflow_approval.email_settings import PROFILE_FIELDS
from dinext_common.workflow_approval.email_migration import (
    migration_policy_for,
    native_state_template,
    suppress_existing_notifications,
)

PARENT_FIELDS = tuple("custom_workflow_action_email_template" if name == "next_action_email_template" else name for name in PROFILE_FIELDS) + (
    "send_email_alert", "custom_group_schedule_anchor", "custom_group_send_time", "custom_email_profile_version",
)
STATE_FIELDS = PROFILE_FIELDS + (
    "send_email", "custom_email_settings_override", "custom_email_settings_source", "custom_group_schedule_anchor",
)


def preserve_workflow_email_settings(doc, method=None):
    if not frappe.flags.in_fixtures or not frappe.db.exists("Workflow", doc.name):
        return
    existing = frappe.get_doc("Workflow", doc.name)
    # A forced fixture import removes the previous Workflow before save validation.
    doc.flags.workflow_before_fixture_import = existing
    if not doc.meta.has_field("custom_email_profile_version"):
        return
    unversioned = not existing.get("custom_email_profile_version")
    if unversioned:
        policy = migration_policy_for(doc.name)
        suppress_existing_notifications(doc.name, policy.get("suppress_open_tasks_in_states", ()))
    # A fixture's version describes its defaults, not this site's completed upgrade.
    for field in PARENT_FIELDS:
        doc.set(field, existing.get(field))
    states = {row.state: row for row in existing.states}
    for row in doc.states:
        if original := states.get(row.state):
            for field in STATE_FIELDS:
                row.set(field, original.get(field))
            if unversioned and native_state_template(original, existing.get("custom_workflow_action_email_template")):
                row.custom_email_settings_override = 1
    transitions = {row.custom_transition_uuid: row for row in existing.transitions if row.custom_transition_uuid}
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
