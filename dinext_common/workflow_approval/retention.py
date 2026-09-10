"""Round-aware retention for the Workflow Task audit ledger."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_days, getdate

from dinext_common.workflow_approval import engine

TERMINAL_ROUND_STATES = {"Transitioned", "Cancelled", "Conflicted"}
TERMINAL_TASK_STATES = {"Completed", "Cancelled"}
TERMINAL_DELIVERY_STATES = {"Enqueued", "Skipped", "Failed"}
ROUND_BATCH_SIZE = 100
LEGACY_SECTION_START = "\t# 6. Workflow Cleanup Rule"
LEGACY_SECTION_END = '\n\tlog("Data Cleanup: finished'


def _candidate_round_ids(rule: object, cutoff: object) -> list[str]:
	filters: list[list[Any]] = [
		["status", "in", sorted(TERMINAL_TASK_STATES)],
		["round_status", "in", sorted(TERMINAL_ROUND_STATES)],
	]
	if rule.get("reference_doctype"):
		filters.append(["reference_doctype", "=", rule.reference_doctype])
	if rule.get("status") == "Open":
		return []
	rows = frappe.get_all(
		"Workflow Task",
		filters=filters,
		or_filters=[
			["completed_at", "<", cutoff],
			["cancelled_at", "<", cutoff],
			["source_deleted_at", "<", cutoff],
		],
		fields=["approval_round_id", "completed_at", "cancelled_at", "source_deleted_at"],
		order_by="completed_at asc, cancelled_at asc, source_deleted_at asc, approval_round_id asc",
		limit=ROUND_BATCH_SIZE * 5,
	)
	result: list[str] = []
	for row in rows:
		round_id = row.approval_round_id
		if round_id and round_id not in result:
			result.append(round_id)
		if len(result) >= ROUND_BATCH_SIZE:
			break
	return result


def _round_is_protected(tasks: list[object]) -> bool:
	if not tasks or any(
		task.status not in TERMINAL_TASK_STATES
		or task.round_status not in TERMINAL_ROUND_STATES
		or task.finalization_status == "Queued"
		for task in tasks
	):
		return True
	names = [task.name for task in tasks]
	if frappe.db.exists(
		"Workflow Task",
		{"reused_from_workflow_task": ("in", names)},
	):
		return True
	actions = frappe.get_all(
		"Workflow Action",
		filters={"custom_workflow_task": ("in", names)},
		fields=[
			"name",
			"status",
			"custom_notification_status",
			"custom_delivery_key",
		],
	)
	if any(
		action.status == "Open"
		or action.custom_notification_status not in TERMINAL_DELIVERY_STATES
		for action in actions
	):
		return True
	delivery_keys = [
		action.custom_delivery_key
		for action in actions
		if action.custom_delivery_key
	]
	return bool(
		delivery_keys
		and frappe.db.exists(
			"Email Queue",
			{
				"message_id": ("in", delivery_keys),
				"status": ("not in", ("Sent", "Error")),
			},
		)
	)


def _delete_terminal_round(round_id: str) -> bool:
	pointers = frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id},
		fields=["name", "reference_doctype", "reference_name"],
		order_by="name asc",
	)
	if not pointers:
		return False
	first = pointers[0]
	if (
		frappe.db.exists("DocType", first.reference_doctype)
		and frappe.db.exists(first.reference_doctype, first.reference_name)
	):
		engine._lock_domain_dependencies(first.reference_doctype, first.reference_name)
	tasks = [
		frappe.get_doc("Workflow Task", row.name, for_update=True)
		for row in pointers
	]
	if _round_is_protected(tasks):
		return False
	names = [task.name for task in tasks]
	action_names = frappe.get_all(
		"Workflow Action",
		filters={"custom_workflow_task": ("in", names)},
		pluck="name",
		order_by="name asc",
	)
	delivery_keys = frappe.get_all(
		"Workflow Action",
		filters={
			"custom_workflow_task": ("in", names),
			"custom_delivery_key": ("is", "set"),
		},
		pluck="custom_delivery_key",
	)
	email_queue_names = (
		frappe.get_all(
			"Email Queue",
			filters={
				"message_id": ("in", delivery_keys),
				"status": ("in", ("Sent", "Error")),
			},
			pluck="name",
			order_by="name asc",
		)
		if delivery_keys
		else []
	)
	todo_names = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Workflow Task",
			"reference_name": ("in", names),
		},
		pluck="name",
		order_by="name asc",
	)
	for doctype, record_names in (
		("Email Queue", email_queue_names),
		("Workflow Action", action_names),
		("ToDo", todo_names),
	):
		for name in record_names:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	previous_flag = getattr(frappe.flags, "in_workflow_task_retention", False)
	frappe.flags.in_workflow_task_retention = True
	try:
		for name in names:
			frappe.delete_doc(
				"Workflow Task",
				name,
				force=True,
				ignore_permissions=True,
			)
	finally:
		frappe.flags.in_workflow_task_retention = previous_flag
	return True


@frappe.whitelist()
def cleanup_workflow_approval_rounds() -> int:
	"""Delete bounded terminal rounds only when an explicit rule permits it."""
	if not frappe.db.table_exists("Data Cleanup Rules"):
		return 0
	rules = frappe.get_single("Data Cleanup Rules")
	deleted = 0
	for rule in rules.workflow_rules or []:
		if not rule.enabled or not rule.days or rule.status == "Open":
			continue
		cutoff = add_days(getdate(), -int(rule.days))
		for round_id in _candidate_round_ids(rule, cutoff):
			try:
				if _delete_terminal_round(round_id):
					frappe.db.commit()
					deleted += 1
			except Exception:
				frappe.db.rollback()
				frappe.log_error(
					title=f"Workflow approval retention failed: {round_id}"
				)
	return deleted


def install_cleanup_delegation() -> bool:
	"""Replace only the legacy Workflow branch in the retained daily script."""
	if not frappe.db.exists("Server Script", "Data Cleanup Daily"):
		return False
	script = frappe.get_doc("Server Script", "Data Cleanup Daily")
	if "cleanup_workflow_approval_rounds" in script.script:
		return False
	start = script.script.find(LEGACY_SECTION_START)
	end = script.script.find(LEGACY_SECTION_END)
	if start < 0 or end <= start:
		raise RuntimeError("Data Cleanup Daily Workflow section was not recognized")
	delegation = (
		'\tworkflow_rounds = frappe.call('
		'"dinext_common.workflow_approval.retention.cleanup_workflow_approval_rounds"'
		") or 0\n"
		"\tdeleted_total += workflow_rounds\n"
	)
	script.script = script.script[:start] + delegation + script.script[end:]
	script.save(ignore_permissions=True)
	return True
