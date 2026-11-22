"""Install approval metadata and migrate unambiguous legacy identifiers."""

from __future__ import annotations

import hashlib
import json

import frappe

from dinext_common.workflow_approval.metadata import (
	ensure_workflow_approval_desk_records,
	ensure_workflow_approval_custom_fields,
	ensure_workflow_approval_email_templates,
)
from dinext_common.workflow_approval.policy import policy_from_legacy_flag
from dinext_common.dinext_common.doctype.workflow_task.workflow_task import (
	on_doctype_update as ensure_workflow_task_indexes,
)


def _legacy_round_id(row: dict) -> str:
	identity = "\0".join(
		(
			"legacy",
			str(row.get("doc") or ""),
			str(row.get("wt_docname") or ""),
			str(row.get("state") or ""),
		)
	)
	return f"legacy-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"


def _migrate_transition_configuration() -> None:
	fields = [
		"name",
		"custom_all_users_with_role",
		"custom_parallel_approval_policy",
		"custom_transition_uuid",
	]
	for row in frappe.db.get_all("Workflow Transition", fields=fields):
		updates = {}
		if not row.custom_parallel_approval_policy:
			updates["custom_parallel_approval_policy"] = policy_from_legacy_flag(
				row.custom_all_users_with_role
			)
		# UUID canon is the fixture value. A generated hash here is wiped or
		# diverges from live manifests. after_migrate fills a still-empty UUID.
		if updates:
			frappe.db.set_value(
				"Workflow Transition",
				row.name,
				updates,
				update_modified=False,
			)


def _source_snapshot(doctype: str, name: str) -> dict:
	if not doctype or not name or not frappe.db.exists(doctype, name):
		return {}
	meta = frappe.get_meta(doctype)
	fields = ["creation", "owner"]
	if meta.title_field and meta.title_field not in fields:
		fields.append(meta.title_field)
	row = frappe.db.get_value(doctype, name, fields, as_dict=True) or {}
	return {
		"source_created_at": row.get("creation"),
		"source_owner": row.get("owner"),
		"source_title": row.get(meta.title_field) if meta.title_field else name,
	}


def _one_assignee(values: list[str], source: str, task_name: str) -> str | None:
	unique = sorted(set(filter(None, values)))
	if len(unique) > 1:
		raise RuntimeError(
			f"Ambiguous legacy Workflow Task assignee from {source}: {task_name}"
		)
	return unique[0] if unique else None


def _legacy_assignee(row: dict) -> str | None:
	todo_users = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Workflow Task",
			"reference_name": row.name,
			"status": "Open",
		},
		pluck="allocated_to",
	)
	if assignee := _one_assignee(todo_users, "ToDo", row.name):
		return assignee
	share_users = frappe.get_all(
		"DocShare",
		filters={
			"share_doctype": "Workflow Task",
			"share_name": row.name,
			"read": 1,
		},
		pluck="user",
	)
	if assignee := _one_assignee(share_users, "DocShare", row.name):
		return assignee
	try:
		assigned_users = frappe.parse_json(row.get("_assign") or "[]")
	except (TypeError, ValueError, json.JSONDecodeError):
		assigned_users = []
	if assignee := _one_assignee(assigned_users or [], "_assign", row.name):
		return assignee
	return row.user


def _migrate_legacy_tasks() -> None:
	if not frappe.db.table_exists("Workflow Task"):
		return
	rows = frappe.db.get_all(
		"Workflow Task",
		fields=[
			"name",
			"doc",
			"wt_docname",
			"user",
			"state",
			"status",
			"reference_doctype",
			"reference_name",
			"approver",
			"approval_round_id",
			"_assign",
		],
	)
	for row in rows:
		updates = {}
		reference_doctype = row.reference_doctype or row.doc
		reference_name = row.reference_name or row.wt_docname
		if not row.reference_doctype and reference_doctype:
			updates["reference_doctype"] = reference_doctype
		if not row.reference_name and reference_name:
			updates["reference_name"] = reference_name
		if not row.approver:
			if assignee := _legacy_assignee(row):
				updates["approver"] = assignee
		if not row.approval_round_id:
			updates["approval_round_id"] = _legacy_round_id(row)
		updates["round_status"] = "Open" if row.status == "Working" else "Transitioned"
		for key, value in _source_snapshot(reference_doctype, reference_name).items():
			if value is not None:
				updates[key] = value
		if updates:
			frappe.db.set_value("Workflow Task", row.name, updates, update_modified=False)


def execute() -> None:
	"""Apply backward-compatible approval metadata without running transitions."""
	ensure_workflow_approval_custom_fields()
	ensure_workflow_approval_email_templates()
	ensure_workflow_approval_desk_records()
	ensure_workflow_task_indexes()
	_migrate_transition_configuration()
	_migrate_legacy_tasks()
