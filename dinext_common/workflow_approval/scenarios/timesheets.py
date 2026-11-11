"""Compatibility for Timesheets' task/source check without producer source changes."""

from __future__ import annotations

import importlib
from functools import wraps

import frappe

_installed = False


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
