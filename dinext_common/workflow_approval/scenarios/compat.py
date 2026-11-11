"""Install Frappe compatibility once; keep routing and authority local to an operation."""

from __future__ import annotations

import copy
import importlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from threading import RLock
from typing import Any
from uuid import uuid4

import frappe

_STACK_KEY = "dinext_workflow_document_stack"
_AUTHORITY_KEY = "dinext_workflow_finalization_stack"
_NATIVE_ACTION_KEY = "dinext_workflow_native_action_stack"
_installed = False
_installing = False
_install_lock = RLock()
_originals: dict[str, Any] = {}


@dataclass(frozen=True)
class _DocumentScope:
	site: str | None
	document: Any


def _service():
	from dinext_common.workflow_approval.scenarios import service

	return service


def _ready() -> bool:
	if not getattr(frappe.local, "site", None):
		return False
	return bool(_service().is_ready())


def _value(document, key, default=None):
	return document.get(key, default) if hasattr(document, "get") else getattr(document, key, default)


@contextmanager
def document_scope(doc):
	"""Restore the caller even when another source of the same type fails."""
	previous = getattr(frappe.local, _STACK_KEY, ())
	entry = _DocumentScope(getattr(frappe.local, "site", None), doc)
	setattr(frappe.local, _STACK_KEY, (*previous, entry))
	try:
		yield doc
	finally:
		setattr(frappe.local, _STACK_KEY, previous)


def current_document(doctype: str | None = None):
	stack = getattr(frappe.local, _STACK_KEY, ())
	if not stack:
		return None
	entry = stack[-1]
	if entry.site != getattr(frappe.local, "site", None):
		return None
	if doctype and _value(entry.document, "doctype") != doctype:
		return None
	return entry.document


def _source_identity(doc):
	from frappe.utils import get_datetime

	created = _value(doc, "creation")
	return (_value(doc, "doctype"), _value(doc, "name"), str(get_datetime(created)) if created else "")


def _current_user():
	return getattr(frappe.session, "user", None)


@contextmanager
def authorized_finalization(doc):
	"""Grant only the selected source the engine's temporary save authority."""
	previous = getattr(frappe.local, _AUTHORITY_KEY, ())
	entry = (getattr(frappe.local, "site", None), _source_identity(doc), _current_user())
	setattr(frappe.local, _AUTHORITY_KEY, (*previous, entry))
	try:
		with document_scope(doc):
			yield doc
	finally:
		setattr(frappe.local, _AUTHORITY_KEY, previous)


def is_authorized_finalization(doc, user=None) -> bool:
	stack = getattr(frappe.local, _AUTHORITY_KEY, ())
	actor = _current_user()
	return bool(stack and (user is None or user == actor) and stack[-1] == (
		getattr(frappe.local, "site", None), _source_identity(doc), actor,
	))


def clear_context(*args, **kwargs) -> None:
	"""Clear a completed request/job boundary, including before metadata is installed."""
	setattr(frappe.local, _STACK_KEY, ())
	setattr(frappe.local, _AUTHORITY_KEY, ())
	setattr(frappe.local, _NATIVE_ACTION_KEY, ())


def initialize(*args, **kwargs) -> None:
	"""Entry hook for HTTP, jobs, tests and migration startup."""
	install()
	# Operation scopes own restoration. Do not destroy a nested synchronous job's caller.
	if current_document() is None:
		clear_context()


def cleanup(*args, **kwargs) -> None:
	"""Clear finished boundaries while preserving a synchronous job's outer scope."""
	if current_document() is None:
		clear_context()


def _preserve_whitelist(original, replacement) -> None:
	for registry_name in ("whitelisted", "guest_methods", "xss_safe_methods"):
		registry = getattr(frappe, registry_name, ())
		if original in registry and replacement not in registry:
			registry.append(replacement)
	methods = getattr(frappe, "allowed_http_methods_for_whitelisted_func", {})
	if original in methods:
		methods[replacement] = list(methods[original])


