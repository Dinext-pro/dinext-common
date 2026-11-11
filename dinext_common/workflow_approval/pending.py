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
		fields=["name", "workflow", "approver", "approval_round_id", "workflow_state", "reference_name",
			"reference_doctype", "source_created_at", "workflow_process", "round_status"],
		order_by="approver asc, reference_name asc, name asc",
	)
	from dinext_common.workflow_approval.scenarios.service import current_task_rows
	tasks = current_task_rows(tasks)
	tasks = [task for task in tasks if task.approver and task.workflow]
	selected = required_target_task_names(tasks)
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


def required_target_task_names(tasks) -> set[str]:
	"""Match each personal snapshot to the current optionality of its Workflow states."""
	tasks = [task for task in tasks if task.workflow]
	if not tasks:
		return set()
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
		return set()
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
	return {row.parent for row in transitions if (workflows[row.parent], row.next_state) in mandatory}
