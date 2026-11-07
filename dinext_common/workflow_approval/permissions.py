"""Source-aware task authorization for approval APIs and public number cards."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from functools import cache
from importlib import import_module
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


def _source_reference(task: object) -> tuple[str | None, str | None]:
	return (
		_get(task, "reference_doctype") or _get(task, "doc"),
		_get(task, "reference_name") or _get(task, "wt_docname"),
	)


def _has_source_read_permission(task: object, user: str) -> bool:
	doctype, name = _source_reference(task)
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
	return _can_read_task(
		doc,
		user,
		_is_system_manager(user),
		lambda task: _is_workflow_monitor(task, user),
		lambda task: _has_source_read_permission(task, user),
	)


def _can_read_task(doc, user, is_manager, can_monitor, can_read_source) -> bool:
	if is_manager:
		return True

	approver = _get(doc, "approver") or _get(doc, "user")
	if _get(doc, "source_deleted_at"):
		return approver == user
	if approver != user and not can_monitor(doc):
		return False
	return can_read_source(doc)


def _batch_read_helper():
	if "doctype_permission" not in frappe.get_installed_apps():
		return None
	module_name = "doctype_permission.doctype_permission.batch_read"
	try:
		return import_module(module_name).readable_document_names
	except ModuleNotFoundError as error:
		if error.name != module_name:
			raise
		return None


def prepare_source_permissions(rows, user, source_permissions):
	"""Resolve only new, non-archived source identities for this task read."""
	if user != frappe.session.user:
		return
	sources = defaultdict(set)
	for row in rows:
		key = _source_reference(row)
		if all(key) and not _get(row, "source_deleted_at") and key not in source_permissions:
			sources[key[0]].add(key[1])
	if not sources:
		return
	batch_read = _batch_read_helper()
	if batch_read is None:
		return
	for doctype, names in sources.items():
		visible = batch_read(doctype, names)
		source_permissions.update(((doctype, name), name in visible) for name in names)


def get_task_read_checker(
	user: str,
	*,
	monitored_only: bool = False,
	require_source: bool = False,
	source_permissions: dict[tuple[str, str], bool] | None = None,
) -> Callable[[object], bool]:
	"""Check each workflow and source once across the pages of one read."""

	@cache
	def workflow_allowed(workflow):
		return _is_workflow_monitor({"workflow": workflow}, user)

	@cache
	def source_allowed(doctype, name):
		if source_permissions is not None and (doctype, name) in source_permissions:
			return source_permissions[(doctype, name)]
		return _has_source_read_permission({"reference_doctype": doctype, "reference_name": name}, user)

	def can_monitor(row):
		return workflow_allowed(_get(row, "workflow"))

	def can_read_source(row):
		return source_allowed(*_source_reference(row))

	is_manager = _is_system_manager(user)

	def can_read(row):
		if monitored_only:
			return (is_manager or can_monitor(row)) and can_read_source(row)
		if require_source and is_manager:
			return bool(
				(_get(row, "source_deleted_at") and _get(row, "approver") == user) or can_read_source(row)
			)
		return _can_read_task(row, user, is_manager, can_monitor, can_read_source)

	return can_read


PUBLIC_APPROVAL_NUMBER_CARDS = frozenset(
	{
		"My open approvals",
		"Новые сегодня",
		"My completed approvals",
		"Автоматически выполнено за 30 дней",
	}
)


MONITORING_APPROVAL_NUMBER_CARDS = frozenset(
	{
		"Открытые раунды",
		"Сбои",
		"Самое долгое ожидание",
		"Решений за 30 дней",
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
	if not _get(doc, "is_public"):
		return None
	name = _get(doc, "name")
	if name in PUBLIC_APPROVAL_NUMBER_CARDS:
		return True
	if name in MONITORING_APPROVAL_NUMBER_CARDS:
		user = user or frappe.session.user
		return _is_system_manager(user) or bool(get_monitorable_workflows(user))
	return None
