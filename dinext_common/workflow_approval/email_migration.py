"""One-time approved defaults; later administrator changes remain authoritative."""

import frappe

from dinext_common.workflow_approval.email_settings import PROFILE_FIELDS, value

APPROVAL_STATES = {
	"UTP Workflow": ("Pending Approval",),
	"AFL Workflow": ("Pending Approval",),
	"Goal Approval": ("Parent Approval", "Finance Approval"),
	"Dinext Project Scorecard Approval": ("Submitted for Review", "Reviewed"),
	"Dinext Budget Approval": ("Pending Approval",),
	"Project Stage Workflow": (),
	"Project Gate Checkpoint Workflow": ("In Review",),
	"Project Approval": ("На согласовании",),
	"Purchase_Invoice_Workflow": ("На согласовании",),
	"Sales_Invoice_Workflow": ("На согласовании",),
	"Expense_Claim_Workflow": ("Pending Approval",),
}


def configure_workflow(workflow, *, now):
	timesheets = workflow.name == "UTP Workflow"
	workflow.send_email_alert = 1
	workflow.custom_group_workflow_action_emails = 1
	workflow.custom_group_interval_unit = "Days"
	workflow.custom_group_interval_value = 1
	workflow.custom_group_send_times = "08:00, 17:00"
	workflow.custom_group_send_time = "08:00:00"
	workflow.custom_group_schedule_anchor = now
	workflow.custom_group_email_template = "Dinext Timesheet Workflow Digest" if timesheets else "Dinext Workflow Digest"
	workflow.custom_workflow_action_email_template = "Dinext Workflow Action"
	workflow.custom_attach_document_pdf = 0
	if workflow.name in {"Goal Approval", "Expense_Claim_Workflow"}:
		if not any(row.state == "Rejected" for row in workflow.states):
			workflow.append("states", {"state": "Rejected", "doc_status": "0", "is_optional_state": 1,
				"update_field": "status", "update_value": "Rejected", "allow_edit": "All"})
		if workflow.name == "Goal Approval":
			for transition in workflow.transitions:
				if value(transition, "action") == "Reject":
					transition.next_state = "Rejected"
		if not any(row.state == "Rejected" and row.next_state == "Draft" for row in workflow.transitions):
			workflow.append("transitions", {"state": "Rejected", "action": "Edit", "next_state": "Draft",
				"allowed": "All", "allow_self_approval": 1, "send_email_to_creator": 1,
				"condition": "doc.owner == frappe.session.user", "custom_parallel_approval_policy": "Any"})
	for row in workflow.states:
		rejected = row.state in {"Rejected", "Отклонено"}
		row.send_email = int(rejected or row.state in APPROVAL_STATES[workflow.name])
		row.custom_email_settings_override = int(rejected)
		for field in PROFILE_FIELDS:
			setattr(row, field, value(workflow, "custom_workflow_action_email_template" if field == "next_action_email_template" else field))
		row.custom_group_schedule_anchor = now
		if rejected:
			row.custom_group_workflow_action_emails = 0
			row.next_action_email_template = "Dinext Timesheet Workflow Correction" if timesheets else "Dinext Workflow Correction"
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
	for name in APPROVAL_STATES:
		if not frappe.db.exists("Workflow", {"name": name, "is_active": 1}):
			continue
		workflow = frappe.get_doc("Workflow", name)
		if workflow.get("custom_email_profile_version") == 1:
			continue
		_suppress_existing_corrections(workflow.name)
		configure_workflow(workflow, now=frappe.utils.now_datetime())
		workflow.save(ignore_permissions=True)
		if name == "Goal Approval":
			_rebuild_goal_rounds()
			_suppress_existing_corrections(workflow.name)


def _rebuild_goal_rounds():
	from dinext_common.workflow_approval import engine
	rows = frappe.get_all("Workflow Task", filters={"workflow": "Goal Approval", "round_status": "Open"},
		fields=["reference_name", "approval_round_id"], distinct=True)
	for row in rows:
		source = frappe.get_doc("Goal", row.reference_name)
		engine.reconcile_source(source)
		if frappe.db.get_value("Workflow Task", {"approval_round_id": row.approval_round_id}, "round_status") == "Conflicted":
			engine.rebuild_configuration_conflict(source, row.approval_round_id, frappe._("Workflow email settings migration"))


def _suppress_existing_corrections(workflow_name):
	old_tasks = frappe.get_all("Workflow Task", filters={"workflow": workflow_name,
		"workflow_state": ("in", ("Rejected", "Отклонено")), "status": "Working", "round_status": "Open"}, pluck="name")
	if old_tasks:
		frappe.db.set_value("Workflow Action", {"custom_workflow_task": ("in", old_tasks), "status": "Open"},
			{"custom_notification_suppressed": 1, "custom_notification_status": "Skipped"}, update_modified=False)
