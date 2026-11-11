"""Document-specific Workflow routing and durable, independently repeatable processes.

Selection is deliberately separate from execution. Only an accepted decision pins
an instance; terminal transitions release it. All mutations use the source lock.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypedDict

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

CONTEXT = "Workflow Document Context"
PROCESS = "Workflow Process"
ACTIVE = ("Prepared", "Running")
SERVICE_DOCTYPES = {
	CONTEXT,
	PROCESS,
	"Workflow",
	"Workflow State",
	"Workflow Action Master",
	"Workflow Task",
	"Workflow Action",
	"ToDo",
	"Email Queue",
	"Submission Queue",
	"DocType",
	"Custom Field",
	"Property Setter",
	"Version",
	"Comment",
	"Notification Log",
}


class WorkflowScenarioError(frappe.ValidationError):
	"""A routing definition cannot safely be evaluated or initialized."""

	def __init__(self, message: str, *, workflow: str | None = None):
		super().__init__(message)
		self.workflow = workflow


class WorkflowContext(TypedDict):
	workflow: str | None
	state_field: str | None
	state: str | None
	process_id: str | None
	process_status: str | None
	definition_revision: str | None


def is_ready() -> bool:
	"""Gate every installed adapter by this site, never a process-wide flag."""
	try:
		if not getattr(frappe.local, "site", None) or not getattr(frappe.local, "db", None):
			return False
		if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_install", False):
			return False
		if "dinext_common" not in frappe.get_installed_apps():
			return False
		# Cache schema readiness only for this request/job. Never cache a chosen Workflow.
		cached = getattr(frappe.local, "workflow_scenarios_ready", None)
		identity = (frappe.local.site, id(frappe.local.db))
		ready = cached[1] if cached and cached[0] == identity else None
		if ready is None:
			ready = bool(
				frappe.db.table_exists(CONTEXT)
				and frappe.db.table_exists(PROCESS)
				and frappe.db.has_column("Workflow", "custom_selection_order")
				and frappe.db.has_column("Workflow Task", "workflow_process")
			)
			frappe.local.workflow_scenarios_ready = (identity, ready)
		return ready
	except (AttributeError, RuntimeError, ImportError):
		return False


def supports_doctype(doctype: str) -> bool:
	if not doctype or doctype in SERVICE_DOCTYPES or not is_ready():
		return False
	return bool(frappe.db.exists("Workflow", {"document_type": doctype}))


def source_key(doc: Any) -> str:
	created = doc.get("creation")
	identity = [doc.get("doctype"), doc.get("name"), str(get_datetime(created)) if created else ""]
	return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _definitions(doctype: str) -> list[Any]:
	return [
		frappe.get_doc("Workflow", name)
		for name in frappe.get_all(
			"Workflow",
			filters={"document_type": doctype, "is_active": 1},
			pluck="name",
			order_by="custom_selection_order asc, name asc",
		)
	]


def select_workflow(doc: Any) -> Any | None:
	"""Stop on a broken higher-priority expression, rather than silently falling through."""
	from frappe.model.workflow import get_workflow_safe_globals

	for workflow in sorted(
		_definitions(doc.get("doctype")),
		key=lambda row: (int(row.get("custom_selection_order") or 0), row.name),
	):
		condition = str(workflow.get("custom_activation_condition") or "").strip()
		try:
			matches = not condition or bool(
				frappe.safe_eval(
					condition,
					get_workflow_safe_globals(),
					{"doc": frappe._dict(doc.as_dict() if callable(getattr(doc, "as_dict", None)) else doc)},
				)
			)
		except Exception as exc:
			raise WorkflowScenarioError(
				_("Cannot evaluate the activation condition for Workflow {0}: {1}").format(
					workflow.name, str(exc)
				),
				workflow=workflow.name,
			) from exc
		if matches:
			return workflow
	return None


def initial_state(workflow: Any, doc: Any) -> Any:
	states = workflow.get("states") or []
	if not states:
		raise WorkflowScenarioError(
			_("Workflow {0} has no initial state").format(workflow.name), workflow=workflow.name
		)
	state = states[0]
	if int(state.get("doc_status") or 0) != int(doc.get("docstatus") or 0):
		raise WorkflowScenarioError(
			_("Workflow {0} cannot start in state {1} with document status {2}").format(
				workflow.name, state.state, doc.get("docstatus") or 0
			),
			workflow=workflow.name,
		)
	return state


def is_terminal(workflow: Any, state: str) -> bool:
	return not any(row.get("state") == state for row in workflow.get("transitions") or [])


def _context_row(doc: Any) -> Any | None:
	if not doc.get("name") or not doc.get("creation"):
		return None
	name = source_key(doc)
	if not frappe.db.exists(CONTEXT, name):
		return None
	return frappe.get_doc(CONTEXT, name)


def active_process(doc: Any) -> Any | None:
	context = _context_row(doc)
	if not context or not context.active_process:
		return None
	process = frappe.get_doc(PROCESS, context.active_process)
	if process.status not in ACTIVE or process.source_key != source_key(doc):
		return None
	return process


def _legacy_active_tasks(doc: Any) -> list[Any]:
	if not doc.get("name") or not doc.get("creation"):
		return []
	return frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"source_created_at": doc.creation,
			"workflow_process": ("is", "not set"),
			"round_status": ("in", ("Open", "Stalled", "Finalizing", "Conflicted")),
		},
		fields=["*"],
		order_by="creation asc,name asc",
	)


def _selected(doc: Any) -> tuple[Any | None, Any | None]:
	process = active_process(doc)
	context = _context_row(doc)
	if process and process.status == "Running":
		return frappe.get_doc("Workflow", process.workflow), process
	if context and context.routing_error:
		return None, None
	if process:
		return frappe.get_doc("Workflow", process.workflow), process
	legacy = _legacy_active_tasks(doc)
	names = {row.workflow for row in legacy}
	if len(names) == 1 and frappe.db.exists("Workflow", next(iter(names))):
		workflow = frappe.get_doc("Workflow", next(iter(names)))
		if workflow.workflow_state_field:
			return workflow, None
	return select_workflow(doc), None


def get_context(doc: Any) -> WorkflowContext:
	result: WorkflowContext = {
		"workflow": None,
		"state_field": None,
		"state": None,
		"process_id": None,
		"process_status": None,
		"definition_revision": None,
	}
	if not is_ready() or doc.get("doctype") in SERVICE_DOCTYPES:
		return result
	workflow, process = _selected(doc)
	if workflow:
		field = workflow.workflow_state_field
		result.update(
			workflow=workflow.name,
			state_field=field,
			state=str(doc.get(field) or ""),
			process_id=process.name if process else None,
			process_status=process.status if process else None,
			definition_revision=str(workflow.modified),
		)
	return result


def workflow_context(doc: Any) -> tuple[str, Any, str, str] | None:
	if not is_ready() or doc.get("doctype") in SERVICE_DOCTYPES:
		return None
	workflow, _process = _selected(doc)
	if not workflow:
		return None
	field = workflow.workflow_state_field
	return workflow.name, workflow, field, str(doc.get(field) or "")


def _insert(doctype: str, values: dict[str, Any]) -> Any:
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.flags.in_workflow_scenario_service = True
	return doc.insert(ignore_permissions=True, ignore_links=True)


def _lock_source(doc: Any) -> None:
	if doc.get("name") and not doc.is_new():
		from dinext_common.workflow_approval.engine import _lock_domain_dependencies

		_lock_domain_dependencies(doc.doctype, doc.name)
		persisted = frappe.get_doc(doc.doctype, doc.name, for_update=True)
		if get_datetime(persisted.creation) != get_datetime(doc.creation):
			raise WorkflowScenarioError(
				_("The document creation timestamp cannot be changed during Workflow processing")
			)


def _ensure_row(doc: Any) -> Any:
	key = source_key(doc)
	if not frappe.db.exists(CONTEXT, key):
		return _insert(
			CONTEXT,
			{
				"name": key,
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"source_created_at": doc.creation,
			},
		)
	return frappe.get_doc(CONTEXT, key, for_update=True)


def _retire_process(process: Any, reason: str, status: str = "Cancelled") -> None:
	from dinext_common.workflow_approval.engine import ACTIVE_ROUND_STATUSES, _cancel_round

	for round_id in frappe.get_all(
		"Workflow Task",
		filters={"workflow_process": process.name, "round_status": ("in", ACTIVE_ROUND_STATUSES)},
		pluck="approval_round_id",
		distinct=True,
	):
		_cancel_round(round_id, reason)
	frappe.db.set_value(
		PROCESS,
		process.name,
		{"status": status, "active_source_key": None, "completed_at": now_datetime()},
		update_modified=False,
	)


def ensure_context(doc: Any, *, persist_state: bool = False, strict: bool = True) -> WorkflowContext:
	"""Prepare a candidate under the source lock; preserve every Running process.

	Called before source validation with incoming values, and after terminal work
	with persist_state=True. Completion uses strict=False so the previous action is
	not rolled back by an incompatible next definition.
	"""
	if not supports_doctype(doc.get("doctype")) or not doc.get("name") or not doc.get("creation"):
		return get_context(doc)
	_lock_source(doc)
	context = _ensure_row(doc)
	process = active_process(doc)
	if not process:
		legacy = _legacy_active_tasks(doc)
		if legacy:
			adopt_legacy_source(doc, legacy)
			process = active_process(doc)
	if process and (
		process.status == "Running" or getattr(frappe.flags, "in_dinext_workflow_finalization", False)
	):
		return get_context(doc)
	try:
		workflow = select_workflow(doc)
		state = (
			initial_state(workflow, doc)
			if workflow and (not process or process.workflow != workflow.name)
			else None
		)
	except WorkflowScenarioError as exc:
		frappe.db.set_value(
			CONTEXT,
			context.name,
			{"routing_error": str(exc), "error_workflow": exc.workflow},
			update_modified=False,
		)
		if strict:
			raise
		return get_context(doc)
	if process and workflow and process.workflow == workflow.name:
		frappe.db.set_value(
			CONTEXT, context.name, {"routing_error": None, "error_workflow": None}, update_modified=False
		)
		return get_context(doc)
	if process:
		_retire_process(process, _("Another Workflow scenario was selected before the first action"))
	frappe.db.set_value(
		CONTEXT,
		context.name,
		{"active_process": None, "routing_error": None, "error_workflow": None},
		update_modified=False,
	)
	if not workflow:
		return get_context(doc)
	process = _insert(
		PROCESS,
		{
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"source_created_at": doc.creation,
			"source_key": context.name,
			"active_source_key": context.name,
			"workflow": workflow.name,
			"status": "Prepared",
			"initial_state": state.state,
			"current_state": state.state,
			"definition_revision": str(workflow.modified),
			"cascade_id": _cascade(doc)[0],
			"automatic_transition_count": _cascade(doc)[1],
		},
	)
	frappe.db.set_value(
		CONTEXT,
		context.name,
		{"active_process": process.name, "last_process": process.name},
		update_modified=False,
	)
	updates = {workflow.workflow_state_field: state.state}
	if state.get("update_field"):
		updates[state.update_field] = state.update_value
	doc.update(updates)
	doc.flags.workflow_scenario_prepared = True
	doc.flags.workflow_scenario_prepared_workflow = workflow.name
	if persist_state and not doc.is_new():
		frappe.db.set_value(doc.doctype, doc.name, updates, update_modified=False)
	return get_context(doc)


def prepare_source(doc: Any, method: str | None = None) -> None:
	if supports_doctype(doc.get("doctype")) and not getattr(
		frappe.flags, "in_dinext_workflow_finalization", False
	):
		ensure_context(doc)


def validate_task(doc: Any, task: Any) -> None:
	"""Called after a request replay check and while holding the source row lock."""
	from dinext_common.workflow_approval.engine import WorkflowApprovalConflictError

	if task.get("source_created_at") and get_datetime(task.source_created_at) != get_datetime(doc.creation):
		raise WorkflowApprovalConflictError(_("The Workflow Task belongs to another document instance"))
	if not is_ready():
		return
	from functools import partial

	try:
		context = ensure_context(doc, persist_state=True)
		if not task.get("workflow_process"):
			task.reload()
	except WorkflowScenarioError:
		frappe.db.after_rollback.add(
			partial(
				_persist_reselection, doc.doctype, doc.name, str(doc.creation), task.get("workflow_process")
			)
		)
		raise
	if (
		not task.get("workflow_process")
		or task.workflow_process != context["process_id"]
		or task.workflow != context["workflow"]
	):
		frappe.db.after_rollback.add(
			partial(
				_persist_reselection, doc.doctype, doc.name, str(doc.creation), task.get("workflow_process")
			)
		)
		raise WorkflowApprovalConflictError(
			_("The Workflow process has changed. Refresh the document before acting.")
		)


def pin_process(doc: Any, process_id: str | None = None) -> None:
	if not is_ready():
		return
	process = active_process(doc)
	if not process or (process_id and process.name != process_id):
		raise WorkflowScenarioError(_("The Workflow process is no longer active"))
	if process.status == "Prepared":
		frappe.db.set_value(
			PROCESS,
			process.name,
			{"status": "Running", "started_at": now_datetime(), "started_by": frappe.session.user},
			update_modified=False,
		)


def finish_transition(doc: Any, workflow_name: str | None = None, process_id: str | None = None) -> bool:
	"""Release only after a successful terminal entry. Preparing repeats is separate."""
	if not is_ready():
		return False
	process = active_process(doc)
	if not process or (process_id and process.name != process_id):
		return False
	workflow = frappe.get_doc("Workflow", process.workflow)
	state = str(doc.get(workflow.workflow_state_field) or "")
	frappe.db.set_value(PROCESS, process.name, {"current_state": state}, update_modified=False)
	if workflow_name and workflow_name != process.workflow:
		raise WorkflowScenarioError(_("Workflow process identity changed during completion"))
	if not is_terminal(workflow, state):
		return False
	frappe.db.set_value(
		PROCESS,
		process.name,
		{"status": "Completed", "active_source_key": None, "completed_at": now_datetime()},
		update_modified=False,
	)
	frappe.db.set_value(
		CONTEXT,
		process.source_key,
		{"active_process": None, "last_process": process.name},
		update_modified=False,
	)
	return True


def archive_source(doc: Any) -> None:
	if not is_ready():
		return
	process = active_process(doc)
	if process:
		_retire_process(process, _("Source document deleted"), "Archived")
		frappe.db.set_value(CONTEXT, process.source_key, "active_process", None, update_modified=False)


def _cascade(doc: Any) -> tuple[str | None, int]:
	entry = getattr(frappe.local, "workflow_scenario_cascade", None)
	if entry and entry.get("source_key") == source_key(doc) and entry.get("site") == frappe.local.site:
		return entry["id"], entry["count"]
	process = active_process(doc)
	if not process:
		context = _context_row(doc)
		process = frappe.get_doc(PROCESS, context.last_process) if context and context.last_process else None
	return (process.cascade_id, int(process.automatic_transition_count or 0)) if process else (None, 0)


def start_cascade(doc: Any, *, manual: bool = False) -> dict[str, Any]:
	cascade_id, count = _cascade(doc)
	if manual or not cascade_id:
		cascade_id, count = frappe.generate_hash(length=32), 0
	entry = {"site": frappe.local.site, "source_key": source_key(doc), "id": cascade_id, "count": count}
	frappe.local.workflow_scenario_cascade = entry
	process = active_process(doc)
	if process:
		values = {"cascade_id": cascade_id, "automatic_transition_count": count}
		if manual:
			values["automatic_visited_states"] = "[]"
		frappe.db.set_value(PROCESS, process.name, values, update_modified=False)
	return entry


def automation_budget_available(doc: Any, limit: int = 20, *, state_key: str | None = None) -> bool:
	if _cascade(doc)[1] >= limit:
		return False
	process = active_process(doc)
	return (
		not state_key
		or not process
		or state_key not in json.loads(process.get("automatic_visited_states") or "[]")
	)


def consume_automatic_transition(doc: Any, *, state_key: str | None = None) -> None:
	entry = start_cascade(doc)
	entry["count"] += 1
	process = active_process(doc)
	if process:
		visited = json.loads(process.get("automatic_visited_states") or "[]")
		if state_key:
			visited.append(state_key)
		frappe.db.set_value(
			PROCESS,
			process.name,
			{
				"cascade_id": entry["id"],
				"automatic_transition_count": entry["count"],
				"automatic_visited_states": json.dumps(visited),
			},
			update_modified=False,
		)


def adopt_legacy_source(source: Any, tasks: list[dict[str, Any]]) -> str | None:
	"""Migration only: link historical rounds without replaying any operation."""
	from collections import defaultdict

	if not tasks:
		return None
	_lock_source(source)
	context = _ensure_row(source)
	groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
	definitions = {
		name: frappe.get_doc("Workflow", name) if frappe.db.exists("Workflow", name) else None
		for name in {row.get("workflow") for row in tasks}
	}
	valid_names = {
		name for name, workflow in definitions.items() if workflow and workflow.get("workflow_state_field")
	}
	active_workflows = {
		row.get("workflow")
		for row in tasks
		if row.get("workflow") in valid_names
		and row.get("round_status") in ("Open", "Stalled", "Finalizing", "Conflicted")
	}
	if len(active_workflows) > 1:
		raise WorkflowScenarioError(
			_("Several legacy Workflow processes exist for {0} {1}").format(source.doctype, source.name)
		)
	for task in tasks:
		active = task.get("round_status") in ("Open", "Stalled", "Finalizing", "Conflicted")
		key = (task["workflow"], "active" if active else task.get("approval_round_id") or task["name"])
		groups[key].append(task)
	last_process = context.last_process
	for (workflow_name, group_key), rows in groups.items():
		if group_key == "active" and workflow_name in valid_names and context.active_process:
			process_id = context.active_process
		else:
			workflow = definitions[workflow_name]
			status = (
				"Archived"
				if workflow_name not in valid_names
				else "Running"
				if group_key == "active"
				else (
					"Completed"
					if any(row.get("round_status") == "Transitioned" for row in rows)
					else "Cancelled"
				)
			)
			process = _insert(
				PROCESS,
				{
					"reference_doctype": source.doctype,
					"reference_name": source.name,
					"source_created_at": source.creation,
					"source_key": context.name,
					"active_source_key": context.name if status == "Running" else None,
					"workflow": workflow_name,
					"legacy_task_names": json.dumps([row["name"] for row in rows]),
					"status": status,
					"initial_state": rows[0].get("workflow_state"),
					"current_state": source.get(workflow.workflow_state_field)
					if status == "Running"
					else rows[-1].get("next_state") or rows[-1].get("workflow_state"),
					"definition_revision": str(workflow.modified) if workflow else None,
					"started_at": min(
						(row.get("creation") for row in rows if row.get("creation")), default=source.creation
					),
					"completed_at": None
					if status == "Running"
					else max(
						(
							row.get("completed_at") or row.get("modified") or row.get("creation")
							for row in rows
						),
						default=source.creation,
					),
					"started_by": source.owner,
				},
			)
			process_id = process.name
			if status == "Running":
				context.active_process = process_id
		last_process = process_id
		for task in rows:
			frappe.db.set_value(
				"Workflow Task", task["name"], "workflow_process", process_id, update_modified=False
			)
	frappe.db.set_value(
		CONTEXT,
		context.name,
		{"active_process": context.active_process, "last_process": context.active_process or last_process},
		update_modified=False,
	)
	return context.active_process or last_process


def task_is_current(source: Any, task: Any) -> bool:
	if task.get("source_created_at") and get_datetime(task.source_created_at) != get_datetime(
		source.creation
	):
		return False
	if not is_ready():
		return True
	context = get_context(source)
	return bool(
		context["process_id"]
		and context["process_id"] == task.get("workflow_process")
		and context["workflow"] == task.workflow
		and context["state"] == task.workflow_state
	)


def current_task_rows(rows: list[Any]) -> list[Any]:
	if not is_ready():
		return rows
	active = [
		row for row in rows if row.get("round_status") in ("Open", "Stalled", "Finalizing", "Conflicted")
	]
	if not active:
		return rows
	keys = {
		row.name: source_key(
			frappe._dict(
				doctype=row.reference_doctype, name=row.reference_name, creation=row.source_created_at
			)
		)
		for row in active
		if row.get("source_created_at")
	}
	contexts = (
		{
			row.name: row.active_process
			for row in frappe.get_all(
				CONTEXT, filters={"name": ("in", list(set(keys.values())))}, fields=["name", "active_process"]
			)
		}
		if keys
		else {}
	)
	return [
		row
		for row in rows
		if row not in active
		or (row.get("workflow_process") and contexts.get(keys.get(row.name)) == row.workflow_process)
	]


def get_routing_error(doc: Any) -> str | None:
	if not is_ready() or doc.get("doctype") in SERVICE_DOCTYPES:
		return None
	context = _context_row(doc)
	return context.routing_error if context else None


def before_source_rename(doc: Any, method: str | None, old: str, new: str, merge: bool = False) -> None:
	if not is_ready() or doc.doctype in SERVICE_DOCTYPES:
		return
	_lock_source(doc)
	if merge:
		target = frappe.get_doc(doc.doctype, new)
		if active_process(doc) or active_process(target):
			raise WorkflowScenarioError(_("Finish the active Workflow processes before merging documents"))


def after_source_rename(doc: Any, method: str | None, old: str, new: str, merge: bool = False) -> None:
	"""Native Dynamic Links follow a rename; rekey the source-instance hashes too."""
	if not is_ready() or doc.doctype in SERVICE_DOCTYPES or merge:
		return
	old_key = source_key(frappe._dict(doctype=doc.doctype, name=old, creation=doc.creation))
	if not frappe.db.exists(CONTEXT, old_key):
		return
	new_key = source_key(doc)
	frappe.db.set_value(CONTEXT, old_key, "name", new_key, update_modified=False)
	for process in frappe.get_all(
		PROCESS, filters={"source_key": old_key}, fields=["name", "active_source_key"]
	):
		values = {"source_key": new_key}
		if process.active_source_key:
			values["active_source_key"] = new_key
		frappe.db.set_value(PROCESS, process.name, values, update_modified=False)
	cascade = getattr(frappe.local, "workflow_scenario_cascade", None)
	if cascade and cascade.get("site") == frappe.local.site and cascade.get("source_key") == old_key:
		cascade["source_key"] = new_key


def _persist_reselection(doctype: str, name: str, created: str, rejected_process: str | None) -> None:
	"""Keep the new candidate after rejecting a stale vote, without its business edits."""
	previous_db = frappe.local.db
	previous_ready = getattr(frappe.local, "workflow_scenarios_ready", None)
	try:
		frappe.connect(set_admin_as_user=False)
		try:
			source = frappe.get_doc(doctype, name, for_update=True)
		except frappe.DoesNotExistError:
			return
		if get_datetime(source.creation) != get_datetime(created):
			return
		process = active_process(source)
		if not process or process.status != "Prepared" or process.name != rejected_process:
			return
		ensure_context(source, persist_state=True, strict=False)
		from dinext_common.workflow_approval.engine import reconcile_source

		reconcile_source(source, apply_automatic=False)
		frappe.db.commit()
	finally:
		if frappe.local.db is not previous_db:
			frappe.db.close()
		frappe.local.db = previous_db
		frappe.local.workflow_scenarios_ready = previous_ready
