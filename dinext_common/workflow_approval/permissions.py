"""Source-aware permissions for Workflow Task and Workflow Action."""

from __future__ import annotations

from typing import Any

import frappe

READ_PERMISSION_TYPES = {"read", "report", "export", "print", "email", "select"}
MUTATING_PERMISSION_TYPES = {"create", "write", "delete", "share", "submit", "cancel"}


def _get(doc: object, fieldname: str, default: Any = None) -> Any:
	if isinstance(doc, dict):
		return doc.get(fieldname, default)
	if hasattr(doc, "get"):
		return doc.get(fieldname, default)
	return getattr(doc, fieldname, default)


def _is_system_manager(user: str) -> bool:
	if user == "Administrator":
		return True
	try:
		return "System Manager" in frappe.get_roles(user)
	except AttributeError:
		return False


def _has_source_read_permission(task: object, user: str) -> bool:
	doctype = _get(task, "reference_doctype") or _get(task, "doc")
	name = _get(task, "reference_name") or _get(task, "wt_docname")
	if not doctype or not name:
		return False
	return bool(
		frappe.has_permission(
			doctype,
			ptype="read",
			doc=name,
			user=user,
			throw=False,
		)
	)


def _is_workflow_monitor(task: object, user: str) -> bool:
	workflow = _get(task, "workflow")
	if not workflow:
		return False
	monitor_roles = frappe.get_all(
		"Has Role",
		filters={
			"parent": workflow,
			"parenttype": "Workflow",
			"parentfield": "custom_approval_monitor_roles",
		},
		pluck="role",
	)
	return not set(monitor_roles).isdisjoint(frappe.get_roles(user))


def is_workflow_monitor(task: object, user: str | None = None) -> bool:
	return _is_workflow_monitor(task, user or frappe.session.user)


def get_monitorable_workflows(user: str | None = None) -> list[str]:
	user = user or frappe.session.user
	if _is_system_manager(user):
		return frappe.get_all("Workflow", filters={"is_active": 1}, pluck="name")
	roles = frappe.get_roles(user)
	if not roles:
		return []
	return frappe.get_all(
		"Has Role",
		filters={
			"parenttype": "Workflow",
			"parentfield": "custom_approval_monitor_roles",
			"role": ("in", roles),
		},
		pluck="parent",
		distinct=True,
	)


def get_workflow_task_query_conditions(user: str | None = None) -> str:
	"""Deny the standard list because Dynamic Link source access is not SQL-expressible."""
	user = user or frappe.session.user
	return "" if _is_system_manager(user) else "1=0"


def get_workflow_action_query_conditions(user: str | None = None) -> str:
	"""Use custom source-aware APIs instead of leaking Dynamic Link rows in lists."""
	user = user or frappe.session.user
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.workflow.doctype.workflow_action.workflow_action import (
			get_permission_query_conditions as core_conditions,
		)

		return core_conditions(user)
	return "" if _is_system_manager(user) else "1=0"


def has_workflow_task_permission(
	doc: object,
	ptype: str = "read",
	user: str | None = None,
) -> bool:
	"""Allow immutable task reads only to source-authorized principals."""
	user = user or frappe.session.user
	if ptype in MUTATING_PERMISSION_TYPES or ptype not in READ_PERMISSION_TYPES:
		return False
	if _is_system_manager(user):
		return True

	approver = _get(doc, "approver") or _get(doc, "user")
	if _get(doc, "source_deleted_at"):
		return approver == user
	if approver != user and not _is_workflow_monitor(doc, user):
		return False
	return _has_source_read_permission(doc, user)


def _has_core_action_access(doc: object, user: str) -> bool:
	if _is_system_manager(user) or _get(doc, "user") == user:
		return True
	permitted_roles = {
		_get(row, "role")
		for row in (_get(doc, "permitted_roles", []) or [])
		if _get(row, "role")
	}
	return not permitted_roles.isdisjoint(frappe.get_roles(user))


def has_workflow_action_permission(
	doc: object,
	ptype: str = "read",
	user: str | None = None,
) -> bool:
	"""Compose core action access with its active source-aware Workflow Task."""
	user = user or frappe.session.user
	if not _has_core_action_access(doc, user):
		return False

	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	task_name = _get(doc, "custom_workflow_task")
	if not task_name:
		return not is_engine_enabled()
	if ptype in MUTATING_PERMISSION_TYPES or ptype not in READ_PERMISSION_TYPES:
		return False
	try:
		task = frappe.get_doc("Workflow Task", task_name)
	except frappe.DoesNotExistError:
		return False
	return has_workflow_task_permission(task, "read", user)


PUBLIC_APPROVAL_NUMBER_CARDS = frozenset(
	{
		"My open approvals",
		"Новые сегодня",
		"My completed approvals",
		"Автоматически выполнено за 30 дней",
	}
)


def has_public_number_card_permission(doc, ptype="read", user=None, debug=False):
	"""Allow read of the public approval cards.

	Frappe's Number Card controller denies Custom cards that have no
	document_type unless the user is a System Manager. These cards count
	through whitelisted methods, so a read-only approver must still see them.
	"""
	if ptype not in READ_PERMISSION_TYPES:
		return None
	if _get(doc, "name") not in PUBLIC_APPROVAL_NUMBER_CARDS:
		return None
	if not _get(doc, "is_public"):
		return None
	return True
