"""Standard Frappe projections for task assignments and Workflow Actions."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.notifications import clear_doctype_notifications


def _close_assignment(task: object) -> None:
	todo_names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Workflow Task",
			"reference_name": task.name,
			"allocated_to": task.approver,
			"status": ("not in", ("Closed", "Cancelled")),
		},
		pluck="name",
	)
	for todo_name in todo_names:
		todo = frappe.get_doc("ToDo", todo_name)
		todo.status = "Closed"
		todo.save(ignore_permissions=True)


def _create_assignment(task: object) -> object:
	existing = frappe.db.get_value(
		"ToDo",
		{
			"reference_type": "Workflow Task",
			"reference_name": task.name,
			"allocated_to": task.approver,
			"status": "Open",
		},
	)
	if existing:
		return frappe.get_doc("ToDo", existing)
	return frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": task.approver,
			"assigned_by": frappe.session.user,
			"reference_type": "Workflow Task",
			"reference_name": task.name,
			"description": _("Workflow approval for {0}").format(
				task.source_title
			),
			"status": "Open",
		}
	).insert(ignore_permissions=True)


def _create_workflow_action(task: object) -> object:
	existing = frappe.db.get_value(
		"Workflow Action",
		{
			"custom_workflow_task": task.name,
			"status": "Open",
		},
	)
	if existing:
		return frappe.get_doc("Workflow Action", existing)
	action = frappe.get_doc(
		{
			"doctype": "Workflow Action",
			"reference_doctype": task.reference_doctype,
			"reference_name": task.reference_name,
			"workflow_state": task.workflow_state,
			"status": "Open",
			"user": task.approver,
			"custom_workflow_task": task.name,
			"custom_approval_round_id": task.approval_round_id,
			"custom_notification_status": "Pending",
		}
	)
	for role in sorted(
		{
			row.allowed_role
			for row in task.available_workflow_transitions
			if row.allowed_role
		}
	):
		action.append("permitted_roles", {"role": role})
	action.insert(ignore_permissions=True)
	return action


def create_round_projections(source: object, tasks: list[object]) -> None:
	"""Create immediate ToDo and individualized Workflow Action projections."""
	if not tasks:
		return
	frappe.db.delete(
		"Workflow Action",
		{
			"reference_doctype": source.doctype,
			"reference_name": source.name,
			"workflow_state": tasks[0].workflow_state,
			"status": "Open",
			"custom_workflow_task": ("is", "not set"),
		},
	)
	for task in tasks:
		_create_assignment(task)
		_create_workflow_action(task)
	clear_doctype_notifications("Workflow Action")

	from dinext_common.workflow_approval.notifications import schedule_task_notification

	for task in tasks:
		schedule_task_notification(task)


def close_task_projection(task: object) -> None:
	"""Complete one action and close assignment if no other task needs it."""
	role = next(
		(
			row.allowed_role
			for row in task.available_workflow_transitions
			if row.transition_uuid == task.transition_uuid
		),
		None,
	)
	frappe.db.set_value(
		"Workflow Action",
		{"custom_workflow_task": task.name, "status": "Open"},
		{
			"status": "Completed",
			"completed_by": task.approver,
			"completed_by_role": role,
		},
		update_modified=False,
	)
	_close_assignment(task)
	clear_doctype_notifications("Workflow Action")


def close_round_projections(round_id: str) -> None:
	"""Close all standard projections associated with one immutable round."""
	task_names = frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id},
		pluck="name",
	)
	frappe.db.set_value(
		"Workflow Action",
		{"custom_approval_round_id": round_id, "status": "Open"},
		{"status": "Completed"},
		update_modified=False,
	)
	for task_name in task_names:
		_close_assignment(frappe.get_doc("Workflow Task", task_name))
	clear_doctype_notifications("Workflow Action")
