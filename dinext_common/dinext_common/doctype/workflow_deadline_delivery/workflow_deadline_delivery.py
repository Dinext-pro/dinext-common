# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, cint, create_batch, now_datetime

DOCTYPE = "Workflow Deadline Delivery"
DEFAULT_RETENTION_DAYS = 7
BATCH_SIZE = 500


class WorkflowDeadlineDelivery(Document):
	@staticmethod
	def clear_old_logs(days: int) -> None:
		now = now_datetime()
		cutoff = add_days(now, -max(0, cint(days)))
		filters = {"status": "Enqueued", "creation": ("<", cutoff)}
		last_name = ""
		while rows := frappe.get_all(
			DOCTYPE,
			filters={**filters, "name": (">", last_name)},
			fields=["name", "workflow", "workflow_state", "recipient", "slot"],
			order_by="name asc",
			limit_page_length=BATCH_SIZE,
		):
			last_name = rows[-1].name
			if names := _finished_deliveries(rows, now):
				frappe.db.delete(DOCTYPE, {**filters, "name": ("in", names)})


def register_log_settings() -> None:
	settings = frappe.get_single("Log Settings")
	if any(row.ref_doctype == DOCTYPE for row in settings.logs_to_clear):
		return
	settings.register_doctype(DOCTYPE, DEFAULT_RETENTION_DAYS)
	settings.save(ignore_permissions=True)


def _finished_deliveries(rows, now):
	from dinext_common.workflow_approval.deadlines.delivery import delivery_key

	groups = defaultdict(list)
	for row in rows:
		groups[row.workflow, row.workflow_state, row.recipient].append(row)

	active_by_state = {}
	finished = []
	for (workflow, state, recipient), deliveries in groups.items():
		scope = (workflow, state)
		if scope not in active_by_state:
			active_by_state[scope] = _restorable_assignments(workflow, state)
		tasks = active_by_state[scope]
		immediate_keys = {
			delivery_key(workflow, state, recipient, task.deadline_assignment_id) for task in tasks
		}
		digest_keys = set()
		if tasks and any(row.slot for row in deliveries):
			digest_keys = _active_digest_keys(workflow, state, recipient, tasks, now, deliveries)
		for row in deliveries:
			if row.slot:
				if digest_keys is None or row.name in digest_keys:
					continue
			elif row.name in immediate_keys:
				continue
			finished.append(row.name)
	return finished


def _restorable_assignments(workflow, state):
	from dinext_common.workflow_approval.engine import ACTIVE_ROUND_STATUSES, _parse_manifest

	rows = frappe.get_all(
		"Workflow Task",
		filters={"workflow": workflow, "workflow_state": state, "round_status": ("in", ACTIVE_ROUND_STATUSES)},
		fields=[
			"name", "status", "approval_round_id", "deadline_assignment_id", "deadline_due_at",
			"deadline_transition_uuid", "approver", "reference_doctype", "reference_name",
		],
		order_by="name asc",
	)

	# An amendment can restore a withdrawn personal row without changing its assignment.
	assignments = [row for row in rows if row.deadline_assignment_id and row.status in ("Working", "Cancelled")]
	representatives = {}
	for row in rows:
		if row.approval_round_id:
			representatives.setdefault(row.approval_round_id, row.name)
	# The engine copies the same manifest to each row. Read it once per active round.
	# a later rebuild can recreate an absent approver using that frozen assignment.
	for names in create_batch(list(representatives.values()), BATCH_SIZE):
		for row in frappe.get_all(
			"Workflow Task", filters={"name": ("in", names)},
			fields=["round_manifest", "reference_doctype", "reference_name"],
		):
			for approver, snapshot in _parse_manifest(row).get("deadline_assignments", {}).items():
				if snapshot.get("deadline_assignment_id"):
					assignments.append(frappe._dict(
						snapshot, approver=approver, reference_doctype=row.reference_doctype,
						reference_name=row.reference_name,
					))
	# A manifest normally repeats the current row. Recalculate a recipient's schedule
	# twice only when the recoverable facts actually differ (e.g. a repaired due date).
	return {
		(task.deadline_assignment_id, str(task.deadline_due_at), task.deadline_transition_uuid,
		 task.approver, task.reference_doctype, task.reference_name): task
		for task in assignments
	}.values()


def _active_digest_keys(workflow, state, recipient, tasks, now, deliveries):
	from dinext_common.workflow_approval.deadlines.delivery import current_policy, delivery_key, delivery_slot
	from dinext_common.workflow_approval.notifications import _aware_utc

	try:
		route = frappe.get_cached_doc("Workflow", workflow)
	except frappe.DoesNotExistError:
		return None

	keys = set()
	for task in tasks:
		if not task.deadline_due_at:
			# A failed deadline calculation may leave the policy ID unset as well.
			return None
		policy = current_policy(task, route, include_disabled=True)
		if not policy:
			# A withdrawn transition may be restored with the same UUID and schedule.
			if not task.deadline_transition_uuid:
				return None
			for row in deliveries:
				if row.slot and row.name == delivery_key(
					workflow, state, recipient, task.deadline_transition_uuid, slot=_aware_utc(row.slot),
				):
					keys.add(row.name)
			continue
		if policy.custom_deadline_email_mode != "Digest":
			continue
		try:
			slot = delivery_slot(task, policy, recipient, now, require_provider=True)
		except Exception:
			# A missing calendar or an unavailable provider may recover at the same slot.
			return None
		if slot is not None:
			keys.add(delivery_key(workflow, state, recipient, task.deadline_transition_uuid, slot=slot))
	return keys