def replace_function(original, replacement):
	"""Rebind exported/imported aliases while retaining Frappe's HTTP contract."""
	_preserve_whitelist(original, replacement)
	for module in tuple(sys.modules.values()):
		if module is None or getattr(module, "__name__", "") == __name__:
			continue
		for name, value in tuple(vars(module).items()):
			if value is original:
				setattr(module, name, replacement)
	return replacement


def _normalized_document(doc, *, load=False):
	from frappe.model.document import Document

	if not isinstance(doc, Document):
		doc = frappe.get_doc(frappe.parse_json(doc))
		load = True
	if load:
		doc.load_from_db()
	return doc


def _wrap_document(original):
	@wraps(original)
	def scoped(self, *args, **kwargs):
		with document_scope(self):
			try:
				return original(self, *args, **kwargs)
			finally:
				if original.__name__ == "validate_workflow":
					_clear_preparation_authority(self)

	return scoped


def _wrap_permission(original):
	@wraps(original)
	def has_permission(self, permtype="read", *, debug=False, user=None):
		if permtype in {"read", "write", "submit", "cancel"} and is_authorized_finalization(self, user=user):
			return True
		return original(self, permtype, debug=debug, user=user)

	return has_permission


def _clear_preparation_authority(doc):
	flags = getattr(doc, "flags", None)
	if flags is not None:
		flags.workflow_scenario_prepared = False
		flags.workflow_scenario_prepared_workflow = None


def _workflow_name(doctype):
	if not _ready():
		return _originals["get_workflow_name"](doctype)
	doc = current_document(doctype)
	if doc is not None and _service().supports_doctype(doctype):
		context = _service().workflow_context(doc)
		return context[0] if context else None
	# This legacy path answers catalog/presence queries; it never stores a document choice.
	names = frappe.get_all(
		"Workflow",
		filters={"document_type": doctype, "is_active": 1},
		pluck="name",
		order_by="custom_selection_order asc, name asc",
		limit_page_length=1,
	)
	return names[0] if names else None


def _workflow(doctype):
	if _ready() and (doc := current_document(doctype)) is not None and _service().supports_doctype(doctype):
		context = _service().workflow_context(doc)
		if context:
			return context[1]
		frappe.throw(frappe._("No matching Workflow for this document"), frappe.DoesNotExistError)
	return _originals["get_workflow"](doctype)


def _wrap_transitions(original):
	@wraps(original)
	def transitions(doc, workflow=None, raise_exception=False):
		if not _ready():
			return original(doc, workflow, raise_exception)
		doc = _normalized_document(doc)
		with document_scope(doc):
			if not _service().supports_doctype(doc.doctype):
				return original(doc, workflow, raise_exception)
			context = _service().workflow_context(doc)
			if not context:
				return []
			if workflow is not None and _value(workflow, "name") != context[0]:
				if raise_exception:
					from frappe.model.workflow import WorkflowTransitionError

					raise WorkflowTransitionError
				return []
			workflow = workflow or context[1]
			return original(doc, workflow, raise_exception)

	return transitions


def _wrap_validator(original):
	@wraps(original)
	def validate(doc):
		if not _ready() or not _service().supports_doctype(_value(doc, "doctype")):
			return original(doc)
		with document_scope(doc):
			context = _service().workflow_context(doc)
			if not context:
				return
			workflow_name, workflow, state_field, state = context
			flags = getattr(doc, "flags", None)
			prepared = _value(flags, "workflow_scenario_prepared", False)
			authorized_workflow = _value(flags, "workflow_scenario_prepared_workflow")
			initial_state = workflow.states[0].state if workflow.states else None
			before = getattr(doc, "_doc_before_save", None)
			if prepared and authorized_workflow == workflow_name and state == initial_state and before:
				# Only a service-authorized candidate reset gets a virtual initial predecessor.
				doc._doc_before_save = copy.copy(before)
				doc._doc_before_save.set(state_field, initial_state)
			try:
				return original(doc)
			finally:
				doc._doc_before_save = before
				_clear_preparation_authority(doc)

	return validate


