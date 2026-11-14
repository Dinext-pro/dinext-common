"""Compatibility for Timesheets' task/source check without producer source changes."""

from __future__ import annotations

import importlib
from functools import wraps

import frappe
from frappe import _

_installed = False


def _wrap_source_before_save(original, event):
	@wraps(original)
	def before_save(doc, method=None):
		from dinext_common.workflow_approval.scenarios import compat

		before = doc.get_doc_before_save()
		if not before or doc.flags.ignore_permissions or not compat.is_authorized_finalization(doc):
			return original(doc, method)
		field = compat._service().get_context(doc).get("state_field")
		if not field or field == "workflow_state" or before.get(field) == doc.get(field):
			return original(doc, method)
		if any(doc.get(key) != before.get(key) for key in ("user_timesheet", "user", "user_group")):
			frappe.throw(_("The position must belong to the timesheet worker"), frappe.PermissionError)
		if any(row.next_state == doc.get(field) for row in event.timesheet_management_transitions(before)):
			parent = frappe.get_doc("User Timesheet", doc.user_timesheet)
			if not event.has_worker_scope(parent.timesheet_from, parent.ts_valid_for) or not frappe.has_permission(
				before, "write", ignore_share_permissions=True
			):
				frappe.throw(_("Not permitted to edit this timesheet"), frappe.PermissionError)
		# Keep the producer's position processing while substituting the selected field for its legacy gate.
		previous = doc.flags.ignore_permissions
		doc.flags.ignore_permissions = True
		try:
			return original(doc, method)
		finally:
			doc.flags.ignore_permissions = previous

	return before_save


def _wrap_source_update(original, producer):
	@wraps(original)
	def on_source_saved(doc, method=None):
		from dinext_common.workflow_approval.scenarios import compat

		if not compat._ready() or not producer._enabled():
			return original(doc, method)
		context = compat._service().get_context(doc)
		field = context.get("state_field")
		before = doc.get_doc_before_save()
		if (not field or field == "status" or not before or before.status != doc.status
			or before.get(field) == doc.get(field)):
			return original(doc, method)
		if (getattr(frappe.flags, "defer_timesheet_rollup", False)
			or getattr(frappe.flags, "in_timesheet_approval_cascade", False)):
			return
		# Domain-status hooks retain their existing dates/notifications behavior. A selected
		# field change only needs the parent rule calculation, without a source status mirror.
		parent = frappe.get_doc("User Timesheet", doc.user_timesheet, for_update=True)
		producer._recalculate_parent(parent, doc, before.status)

	on_source_saved._dinext_scenario_source_update = True
	return on_source_saved


def task_no_longer_matches_source(task_name: str) -> bool:
	from dinext_common.workflow_approval.scenarios import service

	task = frappe.db.get_value(
		"Workflow Task", task_name,
		["status", "round_status", "reference_doctype", "reference_name", "workflow", "workflow_process", "workflow_state", "source_created_at"],
		as_dict=True,
	)
	if not task or task.status != "Working" or task.round_status != "Open":
		return True
	try:
		source = frappe.get_doc(task.reference_doctype, task.reference_name)
	except frappe.DoesNotExistError:
		return True
	if task.source_created_at and str(task.source_created_at) != str(source.creation):
		from frappe.utils import get_datetime

		if get_datetime(task.source_created_at) != get_datetime(source.creation):
			return True
	context = service.get_context(source)
	return (
		not context.get("workflow")
		or context.get("workflow") != task.workflow
		or context.get("process_id") != (task.workflow_process or None)
		or str(context.get("state") or "") != str(task.workflow_state or "")
	)


def install() -> None:
	global _installed
	if _installed:
		return
	try:
		producer = importlib.import_module("dinext_timesheets.workflow_approval")
	except ModuleNotFoundError as error:
		if error.name and error.name.split(".")[0] == "dinext_timesheets":
			return
		raise
	from dinext_common.workflow_approval.scenarios import compat

	original = producer._task_no_longer_matches_source

	@wraps(original)
	def matches(task_name):
		if not compat._ready():
			return original(task_name)
		return task_no_longer_matches_source(task_name)

	compat.replace_function(original, matches)
	event = importlib.import_module(
		"dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet_position"
	)
	compat.replace_function(event.before_save, _wrap_source_before_save(event.before_save, event))
	bridge = importlib.import_module(
		"dinext_timesheets.dinext_timesheets.user_timesheet.events.workflow_tasks"
	)
	original_sync = bridge.sync_status_from_workflow_state

	@wraps(original_sync)
	def sync_status(doc):
		from dinext_common.workflow_approval.scenarios import service

		if service.is_ready() and service.get_context(doc).get("state_field") != "workflow_state":
			return
		return original_sync(doc)

	compat.replace_function(original_sync, sync_status)
	for name in ("on_utp_update", "on_source_saved"):
		original_update = getattr(producer, name, None)
		if original_update and not getattr(original_update, "_dinext_scenario_source_update", False):
			compat.replace_function(original_update, _wrap_source_update(original_update, producer))
	_installed = True
