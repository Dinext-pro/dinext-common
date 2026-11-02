"""Read pending actors for form display without changing approval eligibility."""

from typing import TypedDict

import frappe


class PendingApproverTask(TypedDict):
	approver: str
	approval_round_id: str | None
	workflow_state: str | None
	reference_name: str


def get_required_state_pending_tasks(
	reference_doctype: str, reference_names: list[str]
) -> list[PendingApproverTask]:
	"""Select personal Open/Working tasks with at least one mandatory target."""
	if not reference_names:
		return []
	tasks = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": ("in", reference_names),
			"status": "Working",
			"round_status": "Open",
		},
		fields=["name", "workflow", "approver", "approval_round_id", "workflow_state", "reference_name"],
		order_by="approver asc, reference_name asc, name asc",
	)
	tasks = [task for task in tasks if task.approver and task.workflow]
	if not tasks:
		return []
	states = frappe.get_all(
		"Workflow Document State",
		filters={
			"parent": ("in", sorted({task.workflow for task in tasks})),
			"parenttype": "Workflow",
			"parentfield": "states",
			"is_optional_state": 0,
		},
		fields=["parent", "state"],
	)
	mandatory = {(row.parent, row.state) for row in states}
	if not mandatory:
		return []
	workflows = {task.name: task.workflow for task in tasks}
	transitions = frappe.get_all(
		"Available Workflow Transitions",
		filters={
			"parent": ("in", list(workflows)),
			"parenttype": "Workflow Task",
			"parentfield": "available_workflow_transitions",
		},
		fields=["parent", "next_state"],
	)
	selected = {row.parent for row in transitions if (workflows[row.parent], row.next_state) in mandatory}
	return [
		{
			"approver": task.approver,
			"approval_round_id": task.approval_round_id,
			"workflow_state": task.workflow_state,
			"reference_name": task.reference_name,
		}
		for task in tasks
		if task.name in selected
	]
