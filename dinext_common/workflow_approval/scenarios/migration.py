"""Adopt existing approval work without replaying transitions or routing documents."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import frappe
from frappe.utils import get_datetime

from dinext_common.workflow_approval.scenarios import metadata


def planned_orders(rows: list[dict[str, Any]]) -> dict[str, int]:
	"""Keep valid orders and number legacy rows deterministically."""
	by_type = defaultdict(list)
	for row in rows:
		by_type[row.get("document_type")].append(row)
	updates = {}
	for workflows in by_type.values():
		workflows.sort(key=lambda row: (-int(bool(row.get("is_active"))), row["name"]))
		reserved = set()
		keepers = set()
		for row in workflows:
			try:
				order = metadata.normalized_order(row.get(metadata.ORDER_FIELD))
			except ValueError:
				continue
			if order not in reserved:
				reserved.add(order)
				keepers.add(row["name"])
		candidate = 1
		for row in workflows:
			if row["name"] in keepers:
				continue
			while candidate in reserved:
				candidate += 1
			updates[row["name"]] = candidate
			reserved.add(candidate)
	return updates


def assign_selection_orders() -> int:
	rows = frappe.get_all("Workflow", fields=["name", "document_type", "is_active", metadata.ORDER_FIELD])
	updates = planned_orders(rows)
	for name, order in updates.items():
		frappe.db.set_value("Workflow", name, metadata.ORDER_FIELD, order, update_modified=False)
	return len(updates)


def adopt_legacy_sources() -> int:
	"""Only link stored rows to an audit process of the same source instance."""
	if not frappe.db.table_exists("Workflow Task") or not frappe.db.has_column(
		"Workflow Task", "workflow_process"
	):
		return 0
	from dinext_common.workflow_approval.scenarios.service import adopt_legacy_source

	tasks = frappe.get_all(
		"Workflow Task",
		filters={"workflow_process": ("is", "not set"), "workflow": ("is", "set")},
		fields=["*"],
		order_by="creation asc, name asc",
	)
	by_source = defaultdict(list)
	for task in tasks:
		doctype = task.get("reference_doctype") or task.get("doc")
		name = task.get("reference_name") or task.get("wt_docname")
		if doctype and name and task.get("source_created_at"):
			by_source[(doctype, name, get_datetime(task["source_created_at"]))].append(task)
	adopted = 0
	for (doctype, name, created_at), source_tasks in by_source.items():
		try:
			source = frappe.get_doc(doctype, name)
		except frappe.DoesNotExistError:
			continue
		if get_datetime(source.creation) != created_at:
			continue
		if adopt_legacy_source(source, source_tasks):
			adopted += 1
	return adopted


def restore_legacy_link_bindings() -> int:
	"""Repair an interrupted upgrade without granting old URLs access to new rounds."""
	processes = frappe.get_all(
		"Workflow Process",
		filters={"legacy_task_names": ("is", "not set")},
		fields=["name", "creation", "started_at"],
	)
	legacy = {
		row.name: row
		for row in processes
		if row.started_at and get_datetime(row.started_at) < get_datetime(row.creation)
	}
	if not legacy:
		return 0
	groups = defaultdict(list)
	for task in frappe.get_all(
		"Workflow Task",
		filters={"workflow_process": ("in", list(legacy))},
		fields=["name", "creation", "workflow_process"],
	):
		if get_datetime(task.creation) <= get_datetime(legacy[task.workflow_process].creation):
			groups[task.workflow_process].append(task.name)
	for name, tasks in groups.items():
		frappe.db.set_value(
			"Workflow Process", name, "legacy_task_names", json.dumps(sorted(tasks)), update_modified=False
		)
	return len(groups)


def execute() -> dict[str, int]:
	"""Repeatable after fixtures; no source save, reconciliation, votes or messages."""
	metadata.ensure_fields()
	orders = assign_selection_orders()
	metadata.ensure_constraints()
	adopted = adopt_legacy_sources()
	restore_legacy_link_bindings()
	return {"orders_assigned": orders, "sources_adopted": adopted}
