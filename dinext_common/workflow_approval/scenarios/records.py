"""Service-owned process records retain the source document's read boundary."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import get_datetime

READ_TYPES = {"read", "select", "report", "export", "print", "email"}
SERVICE_TYPES = {"Workflow Process", "Workflow Document Context"}


def require_service_write(doc: object) -> None:
	if not doc.flags.get("in_workflow_scenario_service"):
		frappe.throw(
			_("Workflow process records can only be changed by the Workflow engine"), frappe.PermissionError
		)


def has_record_permission(doc: object, ptype: str = "read", user: str | None = None) -> bool:
	if ptype not in READ_TYPES:
		return False
	if not doc.get("reference_doctype") or not doc.get("reference_name") or not doc.get("source_created_at"):
		return False
	try:
		created_at = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "creation")
	except frappe.DoesNotExistError:
		return False
	if not created_at or get_datetime(created_at) != get_datetime(doc.source_created_at):
		return False
	from dinext_common.workflow_approval.permissions import _has_source_read_permission

	return _has_source_read_permission(doc, user or frappe.session.user)


@contextmanager
def _read_as_user(user: str):
	"""Some source permission hooks read session.user instead of their user argument."""
	previous_user = frappe.session.user
	previous_user_perms = getattr(frappe.local, "user_perms", None)
	previous_role_permissions = getattr(frappe.local, "role_permissions", {})
	try:
		if previous_user != user:
			frappe.session.user = user
			frappe.local.user_perms = None
			frappe.local.role_permissions = {}
		yield
	finally:
		if previous_user != user:
			frappe.session.user = previous_user
			frappe.local.user_perms = previous_user_perms
			frappe.local.role_permissions = previous_role_permissions


def _query_conditions(doctype: str, user: str | None = None) -> str:
	"""Batch source list permissions and creation identities before exposing audit rows."""
	user = user or frappe.session.user
	rows = frappe.get_all(
		doctype, fields=["name", "reference_doctype", "reference_name", "source_created_at"]
	)
	by_type = defaultdict(list)
	for row in rows:
		if row.reference_doctype not in SERVICE_TYPES:
			by_type[row.reference_doctype].append(row)
	readable = []
	for source_type, records in by_type.items():
		if not source_type:
			continue
		try:
			with _read_as_user(user):
				sources = frappe.get_list(
					source_type,
					filters={"name": ("in", sorted({row.reference_name for row in records}))},
					fields=["name", "creation"],
					limit_page_length=0,
					user=user,
				)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue
		identities = {row.name: get_datetime(row.creation) for row in sources}
		readable.extend(
			row.name
			for row in records
			if row.source_created_at
			and identities.get(row.reference_name) == get_datetime(row.source_created_at)
		)
	if not readable:
		return "1=0"
	table = frappe.qb.DocType(doctype)
	return table.name.isin(readable).get_sql()


def process_query_conditions(user: str | None = None) -> str:
	return _query_conditions("Workflow Process", user)


def context_query_conditions(user: str | None = None) -> str:
	return _query_conditions("Workflow Document Context", user)
