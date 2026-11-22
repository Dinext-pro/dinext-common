"""Source-authorized Workflow context for forms and list rows."""

from __future__ import annotations

import json
from typing import TypedDict, cast

import frappe
from frappe import _
from frappe.model.base_document import BaseDocument
from frappe.model.document import Document

from dinext_common.workflow_approval.scenarios import service
from dinext_common.workflow_approval.scenarios.read import load_documents


class WorkflowContextsFormInput(TypedDict):
	doctype: str
	names: list[str]


class WorkflowStatePresentation(TypedDict):
	state: str
	allow_edit: str | None
	doc_status: str | int | None
	update_field: str | None
	update_value: str | None
	avoid_status_override: int | None


class WorkflowTransitionPresentation(TypedDict):
	state: str
	action: str
	next_state: str
	allowed: str | None
	allow_self_approval: int | None
	custom_transition_uuid: str | None
	custom_comment_is_required: int | None


class WorkflowPresentation(TypedDict):
	name: str
	document_type: str
	workflow_state_field: str
	override_status: int | None
	allow_self_approval: int | None
	states: list[WorkflowStatePresentation]
	transitions: list[WorkflowTransitionPresentation]


class WorkflowContextResponse(TypedDict):
	context: service.WorkflowContext
	definition: WorkflowPresentation | None
	error: str | None
	managed: bool


class WorkflowDocumentOnload(TypedDict, total=False):
	dinext_workflow_context: service.WorkflowContext
	dinext_workflow_definition: WorkflowPresentation | None
	dinext_workflow_error: str | None


# The source's other fields are defined by its own DocType.
WorkflowDocumentResponse = TypedDict(
	"WorkflowDocumentResponse",
	{"doctype": str, "name": str, "__onload": WorkflowDocumentOnload},
	total=False,
)


class _FormMetadataDocument(BaseDocument):
	"""A detached, allowlisted document for FormMeta and the Frappe JSON encoder."""

	def __init__(self, fields: dict[str, object]):
		self.__dict__.update(fields)

	def as_dict(self, no_nulls: bool = False) -> dict[str, object]:
		# The standard serializer uses the entire DocType schema, including virtual fields.
		return {
			key: [row.as_dict(no_nulls=no_nulls) for row in value] if isinstance(value, list) else value
			for key, value in vars(self).items()
			if not no_nulls or value is not None
		}


def _value(row, fieldname):
	return row.get(fieldname) if isinstance(row, dict) else getattr(row, fieldname, None)


def _presentation(workflow) -> WorkflowPresentation:
	return WorkflowPresentation(
		name=_value(workflow, "name"),
		document_type=_value(workflow, "document_type"),
		workflow_state_field=_value(workflow, "workflow_state_field"),
		override_status=_value(workflow, "override_status"),
		allow_self_approval=_value(workflow, "allow_self_approval"),
		states=[
			WorkflowStatePresentation(
				state=_value(row, "state"),
				allow_edit=_value(row, "allow_edit"),
				doc_status=_value(row, "doc_status"),
				update_field=_value(row, "update_field"),
				update_value=_value(row, "update_value"),
				avoid_status_override=_value(row, "avoid_status_override"),
			)
			for row in (_value(workflow, "states") or [])
		],
		transitions=[
			WorkflowTransitionPresentation(
				state=_value(row, "state"),
				action=_value(row, "action"),
				next_state=_value(row, "next_state"),
				allowed=_value(row, "allowed"),
				allow_self_approval=_value(row, "allow_self_approval"),
				custom_transition_uuid=_value(row, "custom_transition_uuid"),
				custom_comment_is_required=_value(row, "custom_comment_is_required"),
			)
			for row in (_value(workflow, "transitions") or [])
		],
	)


