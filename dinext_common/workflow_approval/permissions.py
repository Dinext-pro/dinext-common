"""Source-aware task authorization for approval APIs and public number cards."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from importlib import import_module
from typing import Any

import frappe
from frappe.utils import cint
from frappe.utils.caching import request_cache

READ_PERMISSION_TYPES = {"read", "report", "export", "print", "email", "select"}
MUTATING_PERMISSION_TYPES = {"create", "write", "delete", "share", "submit", "cancel"}

_task_candidates = ContextVar("workflow_task_read_candidates", default=None)


def workflow_query_protection_configured() -> bool:
	conditions = frappe.get_hooks("permission_query_conditions", {})
	validator = frappe.get_hooks("doc_events", {}).get("DocShare", {}).get("validate", ())
	return (
		"dinext_common.workflow_approval.permissions.validate_workflow_docshare" in validator
		and all(conditions.get(doctype) for doctype in WORKFLOW_READ_DOCTYPES)
		and not any(_has_workflow_share(doctype, None, None) for doctype in WORKFLOW_READ_DOCTYPES)
	)


def supports_final_task_permission_queries() -> bool:
	# Compatibility for apps that check whether Common protects task queries.
	return workflow_query_protection_configured()

@contextmanager
def task_read_candidates(rows, source_permissions):
	"""Bound the existing final SQL permission hook to this read's candidates."""
	user = frappe.session.user
	token = _task_candidates.set((user, rows, source_permissions,
		get_task_read_checker(user, source_permissions=source_permissions)))
	try:
		yield
	finally:
		_task_candidates.reset(token)


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


@contextmanager
def _quiet_permission_checks():
	"""A denied candidate is an omitted row, so keep its diagnostics out of Desk."""
	previous_mute = frappe.flags.mute_messages
	previous_error = frappe.flags.error_message
	frappe.flags.mute_messages = True
	try:
		yield
	finally:
		frappe.flags.mute_messages = previous_mute
		frappe.flags.error_message = previous_error


def _has_source_read_permission(task: object, user: str) -> bool:
	doctype, name = _source_reference(task)
	if not doctype or not name:
		return False
	previous_user = frappe.session.user
	previous_user_perms = getattr(frappe.local, "user_perms", None)
	previous_role_permissions = getattr(frappe.local, "role_permissions", {})
	try:
		# The installed DocType Permission hook reads as session.user even when
		# has_permission receives user=. Preserve the HTTP session id.
		if previous_user != user:
			frappe.session.user = user
			frappe.local.user_perms = None
			frappe.local.role_permissions = {}
		with _quiet_permission_checks():
			meta = frappe.get_meta(doctype)
			source = name
			if not meta.is_virtual:
				from frappe.model.base_document import get_controller
				from frappe.model.document import Document

				if get_controller(doctype).has_permission is not Document.has_permission:
					return bool(frappe.get_doc(doctype, name).has_permission("read", user=user))
				if _uses_standard_document_loader(doctype, meta, user):
					source = frappe.get_doc(doctype, name)
				elif not frappe.db.exists(doctype, name):
					return False
			return bool(frappe.has_permission(doctype, ptype="read", doc=source, user=user, throw=False))
	except (frappe.DoesNotExistError, frappe.PermissionError):
		return False
	finally:
		if previous_user != user:
			frappe.session.user = previous_user
			frappe.local.user_perms = previous_user_perms
			frappe.local.role_permissions = previous_role_permissions


def _uses_standard_document_loader(doctype: str, meta, user: str) -> bool:
	"""A normal row loader fails closed for missing documents before checking access."""
	from frappe.model.base_document import get_controller
	from frappe.model.document import Document

	if user == "Administrator" or meta.issingle or meta.istable:
		return False
	controller = get_controller(doctype)
	return controller.__init__ is Document.__init__ and controller.load_from_db is Document.load_from_db


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
		return frappe.get_all("Workflow", pluck="name")
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
	scope = _task_candidates.get()
	if scope and scope[0] == user:
		return scope[3](doc)
	if name := _get(doc, "name"):
		require_no_workflow_shares("Workflow Task", user, name)
	return _can_read_task(
		doc,
		user,
		_is_system_manager(user),
		lambda task: _is_workflow_monitor(task, user),
		lambda task: _has_source_read_permission(task, user),
	)


