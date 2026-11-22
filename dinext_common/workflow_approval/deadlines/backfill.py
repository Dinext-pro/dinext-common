"""Recover original open obligations from assignment history, never migration time."""

import json

import frappe

from dinext_common.workflow_approval.deadlines.lifecycle import FIELDS, prepare_task, snapshot


def original_assignment(task, history):
	if not task.get("creation"):
		return None
	cutoff = str(task["creation"])
	prior = [row for row in history if row.get("creation") and str(row["creation"]) <= cutoff]
	boundary = max(
		(str(row["creation"]) for row in prior if row.get("workflow_state") != task["workflow_state"]),
		default="",
	)
	matching = [
		row
		for row in prior
		if str(row["creation"]) > boundary
		and row.get("approver") == task["approver"]
		and row.get("workflow_state") == task["workflow_state"]
	]
	matching.sort(key=lambda row: (str(row["creation"]), row["name"]))
	if not matching:
		return None
	current = matching[-1]
	for previous in reversed(matching[:-1]):
		# A recorded decision ended the earlier obligation, including a same-state return.
		if previous.get("status") == "Completed":
			break
		fingerprint = current.get("entry_fingerprint")
		previous_fingerprint = previous.get("entry_fingerprint")
		version = current.get("entry_fingerprint_version")
		if (
			not fingerprint
			or not previous_fingerprint
			or not version
			or version != previous.get("entry_fingerprint_version")
		):
			return None
		if fingerprint != previous_fingerprint:
			break
		metadata = previous.get("failure_metadata") or {}
		if isinstance(metadata, str):
			try:
				metadata = json.loads(metadata)
			except (ValueError, TypeError):
				return None
		if (
			not isinstance(metadata, dict)
			or previous.get("status") != "Cancelled"
			or metadata.get("reason") != "configuration_changed"
		):
			return None
		current = previous
	return current


def backfill_open_tasks(workflow_name):
	workflow = frappe.get_doc("Workflow", workflow_name)
	names = frappe.get_all(
		"Workflow Task",
		filters={
			"workflow": workflow_name,
			"status": "Working",
			"round_status": ["in", ["Open", "Stalled"]],
			"deadline_assignment_id": ["is", "not set"],
		},
		pluck="name",
		order_by="creation asc",
	)
	recovered = unknown = 0
	for name in names:
		task = frappe.get_doc("Workflow Task", name, for_update=True)
		history = frappe.get_all(
			"Workflow Task",
			filters={
				"workflow": workflow_name,
				"reference_doctype": task.reference_doctype,
				"reference_name": task.reference_name,
				"source_created_at": task.source_created_at,
			},
			fields=[
				"name",
				"creation",
				"approver",
				"workflow_state",
				"approval_round_id",
				"status",
				"entry_fingerprint",
				"entry_fingerprint_version",
				"cancellation_reason",
				"failure_metadata",
			],
			order_by="creation asc, name asc",
		)
		origin = original_assignment(task.as_dict(), history)
		prepare_task(task, workflow, started_at=origin["creation"] if origin else task.creation)
		if not task.deadline_assignment_id:
			continue
		if origin:
			task.deadline_assignment_id = origin["name"]
			task.deadline_origin_task = origin["name"] if origin["name"] != task.name else None
			recovered += 1
		else:
			task.deadline_started_at = task.deadline_due_at = None
			task.deadline_error = "Original assignment time is unknown"
			unknown += 1
		frappe.db.set_value(
			"Workflow Task",
			task.name,
			{key: task.get(key) for key in (*FIELDS, "deadline_origin_task")},
			update_modified=False,
		)
		manifest = json.loads(task.round_manifest or "{}")
		manifest.setdefault("deadline_assignments", {})[task.approver] = snapshot(task)
		frappe.db.set_value(
			"Workflow Task",
			{"approval_round_id": task.approval_round_id},
			"round_manifest",
			json.dumps(manifest, ensure_ascii=False, default=str),
			update_modified=False,
		)
	return dict(recovered=recovered, unknown=unknown)