def _wrap_apply(original):
	@wraps(original)
	def apply(doc, action):
		if not _ready():
			return original(doc, action)
		doc = _normalized_document(doc, load=True)
		with document_scope(doc):
			if not _service().supports_doctype(doc.doctype):
				return original(doc, action)
			if getattr(frappe.flags, "in_dinext_workflow_finalization", False):
				return original(doc, action)
			from dinext_common.workflow_approval.lifecycle import is_engine_enabled

			if is_engine_enabled():
				from dinext_common.workflow_approval import api

				# Native imported aliases must accept one personal vote, including quorum/comment checks.
				api.apply_workflow(doc, action)
				return frappe.get_doc(doc.doctype, doc.name)
			service = _service()
			service.ensure_context(doc, persist_state=True)
			context = service.workflow_context(doc)
			if not context:
				return original(doc, action)
			from frappe.model.workflow import has_approval_access

			# Check the same accepted native action before pinning, including self-approval.
			transitions = _originals["get_transitions"](doc, context[1])
			transition = next((row for row in reversed(transitions) if row.action == action), None)
			if not transition or not has_approval_access(frappe.session.user, doc, transition):
				return original(doc, action)
			process_id = service.get_context(doc).get("process_id")
			savepoint = f"workflow_native_{uuid4().hex}"
			frappe.db.savepoint(savepoint)
			try:
				service.start_cascade(doc, manual=True)
				service.pin_process(doc, process_id=process_id)
				with _native_action(doc):
					result = original(doc, action)
				if result is not None:
					_complete_native_transition(result, context[0], process_id)
			except Exception:
				frappe.db.rollback(save_point=savepoint)
				raise
			return result

	return apply


@contextmanager
def _native_action(doc):
	previous = getattr(frappe.local, _NATIVE_ACTION_KEY, ())
	entry = (getattr(frappe.local, "site", None), _source_identity(doc))
	setattr(frappe.local, _NATIVE_ACTION_KEY, (*previous, entry))
	try:
		yield
	finally:
		setattr(frappe.local, _NATIVE_ACTION_KEY, previous)


def _complete_native_transition(doc, workflow_name, process_id) -> bool:
	service = _service()
	finished = service.finish_transition(doc, workflow_name=workflow_name, process_id=process_id)
	if finished:
		service.ensure_context(doc, persist_state=True, strict=False)
		from dinext_common.workflow_approval.lifecycle import is_engine_enabled

		if is_engine_enabled():
			from dinext_common.workflow_approval.engine import reconcile_source

			reconcile_source(doc)
	return finished


def native_submission_completed(doc, method=None) -> None:
	"""Finish a legacy queued native action after its worker successfully saves the source."""
	if not _ready() or not _service().supports_doctype(doc.doctype):
		return
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if is_engine_enabled():
		return
	identity = (getattr(frappe.local, "site", None), _source_identity(doc))
	if identity in getattr(frappe.local, _NATIVE_ACTION_KEY, ()):
		# Immediate native actions finish after their Workflow comment and other side effects.
		return
	service = _service()
	process = service.active_process(doc)
	if not process or process.status != "Running":
		return
	workflow = frappe.get_doc("Workflow", process.workflow)
	state = str(doc.get(workflow.workflow_state_field) or "")
	if state == str(process.current_state or "") or not service.is_terminal(workflow, state):
		return
	with document_scope(doc):
		_complete_native_transition(doc, process.workflow, process.name)