def _can_read_task(doc, user, is_manager, can_monitor, can_read_source) -> bool:
	approver = _get(doc, "approver") or _get(doc, "user")
	if _get(doc, "source_deleted_at"):
		return is_manager or approver == user
	if not is_manager and approver != user and not can_monitor(doc):
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
	with _quiet_permission_checks():
		for doctype, names in sources.items():
			try:
				visible = batch_read(doctype, names)
			except (frappe.DoesNotExistError, frappe.PermissionError):
				continue  # The exact single-document check handles these candidates.
			source_permissions.update(((doctype, name), name in visible) for name in names)


def public_source_title_field(meta) -> str | None:
	"""Only store titles from fields readable at the document's base permission level."""
	title_field = meta.title_field
	field = meta.get_field(title_field) if title_field else None
	if field and not int(field.permlevel or 0) and field.fieldtype != "Password":
		return title_field
	return None


def sanitize_restricted_task_titles(doctype: str | None = None) -> None:
	if not frappe.db.table_exists("Workflow Task"):
		return
	task = frappe.qb.DocType("Workflow Task")
	todo = frappe.qb.DocType("ToDo")
	doctypes = [doctype] if doctype else frappe.get_all("Workflow Task", pluck="reference_doctype", distinct=True)
	for source_type in doctypes:
		if not source_type or not frappe.db.exists("DocType", source_type):
			continue
		if public_source_title_field(frappe.get_meta(source_type, cached=False)):
			continue
		restricted = (task.reference_doctype == source_type) & (task.source_title != task.reference_name)
		(
			frappe.qb.update(todo)
			.set(todo.description, frappe._("Workflow approval"))
			.where((todo.reference_type == "Workflow Task") &
				todo.reference_name.isin(frappe.qb.from_(task).select(task.name).where(restricted)))
		).run()
		(
			frappe.qb.update(task)
			.set(task.source_title, task.reference_name)
			.where(restricted)
		).run()


def sanitize_tasks_after_title_permission_change(doc, method=None) -> None:
	if doc.get("property") in {"permlevel", "title_field"} and doc.get("doc_type"):
		sanitize_restricted_task_titles(doc.doc_type)


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
		return _can_read_task(row, user, is_manager, can_monitor, can_read_source)

	return can_read


