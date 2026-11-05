"""Source-aware task authorization for approval APIs and public number cards."""

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
	if not frappe.get_meta(doctype).is_virtual and not frappe.db.exists(doctype, name):
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
