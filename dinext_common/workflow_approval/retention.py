"""Retention for workflow approval rounds and scenario history."""

from __future__ import annotations

from datetime import date

import frappe
from frappe.utils import add_days, cint, get_datetime, getdate

from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.scenarios import service

TERMINAL_ROUND_STATES = {"Transitioned", "Cancelled", "Conflicted"}
TERMINAL_TASK_STATES = {"Completed", "Cancelled"}
TERMINAL_DELIVERY_STATES = {"Enqueued", "Skipped", "Failed"}
TERMINAL_PROCESS_STATES = ("Archived", "Cancelled", "Completed")
TERMINAL_RULE_STATUSES = (None, "", "Completed")
BATCH_SIZE = 100


def _candidate_round_ids(rule: object, cutoff: object, after: str = "") -> list[str]:
	if rule.get("status") not in TERMINAL_RULE_STATUSES:
		return []
	task = frappe.qb.DocType("Workflow Task")
	query = (
		frappe.qb.from_(task)
		.select(task.approval_round_id)
		.distinct()
		.where(task.approval_round_id > after)
		.where(task.status.isin(sorted(TERMINAL_TASK_STATES)))
		.where(task.round_status.isin(sorted(TERMINAL_ROUND_STATES)))
		.where(
			(task.completed_at < cutoff) | (task.cancelled_at < cutoff) | (task.source_deleted_at < cutoff)
		)
		.orderby(task.approval_round_id)
		.limit(BATCH_SIZE)
	)
	if reference_doctype := rule.get("reference_doctype"):
		query = query.where(task.reference_doctype == reference_doctype)
	return query.run(pluck=True)


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
		action.status == "Open" or action.custom_notification_status not in TERMINAL_DELIVERY_STATES
		for action in actions
	):
		return True
	delivery_keys = [action.custom_delivery_key for action in actions if action.custom_delivery_key]
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


def _delete_terminal_round(round_id: str, cutoff, reference_doctype=None) -> bool:
	pointers = frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id},
		fields=["name", "reference_doctype", "reference_name"],
		order_by="name asc",
	)
	if not pointers:
		return False
	first = pointers[0]
	if frappe.db.exists("DocType", first.reference_doctype) and frappe.db.exists(
		first.reference_doctype, first.reference_name
	):
		engine._lock_domain_dependencies(first.reference_doctype, first.reference_name)
		frappe.get_doc(first.reference_doctype, first.reference_name, for_update=True)
	tasks = [frappe.get_doc("Workflow Task", row.name, for_update=True) for row in pointers]
	if _round_is_protected(tasks) or any(
		(reference_doctype and task.reference_doctype != reference_doctype)
		or not any(
			timestamp and get_datetime(timestamp) < get_datetime(cutoff)
			for timestamp in (task.completed_at, task.cancelled_at, task.source_deleted_at)
		)
		for task in tasks
	):
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


def _rule_scope(rule):
	if reference_doctype := rule.get("reference_doctype"):
		return {"reference_doctype": reference_doctype}
	return {}


def _names_after(doctype, filters, after):
	return frappe.get_all(
		doctype,
		filters={**filters, "name": (">", after)},
		pluck="name",
		order_by="name asc",
		limit=BATCH_SIZE,
	)


def _run_batches(label, fetch, delete):
	deleted = 0
	after = ""
	while candidates := fetch(after):
		for name in candidates:
			try:
				removed = delete(name)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback()
				frappe.logger("workflow_retention").exception("Failed to delete %s %s", label, name)
				continue
			deleted += int(removed)
			if deleted == BATCH_SIZE:
				return deleted
		after = candidates[-1]
	return deleted


def _delete_standalone_action(name, filters):
	if not frappe.db.get_value("Workflow Action", {**filters, "name": name}, "name", for_update=True):
		return False
	frappe.delete_doc("Workflow Action", name, force=True, ignore_permissions=True)
	return True


def _identity(row):
	return row.reference_doctype, row.reference_name, row.source_created_at


def _lock_source_instance(row):
	doctype, name, created_at = _identity(row)
	if not (doctype and name and created_at):
		return True
	if not frappe.db.exists("DocType", doctype):
		return False
	if frappe.get_meta(doctype).issingle:
		return True
	source = {"name": name}
	if frappe.db.get_value(doctype, source, "name"):
		engine._lock_domain_dependencies(doctype, name)
	creation = frappe.db.get_value(doctype, source, "creation", for_update=True)
	return bool(creation and get_datetime(creation) == get_datetime(created_at))


def _linked_record_exists(doctype, filters):
	return bool(frappe.db.get_value(doctype, filters, "name", for_update=True))