PUBLIC_APPROVAL_NUMBER_CARDS = frozenset(
	{
		"My open approvals",
		"Новые сегодня",
		"My completed approvals",
		"Автоматически выполнено за 30 дней",
		"Overdue Approval Assignments",
		"On-time Approvals",
		"Approvals Completed Late",
		"Approval Deadline Errors",
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


WORKFLOW_SERVICE_DOCTYPES = frozenset({"Workflow Task", "Workflow Process", "Workflow Document Context"})
WORKFLOW_READ_DOCTYPES = WORKFLOW_SERVICE_DOCTYPES | {"Number Card"}
WORKFLOW_SHARE_ERROR = "Workflow access follows the source document and assigned roles. Remove the direct sharing grant."


class WorkflowReadBlocked(frappe.ValidationError):
	# Other permission hooks may catch PermissionError and fall back to DocShare.
	http_status_code = 403


def validate_workflow_docshare(doc, method=None):
	protected = doc.share_doctype in WORKFLOW_SERVICE_DOCTYPES or (
		doc.share_doctype == "Number Card" and doc.share_name in MONITORING_APPROVAL_NUMBER_CARDS
	)
	if protected and any(cint(doc.get(field)) for field in ("read", "write", "submit", "share")):
		frappe.throw(frappe._(WORKFLOW_SHARE_ERROR), frappe.PermissionError)


@request_cache
def _has_workflow_share(doctype, user, name):
	share = frappe.qb.DocType("DocShare")
	query = frappe.qb.from_(share).select(share.name).where(
		(share.share_doctype == doctype) & (share.read == 1)
	)
	if doctype == "Number Card":
		query = query.where(share.share_name.isin(sorted(MONITORING_APPROVAL_NUMBER_CARDS)))
	if user is not None:
		query = query.where((share.user == user) | (share.everyone == 1))
	if name is not None:
		query = query.where(share.share_name == name)
	return bool(query.limit(1).run())


def require_no_workflow_shares(doctype, user, name=None):
	if user != "Administrator" and _has_workflow_share(doctype, user, name):
		frappe.throw(frappe._(WORKFLOW_SHARE_ERROR), WorkflowReadBlocked)


def may_read_monitoring_cards(user):
	return _is_system_manager(user) or bool(get_monitorable_workflows(user))


def set_monitoring_card_visibility(doc, method=None):
	if doc.name in MONITORING_APPROVAL_NUMBER_CARDS:
		doc.is_public = 0
		doc.owner = "Administrator"


def has_public_number_card_permission(doc, ptype="read", user=None, debug=False):
	"""Apply the access rules for the approval widgets shipped by Common."""
	name = _get(doc, "name")
	is_approval_card = name in PUBLIC_APPROVAL_NUMBER_CARDS or name in MONITORING_APPROVAL_NUMBER_CARDS
	if ptype not in READ_PERMISSION_TYPES:
		if (
			ptype in MUTATING_PERMISSION_TYPES
			and is_approval_card
			and _get(doc, "is_standard")
			and _get(doc, "module") == "Dinext Common"
			and _get(doc, "document_type") == "Workflow Task"
		):
			return _is_system_manager(user or frappe.session.user)
		return None
	name = _get(doc, "name")
	if name in MONITORING_APPROVAL_NUMBER_CARDS:
		user = user or frappe.session.user
		require_no_workflow_shares("Number Card", user, name)
		return may_read_monitoring_cards(user)
	if _get(doc, "is_public") and name in PUBLIC_APPROVAL_NUMBER_CARDS:
		return True
	return None


def get_approval_number_card_query_conditions(user=None):
	"""Apply the same monitoring restriction to the Number Card list."""
	user = user or frappe.session.user
	require_no_workflow_shares("Number Card", user)
	if may_read_monitoring_cards(user):
		return None

	card = frappe.qb.DocType("Number Card")
	return card.name.notin(sorted(MONITORING_APPROVAL_NUMBER_CARDS)).get_sql(
		quote_char="`", with_namespace=True
	)


def task_principal_filters(user: str) -> list:
	"""Return a conservative SQL prefilter for the final task policy."""
	if _is_system_manager(user):
		return []
	filters = [["approver", "=", user], ["user", "=", user]]
	if workflows := get_monitorable_workflows(user):
		filters.append(["workflow", "in", workflows])
	return filters


def get_workflow_task_permission_query_conditions(user: str | None = None) -> str:
	"""Narrow standard lists using the same policy as document reads.

	Candidates are internal audit records: get_all deliberately avoids recursively
	invoking this Task hook. Authorization is applied before names enter the SQL
	condition, with source/workflow checks cached only for this invocation.
	"""
	user = user or frappe.session.user
	require_no_workflow_shares("Workflow Task", user)
	scope = _task_candidates.get()
	if scope and scope[0] == user:
		can_read = scope[3]
		allowed = [row.name for row in scope[1] if can_read(row)]
		return frappe.qb.DocType("Workflow Task").name.isin(allowed).get_sql() if allowed else "1=0"
	source_permissions = {}
	can_read = get_task_read_checker(user, source_permissions=source_permissions)
	principal_filters = task_principal_filters(user)
	allowed = []
	filters = {}
	while True:
		rows = frappe.get_all(
			"Workflow Task",
			filters=filters,
			or_filters=principal_filters,
			fields=[
				"name", "approver", "user", "workflow", "reference_doctype",
				"reference_name", "doc", "wt_docname", "source_deleted_at",
			],
			order_by="name asc",
			limit_page_length=500,
		)
		prepare_source_permissions(rows, user, source_permissions)
		allowed.extend(row.name for row in rows if can_read(row))
		if len(rows) < 500:
			break
		filters = {"name": (">", rows[-1].name)}
	if not allowed:
		return "1=0"
	task = frappe.qb.DocType("Workflow Task")
	return task.name.isin(allowed).get_sql()
