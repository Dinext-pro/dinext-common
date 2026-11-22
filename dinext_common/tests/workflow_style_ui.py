"""Synthetic fixtures restricted to the isolated Workflow style test site."""

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

DOCTYPE = "Workflow Style Fixture"
PREFIX = "_Workflow Style "
STYLES = ("Primary", "Info", "Success", "Warning", "Danger", "Inverse", "")


def _guard():
	if not frappe.conf.get("workflow_style_test_site"):
		raise frappe.PermissionError("Workflow style fixtures require the isolated test site")


def _master(doctype, name, **values):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(ignore_permissions=True)


def _task(source, workflow, transitions, suffix, *, prefix=PREFIX):
	task = frappe.get_doc(
		{
			"doctype": "Workflow Task",
			"name": prefix + "Task " + suffix,
			"workflow": workflow.name,
			"reference_doctype": source.doctype,
			"reference_name": source.name,
			"doc": source.doctype,
			"wt_docname": source.name,
			"workflow_state": source.get(workflow.workflow_state_field),
			"approver": "Administrator",
			"status": "Working",
			"round_status": "Open",
			"approval_round_id": "style-" + suffix,
			"round_manifest": "{}",
			"source_created_at": source.creation,
		}
	)
	task.db_insert()
	frappe.db.set_value("Workflow Task", task.name, "_assign", frappe.as_json(["Administrator"]))
	for transition in transitions:
		task.append(
			"available_workflow_transitions",
			{
				"action": transition.action,
				"next_state": transition.next_state,
				"state": transition.state,
				"transition_uuid": transition.custom_transition_uuid,
				"allowed_role": "System Manager",
				"policy": "Any",
				"threshold": 1,
			},
		).db_insert()
	return task


@whitelist_for_tests
def seed_workflow_styles():
	_guard()
	cleanup_workflow_styles()
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": DOCTYPE,
			"module": "Custom",
			"custom": 1,
			"autoname": "hash",
			"title_field": "subject",
			"fields": [
				{"fieldname": "subject", "fieldtype": "Data", "label": "Subject", "in_list_view": 1},
				{"fieldname": "status", "fieldtype": "Data", "label": "Status", "in_list_view": 1},
			],
			"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
		}
	).insert(ignore_permissions=True)
	start = PREFIX + "Start"
	_master("Workflow State", start, workflow_state_name=start, style="")
	transitions = []
	states = [{"state": start, "doc_status": "0", "allow_edit": "System Manager"}]
	for style in STYLES:
		name = PREFIX + (style or "Neutral")
		_master("Workflow State", name, workflow_state_name=name, style=style)
		action = (
			"Style approve"
			if style == "Success"
			else "Style reject"
			if style == "Danger"
			else "Style " + (style or "neutral")
		)
		_master(
			"Workflow Action Master",
			action,
			workflow_action_name=action,
			custom_icon="check" if style == "Success" else "close" if style == "Danger" else "",
		)
		states.append({"state": name, "doc_status": "0", "allow_edit": "System Manager"})
		transitions.append(
			{
				"state": start,
				"action": action,
				"next_state": name,
				"allowed": "System Manager",
				"allow_self_approval": 1,
			}
		)
	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": PREFIX + "Main",
			"document_type": DOCTYPE,
			"workflow_state_field": "status",
			"is_active": 1,
			"send_email_alert": 0,
			"states": states,
			"transitions": transitions,
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(doctype=DOCTYPE)
	source = frappe.get_doc(
		{"doctype": DOCTYPE, "name": PREFIX + "Example", "subject": "Workflow style example", "status": start}
	)
	source.db_insert()
	task = _task(source, workflow, workflow.transitions, "main")
	result = {
		"doctype": DOCTYPE,
		"name": source.name,
		"task": task.name,
		"states": {style or "Neutral": PREFIX + (style or "Neutral") for style in STYLES},
	}
	return result


@whitelist_for_tests
def set_workflow_style(state, style):
	_guard()
	if not state.startswith(PREFIX) or style not in STYLES:
		raise frappe.PermissionError("Only owned fixture states may be changed")
	frappe.db.set_value("Workflow State", state, "style", style)
	frappe.clear_cache(doctype=DOCTYPE)


@whitelist_for_tests
def cleanup_workflow_styles():
	_guard()
	for doctype, filters in (
		("Workflow Task", {"name": ["like", PREFIX + "%"]}),
		("Workflow", {"name": ["like", PREFIX + "%"]}),
	):
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, filters=filters, pluck="name"):
			previous = frappe.flags.in_workflow_task_retention
			try:
				frappe.flags.in_workflow_task_retention = doctype == "Workflow Task"
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			finally:
				frappe.flags.in_workflow_task_retention = previous
	if frappe.db.exists("DocType", DOCTYPE):
		for name in frappe.get_all(DOCTYPE, pluck="name"):
			frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)
		frappe.delete_doc("DocType", DOCTYPE, force=True, ignore_permissions=True)
	for doctype, pattern in (("Workflow State", PREFIX + "%"), ("Workflow Action Master", "Style %")):
		for name in frappe.get_all(doctype, filters={"name": ["like", pattern]}, pluck="name"):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	frappe.clear_cache()