def _wrap_catalog(original):
	@wraps(original)
	def load_workflows(self):
		if not _ready() or not _service().supports_doctype(self.name):
			return original(self)
		names = frappe.get_all(
			"Workflow", filters={"document_type": self.name}, pluck="name",
			order_by="custom_selection_order asc, name asc",
		)
		workflows = [frappe.get_doc("Workflow", name) for name in names]
		state_names = {row.state for workflow in workflows for row in workflow.get("states") or [] if row.state}
		existing_states = set(frappe.get_all("Workflow State", filters={"name": ["in", list(state_names)]}, pluck="name")) if state_names else set()
		documents, seen_states = [], set()
		for workflow in workflows:
			documents.append(workflow)
			for row in workflow.get("states") or []:
				if row.state and row.state not in seen_states:
					seen_states.add(row.state)
					# Historical inactive definitions can outlive their styling master.
					# Keep their catalog entry without creating data or blocking another form.
					documents.append(frappe.get_doc("Workflow State", row.state) if row.state in existing_states else
						frappe.get_doc({"doctype": "Workflow State", "name": row.state, "workflow_state_name": row.state}))
		self.set("__workflow_docs", documents)

	return load_workflows


def _wrap_source_helper(original):
	@wraps(original)
	def scoped(doc, *args, **kwargs):
		if not _ready():
			return original(doc, *args, **kwargs)
		with document_scope(_normalized_document(doc)):
			return original(doc, *args, **kwargs)

	return scoped


def _wrap_legacy_actions(original):
	scoped = _wrap_source_helper(original)

	@wraps(original)
	def process(doc, state):
		if state != "on_trash" and _ready() and _service().supports_doctype(_value(doc, "doctype")):
			from dinext_common.workflow_approval.lifecycle import is_engine_enabled

			if is_engine_enabled():
				return
		return scoped(doc, state)

	return process


def _install_erpnext_adapter():
	try:
		accounts = importlib.import_module("erpnext.controllers.accounts_controller")
	except ModuleNotFoundError as error:
		if error.name and error.name.split(".")[0] == "erpnext":
			return
		raise
	original = accounts.update_child_qty_rate

	@wraps(original)
	def update_child_qty_rate(parent_doctype, trans_items, parent_doctype_name, child_docname="items"):
		if not _ready():
			return original(parent_doctype, trans_items, parent_doctype_name, child_docname)
		with document_scope(frappe.get_doc(parent_doctype, parent_doctype_name)):
			return original(parent_doctype, trans_items, parent_doctype_name, child_docname)

	replace_function(original, update_child_qty_rate)


def install() -> None:
	"""Install DB-free wrappers exactly once, independent of the first site's settings."""
	global _installed, _installing
	with _install_lock:
		if _installed or _installing:
			return
		_installing = True
		try:
			from frappe.desk.form.meta import FormMeta
			from frappe.model import workflow
			from frappe.model.document import Document
			from frappe.workflow.doctype.workflow_action import workflow_action

			for name in ("get_workflow_name", "get_workflow", "get_transitions", "validate_workflow", "apply_workflow"):
				_originals[name] = getattr(workflow, name)
			for name in ("insert", "_save", "run_method", "validate_workflow"):
				setattr(Document, name, _wrap_document(getattr(Document, name)))
			Document.has_permission = _wrap_permission(Document.has_permission)
			for name, replacement in (
				("get_workflow_name", wraps(_originals["get_workflow_name"])(_workflow_name)),
				("get_workflow", wraps(_originals["get_workflow"])(_workflow)),
				("get_transitions", _wrap_transitions(_originals["get_transitions"])),
				("validate_workflow", _wrap_validator(_originals["validate_workflow"])),
				("apply_workflow", _wrap_apply(_originals["apply_workflow"])),
			):
				replace_function(_originals[name], replacement)
			FormMeta.load_workflows = _wrap_catalog(FormMeta.load_workflows)
			original = workflow_action.process_workflow_actions
			replace_function(original, _wrap_legacy_actions(original))
			for name in ("get_doc_workflow_state", "get_email_template_from_workflow", "send_workflow_action_email", "get_common_email_args"):
				original = getattr(workflow_action, name)
				replace_function(original, _wrap_source_helper(original))
			_install_erpnext_adapter()
			from dinext_common.workflow_approval.scenarios import timesheet_actions, timesheets

			timesheets.install()
			timesheet_actions.install()
			_installed = True
		finally:
			_installing = False
