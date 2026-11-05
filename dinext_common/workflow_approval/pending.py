"""Resolve mandatory destinations for pending approval tasks."""

import frappe


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
