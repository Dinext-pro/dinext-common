"""Standard Frappe projections for task assignments and Workflow Actions."""

from __future__ import annotations

import json

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


DELIVERY_FIELDS = (
	"custom_delivery_key", "custom_notification_mode", "custom_notification_status",
	"custom_notification_suppressed", "custom_last_digest_slot",
)


def delivery_snapshot(task: object) -> dict:
	return json.loads(getattr(task, "notification_delivery_snapshot", None) or "{}")


def persist_delivery_snapshot(action: object, method=None) -> None:
	"""Retain a personal delivery decision independently of its projection."""
	task_name = action.get("custom_workflow_task")
	if not task_name or not frappe.get_meta("Workflow Task").has_field("notification_delivery_snapshot"):
		return
	previous = frappe.db.get_value("Workflow Task", task_name, "notification_delivery_snapshot")
	snapshot = json.loads(previous or "{}")
	# A nested key update may have used a separately loaded Action object.
	current = frappe.db.get_value("Workflow Action", action.name, DELIVERY_FIELDS, as_dict=True)
	if not current:
		return
	snapshot.update(current)
	frappe.db.set_value("Workflow Task", task_name, "notification_delivery_snapshot",
		frappe.as_json(snapshot), update_modified=False)


def backfill_delivery_snapshots() -> None:
	"""Copy legacy decisions; never infer a historical immediate send."""
	unknown = 0
	while names := frappe.get_all("Workflow Task", filters={
		"status": "Working", "approval_round_id": ("is", "set"),
		"notification_delivery_snapshot": ("is", "not set"),
	}, pluck="name", limit_page_length=100, order_by="name"):
		for name in names:
			frappe.get_doc("Workflow Task", name, for_update=True)
			action_name = frappe.db.get_value("Workflow Action", {"custom_workflow_task": name, "status": "Open"})
			if action_name:
				persist_delivery_snapshot(frappe.get_doc("Workflow Action", action_name, for_update=True))
			else:
				frappe.db.set_value("Workflow Task", name, "notification_delivery_snapshot",
					frappe.as_json({"legacy_unknown": True}), update_modified=False)
				unknown += 1
	if unknown:
		frappe.log_error(title=_("Workflow notification history is incomplete"),
			message=_("Delivery evidence is missing for {0} legacy tasks; historical immediate mail was skipped.").format(unknown))


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
	snapshot = delivery_snapshot(task)
	for field in DELIVERY_FIELDS:
		if field in snapshot:
			action.set(field, snapshot[field])
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


def repair_round_projections(source: object, round_id: str) -> None:
	"""Restore assignments and missing Actions without resetting existing delivery."""
	rows = frappe.get_all("Workflow Task", filters={
		"approval_round_id": round_id, "round_status": "Open", "status": "Working",
	}, fields=["name", "approver"], order_by="name")
	if not rows:
		return
	names = [row.name for row in rows]
	actions = set(frappe.get_all("Workflow Action", filters={
		"custom_workflow_task": ("in", names), "status": "Open",
	}, pluck="custom_workflow_task"))
	assignments = {(row.reference_name, row.allocated_to) for row in frappe.get_all("ToDo", filters={
		"reference_type": "Workflow Task", "reference_name": ("in", names), "status": "Open",
	}, fields=["reference_name", "allocated_to"])}
	for row in rows:
		name = row.name
		if name in actions and (name, row.approver) in assignments:
			continue
		task = frappe.get_doc("Workflow Task", name, for_update=True)
		if task.status != "Working" or task.round_status != "Open":
			continue
		if (name, task.approver) not in assignments:
			_create_assignment(task)
		if frappe.db.exists("Workflow Action", {"custom_workflow_task": name, "status": "Open"}):
			continue
		snapshot = delivery_snapshot(task)
		if not snapshot:
			snapshot = {"legacy_unknown": True}
			task.notification_delivery_snapshot = frappe.as_json(snapshot)
			frappe.db.set_value("Workflow Task", name, "notification_delivery_snapshot",
				task.notification_delivery_snapshot, update_modified=False)
		_create_workflow_action(task)
		if snapshot.get("legacy_unknown") or snapshot.get("custom_notification_status") == "Enqueued":
			continue
		from dinext_common.workflow_approval.notifications import schedule_task_notification

		schedule_task_notification(task)
	clear_doctype_notifications("Workflow Action")


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