def workflow_catalog(doctype: str) -> list[BaseDocument]:
	"""Supply Desk only presentation data, including styles of historical states."""
	workflows = service.workflow_records(doctype)
	definitions = [(workflow, _presentation(workflow)) for workflow in workflows]
	states = {row["state"] for _, definition in definitions for row in definition["states"] if row["state"]}
	styles = {
		row.name: row.style
		for row in frappe.get_all("Workflow State", filters={"name": ("in", sorted(states))},
			fields=["name", "style"])
	} if states else {}

	documents: list[BaseDocument] = []
	seen = set()
	for workflow, definition in definitions:
		fields = {**definition, "doctype": "Workflow", "is_active": _value(workflow, "is_active")}
		for table, child_doctype in (
			("states", "Workflow Document State"),
			("transitions", "Workflow Transition"),
		):
			fields[table] = [
				_FormMetadataDocument({
					**projected, "doctype": child_doctype, "name": _value(row, "name"),
					"parent": definition["name"], "parenttype": "Workflow", "parentfield": table,
					"idx": index,
				})
				for index, (row, projected) in enumerate(
					zip(_value(workflow, table) or [], definition[table], strict=True), 1
				)
			]
		documents.append(_FormMetadataDocument(fields))
		for row in definition["states"]:
			state = row["state"]
			if state and state not in seen:
				seen.add(state)
				documents.append(_FormMetadataDocument({
					"doctype": "Workflow State", "name": state, "style": styles.get(state),
				}))
	return documents


def describe_document(doc) -> WorkflowContextResponse:
	context = service.get_context(doc)
	workflow = frappe.get_cached_doc("Workflow", context["workflow"]) if context["workflow"] else None
	return {
		"context": context,
		"definition": _presentation(workflow) if workflow else None,
		"error": service.get_routing_error(doc),
		"managed": service.supports_doctype(_value(doc, "doctype")),
	}


def _source(doctype: str, name: str) -> Document:
	if not isinstance(doctype, str) or not doctype or not isinstance(name, str) or not name:
		raise frappe.ValidationError(_("Expected a source type and a list of document names"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc


def _readable_sources(doctype: str, names: list[str]) -> dict[str, Document]:
	result = {}
	for name, doc in load_documents(doctype, names).items():
		try:
			doc.check_permission("read")
		except (frappe.DoesNotExistError, frappe.PermissionError):
			continue
		result[name] = doc
	return result


@frappe.whitelist()
def get_workflow_context(doctype: str, name: str) -> WorkflowContextResponse:
	"""Describe the selected process and safe presentation metadata for a readable source."""
	return describe_document(_source(doctype, name))


@frappe.whitelist()
def get_workflow_document(doctype: str, name: str) -> WorkflowDocumentResponse:
	"""Return a readable source snapshot with context for conflict-merge form resynchronization."""
	doc = _source(doctype, name)
	onload(doc)
	doc.apply_fieldlevel_read_permissions()
	return cast(WorkflowDocumentResponse, doc.as_dict())


def _context_batch_input(doctype: str, names: str | list[str]) -> WorkflowContextsFormInput:
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
	return {"doctype": doctype, "names": unique}


@frappe.whitelist()
def get_workflow_contexts(doctype: str, names: str | list[str]) -> dict[str, WorkflowContextResponse]:
	"""Describe only readable sources from an exact, bounded list selection."""
	form_input = _context_batch_input(doctype, names)
	sources = _readable_sources(form_input["doctype"], form_input["names"])
	if not sources:
		return {}
	managed, routes = service.read_contexts(form_input["doctype"], sources)
	definitions: dict[str, WorkflowPresentation] = {}
	result: dict[str, WorkflowContextResponse] = {}
	for name, route in routes.items():
		workflow = route["workflow"]
		if workflow and workflow.name not in definitions:
			definitions[workflow.name] = _presentation(workflow)
		result[name] = {
			"context": route["context"],
			"definition": definitions.get(workflow.name) if workflow else None,
			"error": route["error"],
			"managed": managed,
		}
	return result


def onload(doc, method=None) -> None:
	"""Preload context before Desk performs its first synchronous readonly calculation."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled() or not service.supports_doctype(_value(doc, "doctype")):
		return
	envelope = describe_document(doc)
	doc.set_onload("dinext_workflow_context", envelope["context"])
	doc.set_onload("dinext_workflow_definition", envelope["definition"])
	doc.set_onload("dinext_workflow_error", envelope["error"])
