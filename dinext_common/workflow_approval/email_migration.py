"""One-time approved defaults; later administrator changes remain authoritative."""

import frappe

from dinext_common.workflow_approval.email_settings import PROFILE_FIELDS, value
from dinext_common.workflow_approval.email_templates import domain_email_profiles

def _provided_profiles():
	return {profile["workflow"]: profile for profile in domain_email_profiles().values()}


def supported_workflow_names():
	return dict.fromkeys(_provided_profiles())


def configure_workflow(workflow, *, profile, now):
	states = profile.get("approval_states", ())
	workflow.send_email_alert = 1
	workflow.custom_group_workflow_action_emails = 1
	workflow.custom_group_interval_unit = "Days"
	workflow.custom_group_interval_value = 1
	workflow.custom_group_send_times = "08:00, 17:00"
	workflow.custom_group_send_time = "08:00:00"
	workflow.custom_group_schedule_anchor = now
	workflow.custom_group_email_template = profile.get("digest_template", "Dinext Workflow Digest")
	workflow.custom_workflow_action_email_template = "Dinext Workflow Action"
	workflow.custom_attach_document_pdf = 0
	for row in workflow.states:
		rejected = row.state in {"Rejected", "Отклонено"}
		row.send_email = int(rejected or row.state in states)
		row.custom_email_settings_override = int(rejected)
		for field in PROFILE_FIELDS:
			setattr(row, field, value(workflow, "custom_workflow_action_email_template" if field == "next_action_email_template" else field))
		row.custom_group_schedule_anchor = now
		if rejected:
			row.custom_group_workflow_action_emails = 0
			row.next_action_email_template = profile.get("correction_template", "Dinext Workflow Correction")
	for transition in workflow.transitions:
		if transition.state in {"Rejected", "Отклонено"} and value(transition, "allow_self_approval"):
			transition.send_email_to_creator = 1
	workflow.custom_email_profile_version = 1


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
		if workflow.get("custom_email_profile_version") == 1:
			continue
		_suppress_existing_corrections(workflow.name)
		if before_configure := profile.get("before_configure"):
			before_configure(workflow)
		configure_workflow(workflow, profile=profile, now=frappe.utils.now_datetime())
		workflow.save(ignore_permissions=True)
		if after_save := profile.get("after_save"):
			after_save(workflow)
			_suppress_existing_corrections(workflow.name)


def _suppress_existing_corrections(workflow_name):
	old_tasks = frappe.get_all("Workflow Task", filters={"workflow": workflow_name,
		"workflow_state": ("in", ("Rejected", "Отклонено")), "status": "Working", "round_status": "Open"}, pluck="name")
	if old_tasks:
		frappe.db.set_value("Workflow Action", {"custom_workflow_task": ("in", old_tasks), "status": "Open"},
			{"custom_notification_suppressed": 1, "custom_notification_status": "Skipped"}, update_modified=False)
