"""Source-authorized Workflow context for forms and list rows."""

from __future__ import annotations

import json
from typing import Any, TypedDict

import frappe
from frappe import _

from dinext_common.workflow_approval.scenarios import service


class WorkflowContextFormInput(TypedDict):
	doctype: str
	name: str


class WorkflowContextsFormInput(TypedDict):
	doctype: str
	names: str | list[str]


class WorkflowContextErrorResponse(TypedDict, total=False):
	error: str | None
	managed: bool


class WorkflowContextResponse(WorkflowContextErrorResponse):
	context: service.WorkflowContext
	definition: dict[str, Any] | None


def _value(row, fieldname):
	return row.get(fieldname) if isinstance(row, dict) else getattr(row, fieldname, None)


def _definition(name: str | None) -> dict[str, Any] | None:
	if not name:
		return None
	workflow = frappe.get_cached_doc("Workflow", name)
	result = {
		field: _value(workflow, field)
		for field in ("name", "document_type", "workflow_state_field", "override_status", "allow_self_approval")
	}
	# Do not disclose conditions, routing expressions or notification configuration.
	result["states"] = [
		{field: _value(row, field) for field in (
			"state", "allow_edit", "doc_status", "update_field", "update_value", "avoid_status_override",
		)}
		for row in (_value(workflow, "states") or [])
	]
	result["transitions"] = [
		{field: _value(row, field) for field in (
			"state", "action", "next_state", "allowed", "allow_self_approval", "custom_transition_uuid",
			"custom_comment_is_required",
		)}
		for row in (_value(workflow, "transitions") or [])
	]
	return result


def describe_document(doc) -> WorkflowContextResponse:
	context = service.get_context(doc)
	return {"context": context, "definition": _definition(context.get("workflow")),
		"error": service.get_routing_error(doc), "managed": service.supports_doctype(_value(doc, "doctype"))}


def _source(doctype: str, name: str):
	if not isinstance(doctype, str) or not doctype or not isinstance(name, str) or not name:
		raise frappe.ValidationError(_("Expected a source type and a list of document names"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc


@frappe.whitelist()
def get_workflow_context(doctype: str, name: str) -> WorkflowContextResponse:
	"""Describe the selected process and safe presentation metadata for a readable source."""
	return describe_document(_source(doctype, name))


@frappe.whitelist()
def get_workflow_document(doctype: str, name: str) -> dict[str, Any]:
	"""Return a readable source snapshot with context for conflict-merge form resynchronization."""
	doc = _source(doctype, name)
	onload(doc)
	doc.apply_fieldlevel_read_permissions()
	return doc.as_dict()


@frappe.whitelist()
def get_workflow_contexts(doctype: str, names: str | list[str]) -> dict[str, WorkflowContextResponse]:
	"""Describe only readable sources from an exact, bounded list selection."""
	if not isinstance(doctype, str) or not doctype:
		raise frappe.ValidationError(_("Expected a source type and a list of document names"))
	try:
		parsed = json.loads(names) if isinstance(names, str) else names
	except (ValueError, TypeError):
		raise frappe.ValidationError(_("Expected a source type and a list of document names"))
	if not isinstance(parsed, list) or any(not isinstance(name, str) or not name for name in parsed):
		raise frappe.ValidationError(_("Expected a source type and a list of document names"))
	unique = list(dict.fromkeys(parsed))
	if len(unique) > 500:
		raise frappe.ValidationError(_("Bulk approval supports at most 500 documents"))
	result = {}
	for name in unique:
		try:
			doc = _source(doctype, name)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue
		result[name] = describe_document(doc)
	return result


def onload(doc, method=None) -> None:
	"""Preload context before Desk performs its first synchronous readonly calculation."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled() or not service.supports_doctype(_value(doc, "doctype")):
		return
	envelope = describe_document(doc)
	doc.set_onload("dinext_workflow_context", envelope["context"])
	doc.set_onload("dinext_workflow_definition", envelope["definition"])
	doc.set_onload("dinext_workflow_error", envelope.get("error"))
