"""One-time approved defaults; later administrator changes remain authoritative."""

import frappe

from dinext_common.workflow_approval.email_settings import PROFILE_FIELDS, assign, checked, value
from dinext_common.workflow_approval.email_templates import domain_email_profiles


def _parent_field(field):
	return "custom_workflow_action_email_template" if field == "next_action_email_template" else field


_WORKFLOW_POLICY_FIELDS = frozenset(map(_parent_field, PROFILE_FIELDS)) | {
	"send_email_alert", "custom_group_send_time",
}


def _provided_profiles():
	return {
		profile["workflow"]: profile
		for profile in domain_email_profiles().values()
		if profile.get("migration")
	}


def migration_policy_for(workflow_name):
	return _provided_profiles().get(workflow_name, {}).get("migration", {})


def native_state_template(row, parent_template):
	template = value(row, "next_action_email_template")
	if template and template != parent_template:
		return template


def _has_configured_mail(workflow):
	"""Recognize an existing schedule, selected templates or an explicit parent setting."""
	# Frappe supplies a current time for Time fields even without a configured digest.
	return any(
		value(workflow, field)
		for field in (
			"custom_group_schedule_anchor", "custom_group_send_times", "custom_group_email_template",
			"custom_workflow_action_email_template",
		)
	) or any(
		checked(value(workflow, field))
		for field in ("custom_group_workflow_action_emails", "custom_attach_document_pdf")
	)


def configure_workflow(workflow, *, profile, now):
	policy = profile.get("migration")
	if not policy:
		return

	parent_template = value(workflow, "custom_workflow_action_email_template")
	configured = _has_configured_mail(workflow)
	if not configured:
		for field, setting in policy["workflow_fields"].items():
			if field in _WORKFLOW_POLICY_FIELDS:
				assign(workflow, field, setting)
		assign(workflow, "custom_group_schedule_anchor", now)

	states = policy.get("enabled_states", ())
	overrides = policy.get("state_overrides", {})
	for row in workflow.states:
		if checked(value(row, "custom_email_settings_override")):
			continue
		template = native_state_template(row, parent_template)
		if configured and value(row, "send_email") is not None and not template:
			continue
		state_override = overrides.get(row.state, {})
		if template:
			state_override = {
				**state_override,
				"next_action_email_template": template,
				"custom_group_workflow_action_emails": int(
					checked(value(row, "custom_group_workflow_action_emails"))
				),
			}
		enabled = checked(value(row, "send_email")) if template else row.state in states
		assign(row, "send_email", int(enabled))
		assign(row, "custom_email_settings_override", int(bool(state_override)))
		for field in PROFILE_FIELDS:
			assign(row, field, state_override.get(field, value(workflow, _parent_field(field))))
		assign(row, "custom_group_schedule_anchor", value(workflow, "custom_group_schedule_anchor") or now)

	creator_notification_states = policy.get("creator_notification_states", ())
	for transition in workflow.transitions:
		if (
			transition.state in creator_notification_states
			and checked(value(transition, "allow_self_approval"))
			and (not configured or value(transition, "send_email_to_creator") is None)
		):
			assign(transition, "send_email_to_creator", 1)
	assign(workflow, "custom_email_profile_version", 1)


def ensure_email_profiles():
	"""Run after all apps' fixtures; configure each known process only once."""
	if not frappe.db.has_column("Workflow", "custom_email_profile_version"):
		return
	from dinext_common.workflow_approval.metadata import ensure_workflow_approval_email_templates
	ensure_workflow_approval_email_templates()
	for name, profile in _provided_profiles().items():
		if not frappe.db.exists("Workflow", {"name": name, "is_active": 1}):
			continue
		workflow = frappe.get_doc("Workflow", name)
		if workflow.get("custom_email_profile_version"):
			continue
		suppressed_states = profile["migration"].get("suppress_open_tasks_in_states", ())
		suppress_existing_notifications(workflow.name, suppressed_states)
		if before_configure := profile.get("before_configure"):
			before_configure(workflow)
		configure_workflow(workflow, profile=profile, now=frappe.utils.now_datetime())
		workflow.save(ignore_permissions=True)
		if after_save := profile.get("after_save"):
			after_save(workflow)
			suppress_existing_notifications(workflow.name, suppressed_states)


def suppress_existing_notifications(workflow_name, states):
	if not states:
		return
	old_tasks = frappe.get_all("Workflow Task", filters={"workflow": workflow_name,
		"workflow_state": ("in", states), "status": "Working", "round_status": "Open"}, pluck="name")
	if old_tasks:
		frappe.db.set_value("Workflow Action", {"custom_workflow_task": ("in", old_tasks), "status": "Open"},
			{"custom_notification_suppressed": 1, "custom_notification_status": "Skipped"}, update_modified=False)