def _delete_process(name, cutoff, reference_doctype):
	pointer = frappe.db.get_value(
		service.PROCESS,
		name,
		["reference_doctype", "reference_name", "source_created_at", "source_key"],
		as_dict=True,
	)
	if not pointer:
		return False
	source_exists = _lock_source_instance(pointer)
	context = (
		frappe.db.get_value(
			service.CONTEXT,
			pointer.source_key,
			["name", "last_process"],
			as_dict=True,
			for_update=True,
		)
		if pointer.source_key
		else None
	)
	process = frappe.db.get_value(
		service.PROCESS,
		name,
		[
			"reference_doctype",
			"reference_name",
			"source_created_at",
			"source_key",
			"status",
			"active_source_key",
			"completed_at",
		],
		as_dict=True,
		for_update=True,
	)
	if (
		not process
		or _identity(process) != _identity(pointer)
		or process.source_key != pointer.source_key
		or (reference_doctype and process.reference_doctype != reference_doctype)
		or process.status not in TERMINAL_PROCESS_STATES
		or process.active_source_key
		or not process.completed_at
		or get_datetime(process.completed_at) >= get_datetime(cutoff)
	):
		return False
	is_last = context and context.last_process == name
	if is_last and source_exists:
		return False
	if _linked_record_exists("Workflow Task", {"workflow_process": name}):
		return False
	if _linked_record_exists(service.CONTEXT, {"active_process": name}):
		return False
	if _linked_record_exists(
		service.CONTEXT, {"last_process": name, "name": ("!=", pointer.source_key or "")}
	):
		return False
	if is_last:
		frappe.db.set_value(service.CONTEXT, context.name, "last_process", None, update_modified=False)
	frappe.delete_doc(
		service.PROCESS,
		name,
		ignore_permissions=True,
		flags={"in_workflow_scenario_service": True},
	)
	return True


def _delete_context(name, cutoff, reference_doctype):
	identity_fields = ["reference_doctype", "reference_name", "source_created_at"]
	pointer = frappe.db.get_value(service.CONTEXT, name, identity_fields, as_dict=True)
	if not pointer or _lock_source_instance(pointer):
		return False
	context = frappe.db.get_value(
		service.CONTEXT,
		name,
		[*identity_fields, "active_process", "last_process", "modified"],
		as_dict=True,
		for_update=True,
	)
	if (
		not context
		or _identity(context) != _identity(pointer)
		or context.active_process
		or (reference_doctype and context.reference_doctype != reference_doctype)
		or not context.modified
		or get_datetime(context.modified) >= get_datetime(cutoff)
	):
		return False
	identity = {field: context.get(field) for field in identity_fields}
	if (
		_linked_record_exists(service.PROCESS, {"source_key": name})
		or _linked_record_exists(service.PROCESS, identity)
		or (context.last_process and _linked_record_exists(service.PROCESS, {"name": context.last_process}))
		or _linked_record_exists("Workflow Task", identity)
	):
		return False
	frappe.delete_doc(
		service.CONTEXT,
		name,
		ignore_permissions=True,
		flags={"in_workflow_scenario_service": True},
	)
	return True


@frappe.whitelist(methods=["POST"])
def cleanup_workflow_approval_rounds() -> int:
	"""Run workflow retention and return the number of rounds deleted."""
	frappe.only_for("System Manager")
	request = getattr(frappe.local, "request", None)
	if request is not None and request.method != "POST":
		raise frappe.PermissionError
	if not frappe.db.exists("DocType", "Data Cleanup Rules"):
		return 0

	today = getdate()
	max_days = (today - date.min).days
	rules = []
	for rule in frappe.get_single("Data Cleanup Rules").workflow_rules or []:
		days = cint(rule.days)
		if rule.enabled and 0 < days <= max_days:
			rules.append((rule, add_days(today, -days)))
	# Let earlier cutoffs consume their own batches before the wider age ranges.
	rules.sort(key=lambda item: (item[1], item[0].reference_doctype or "", item[0].status or ""))
	rounds = actions = processes = contexts = 0
	terminal_rules = [(rule, cutoff) for rule, cutoff in rules if rule.status in TERMINAL_RULE_STATUSES]
	if frappe.db.has_column("Workflow Task", "approval_round_id"):
		for rule, cutoff in terminal_rules:
			rounds += _run_batches(
				"approval round",
				lambda after: _candidate_round_ids(rule, cutoff, after),
				lambda name: _delete_terminal_round(name, cutoff, rule.reference_doctype),
			)
	if frappe.db.has_column("Workflow Action", "custom_workflow_task"):
		for rule, cutoff in rules:
			filters = {
				**_rule_scope(rule),
				"modified": ("<", cutoff),
				"custom_workflow_task": ("is", "not set"),
			}
			if rule.status:
				filters["status"] = rule.status
			actions += _run_batches(
				"Workflow Action",
				lambda after: _names_after("Workflow Action", filters, after),
				lambda name: _delete_standalone_action(name, filters),
			)

	if service.is_ready():
		for rule, cutoff in terminal_rules:
			filters = {
				**_rule_scope(rule),
				"completed_at": ("<", cutoff),
				"status": ("in", TERMINAL_PROCESS_STATES),
			}
			processes += _run_batches(
				service.PROCESS,
				lambda after: _names_after(service.PROCESS, filters, after),
				lambda name: _delete_process(name, cutoff, rule.reference_doctype),
			)
		for rule, cutoff in terminal_rules:
			filters = {**_rule_scope(rule), "modified": ("<", cutoff)}
			contexts += _run_batches(
				service.CONTEXT,
				lambda after: _names_after(service.CONTEXT, filters, after),
				lambda name: _delete_context(name, cutoff, rule.reference_doctype),
			)
	frappe.logger("workflow_retention").info(
		"Workflow cleanup deleted %s rounds, %s standalone actions, %s processes and %s contexts",
		rounds,
		actions,
		processes,
		contexts,
	)
	return rounds
