"""Whitelisted task-based API and compatibility adapters."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, TypedDict

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.pending import (
	PendingApproverTask,
	get_required_state_pending_tasks,
	required_target_task_names,
)
from dinext_common.workflow_approval.permissions import (
	get_monitorable_workflows,
	get_task_read_checker,
	has_workflow_task_permission,
)

QUEUE_FIELDS = [
	"name",
	"creation",
	"reference_doctype",
	"reference_name",
	"source_title",
	"source_created_at",
	"source_owner",
	"workflow",
	"workflow_state",
	"approval_round_id",
	"status",
	"round_status",
	"approver",
	"user",
	"completed_at",
	"cancelled_at",
	"cancellation_reason",
	"source_deleted_at",
	"action",
	"next_state",
	"completion_source",
	"reused_from_workflow_task",
	"policy",
	"threshold",
	"round_manifest",
	"vote_comment",
]


TASK_ACCESS_FIELDS = (
	"workflow",
	"approver",
	"user",
	"reference_doctype",
	"reference_name",
	"doc",
	"wt_docname",
	"source_deleted_at",
)
MONITORING_STATUSES = ("Open", "Stalled", "Conflicted")
MONITORED_TASK_FIELDS = (
	"approval_round_id",
	"creation",
	"source_title",
	"status",
	"completed_at",
	"completion_source",
)
PERSONAL_TASK_ORDER = "modified desc, name asc"


def _require_post() -> None:
	request = getattr(frappe.local, "request", None)
	if request is not None and request.method != "POST":
		raise frappe.PermissionError(_("This workflow operation requires POST"))


def _require_system_manager() -> None:
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		raise frappe.PermissionError(_("System Manager role is required"))


def _as_list(value: str | list[Any]) -> list[Any]:
	if isinstance(value, str):
		parsed = json.loads(value)
		if not isinstance(parsed, list):
			raise frappe.ValidationError(_("Expected a JSON list"))
		return parsed
	return list(value)


def _source_identity(doc: object) -> tuple[str, str]:
	if isinstance(doc, str):
		doc = frappe.parse_json(doc)
	if isinstance(doc, dict):
		return str(doc.get("doctype") or ""), str(doc.get("name") or "")
	return str(getattr(doc, "doctype", "") or ""), str(getattr(doc, "name", "") or "")


def _find_task_for_action(
	doctype: str,
	name: str,
	action: str,
	user: str,
	transition_uuid: str | None = None,
) -> str:
	task_names = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"approver": user,
			"status": "Working",
			"round_status": "Open",
		},
		pluck="name",
		order_by="creation desc, name asc",
		limit=2,
	)
	child_filters: dict[str, Any] = {"parent": None}
	if transition_uuid:
		child_filters = {"transition_uuid": transition_uuid}
	elif action:
		child_filters = {"action": action}
	matches = [
		task_name
		for task_name in task_names
		if frappe.db.exists(
			"Available Workflow Transitions",
			{"parent": task_name, **child_filters},
		)
	]
	if len(matches) != 1:
		raise engine.WorkflowApprovalConflictError(
			_("No unique active Workflow Task is available for this action")
		)
	return matches[0]


def _vote_source_action(
	doctype: str,
	name: str,
	action: str,
	*,
	transition_uuid: str | None = None,
	comment: object = None,
	request_id: str | None = None,
	completion_source: str = "Manual",
) -> engine.VoteResult:
	task_name = _find_task_for_action(
		doctype,
		name,
		action,
		frappe.session.user,
		transition_uuid=transition_uuid,
	)
	return engine.cast_vote(
		task_name,
		transition_uuid=transition_uuid,
		action=action,
		comment=comment,
		request_id=request_id,
		completion_source=completion_source,
	)


@frappe.whitelist(methods=["POST"])
def vote(
	task_name: str,
	transition_uuid: str | None = None,
	action: str | None = None,
	comment: object = None,
	request_id: str | None = None,
) -> engine.VoteResult:
	_require_post()
	return engine.cast_vote(
		task_name,
		transition_uuid=transition_uuid,
		action=action,
		comment=comment,
		request_id=request_id,
		completion_source="Manual",
	)


@frappe.whitelist(methods=["POST"])
def apply_workflow(
	doc: object,
	action: str,
	comment: object = None,
	request_id: str | None = None,
	transition_uuid: str | None = None,
) -> engine.VoteResult:
	"""Replace direct Frappe apply_workflow with one task vote."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.model.workflow import apply_workflow as core_apply_workflow

		return core_apply_workflow(doc, action)
	_require_post()
	doctype, name = _source_identity(doc)
	if not doctype or not name:
		raise frappe.ValidationError(_("A persisted source document is required"))
	return _vote_source_action(
		doctype,
		name,
		action,
		transition_uuid=transition_uuid,
		comment=comment,
		request_id=request_id,
	)


@frappe.whitelist(methods=["POST"])
def bulk_vote(
	doctype: str,
	names: str | list[str],
	action: str,
	comment: object = None,
	request_id: str | None = None,
	transition_uuid: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
	"""Process each source under a savepoint and return itemized outcomes."""
	_require_post()
	docnames = list(dict.fromkeys(str(name) for name in _as_list(names)))
	if len(docnames) > 500:
		raise frappe.ValidationError(_("Bulk approval supports at most 500 documents"))
	result: dict[str, list[dict[str, Any]]] = {"succeeded": [], "failed": []}
	for index, name in enumerate(docnames):
		from frappe.model.workflow import show_progress

		show_progress(docnames, _("Applying: {0}").format(action), index + 1, name)
		try:
			vote_result = _vote_source_action(
				doctype,
				name,
				action,
				transition_uuid=transition_uuid,
				comment=comment,
				request_id=f"{request_id}:{name}" if request_id else None,
				completion_source="Bulk",
			)
			result["succeeded"].append({"name": name, "result": vote_result})
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			redacted = isinstance(
				exc,
				(frappe.DoesNotExistError, frappe.PermissionError),
			)
			result["failed"].append(
				{
					"name": name,
					"error": (
						_("The workflow item could not be processed")
						if redacted
						else str(exc)
					),
					"error_type": (
						"Unavailable"
						if redacted
						else exc.__class__.__name__
					),
				}
			)
	return result


@frappe.whitelist(methods=["POST"])
def bulk_task_vote(
	items: str | list[dict[str, Any]],
	comment: object = None,
	request_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
	"""Vote checked report rows independently with permission-safe outcomes."""
	_require_post()
	parsed = _as_list(items)
	if len(json.dumps(parsed, ensure_ascii=False)) > 1_000_000:
		raise frappe.ValidationError(_("Bulk approval payload is too large"))
	deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
	for item in parsed:
		if not isinstance(item, dict):
			raise frappe.ValidationError(_("Each bulk item must be an object"))
		key = (str(item.get("task_name") or ""), str(item.get("transition_uuid") or ""))
		if not all(key):
			raise frappe.ValidationError(_("Task and transition are required"))
		deduplicated.setdefault(key, item)
	if len(deduplicated) > 500:
		raise frappe.ValidationError(_("Bulk approval supports at most 500 tasks"))

	result: dict[str, list[dict[str, Any]]] = {"succeeded": [], "failed": []}
	for index, ((task_name, transition_uuid), item) in enumerate(deduplicated.items()):
		try:
			vote_result = engine.cast_vote(
				task_name,
				transition_uuid=transition_uuid,
				action=item.get("action"),
				comment=item.get("comment", comment),
				request_id=(
					f"{request_id}:{index}" if request_id else None
				),
				completion_source="Bulk",
			)
			result["succeeded"].append({"task_name": task_name, "result": vote_result})
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			redacted = isinstance(
				exc,
				(frappe.DoesNotExistError, frappe.PermissionError),
			)
			result["failed"].append(
				{
					"task_name": task_name,
					"error": (
						_("The workflow item could not be processed")
						if redacted
						else str(exc)
					),
					"error_type": (
						"Unavailable"
						if redacted
						else exc.__class__.__name__
					),
				}
			)
	return result


@frappe.whitelist(methods=["POST"])
def bulk_workflow_approval(
	docnames: str | list[str],
	doctype: str,
	action: str,
	comment: object = None,
	request_id: str | None = None,
	transition_uuid: str | None = None,
) -> None:
	"""Compatibility override for the standard Frappe bulk method."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.model.workflow import bulk_workflow_approval as core_bulk_workflow_approval

		return core_bulk_workflow_approval(docnames, doctype, action)
	names = [str(name) for name in _as_list(docnames)]
	if len(names) < 20:
		bulk_vote(
			doctype,
			names,
			action,
			comment,
			request_id,
			transition_uuid=transition_uuid,
		)
		return None
	if len(names) <= 500:
		frappe.msgprint(
			_("Bulk {0} is enqueued in background.").format(action),
			alert=True,
		)
		frappe.enqueue(
			bulk_vote,
			doctype=doctype,
			names=names,
			action=action,
			comment=comment,
			request_id=request_id,
			transition_uuid=transition_uuid,
			queue="short",
			timeout=1000,
		)
		return None
	frappe.throw(
		_("Bulk approval only supports up to 500 documents."),
		title=_("Too Many Documents"),
	)


def _select_task_rows(filters, *, fields, order_by, limit, predicate=None, monitored_only=False):
	fields = list(dict.fromkeys((*fields, *TASK_ACCESS_FIELDS)))
	user = frappe.session.user
	if monitored_only and user != "Administrator" and "System Manager" not in frappe.get_roles(user):
		workflows = get_monitorable_workflows(user)
		if filters.get("workflow"):
			workflows = [workflow for workflow in workflows if workflow == filters["workflow"]]
		if not workflows:
			return []
		filters = {**filters, "workflow": ("in", workflows)}
	can_read = get_task_read_checker(user, monitored_only=monitored_only, require_source=True)
	page_size = 500
	start = 0
	result = []
	while True:
		rows = frappe.get_all(
			"Workflow Task",
			filters=filters,
			fields=fields,
			order_by=order_by,
			limit_start=start,
			limit_page_length=page_size,
		)
		selected = [row for row in rows if predicate(row)] if predicate else rows
		result.extend(row for row in selected if can_read(row))
		if limit and len(result) >= limit:
			return result[:limit]
		if len(rows) < page_size:
			return result
		start += page_size


def _filtered_tasks(filters, *, limit=None, include_transitions=False, predicate=None, fields=QUEUE_FIELDS):
	rows = _select_task_rows(
		filters, fields=fields, order_by=PERSONAL_TASK_ORDER, limit=limit, predicate=predicate
	)
	if not include_transitions:
		return [frappe._dict({field: row.get(field) for field in fields}) for row in rows]
	if not rows:
		return []
	transitions = defaultdict(list)
	for child in frappe.get_all(
		"Available Workflow Transitions",
		filters={
			"parent": ("in", [row["name"] for row in rows]),
			"parenttype": "Workflow Task",
			"parentfield": "available_workflow_transitions",
		},
		fields=["parent", "transition_uuid", "action", "next_state", "allowed_role", "comment_is_required"],
		order_by="idx asc",
		limit_page_length=0,
	):
		transitions[child.parent].append(
			{
				"transition_uuid": child.transition_uuid,
				"action": child.action,
				"next_state": child.next_state,
				"allowed": child.allowed_role,
				"comment_is_required": bool(child.comment_is_required),
			}
		)
	return [
		frappe._dict(
			{field: row.get(field) for field in QUEUE_FIELDS},
			available_transitions=transitions[row["name"]],
		)
		for row in rows
	]


def _queue_day_filter(created_on=None):
	from dinext_common.workflow_approval.notifications import (
		_aware_utc,
		_recipient_timezone,
		get_timezone,
	)

	zone = get_timezone(_recipient_timezone(frappe.session.user))
	day = getdate(created_on) if created_on else _aware_utc(now_datetime()).astimezone(zone).date()
	return day, lambda row: _aware_utc(row.creation).astimezone(zone).date() == day


def get_personal_queue(filters=None, *, limit=None, include_transitions=False, fields=QUEUE_FIELDS):
	values = frappe._dict(filters or {})
	task_filters = {
		"approver": frappe.session.user,
		"status": "Working",
		"round_status": "Open",
		"source_deleted_at": ("is", "not set"),
	}
	for field in ("workflow", "reference_doctype", "workflow_state"):
		if values.get(field):
			task_filters[field] = values[field]
	predicate = None
	if values.get("created_on") or values.get("created_today"):
		_, predicate = _queue_day_filter(values.get("created_on"))
	return _filtered_tasks(
		task_filters, limit=limit, include_transitions=include_transitions, predicate=predicate, fields=fields
	)


@frappe.whitelist()
def get_my_queue(limit: int = 500) -> list[dict[str, Any]]:
	return get_personal_queue(limit=int(limit), include_transitions=True)


def get_personal_history(filters=None, *, limit=None, include_transitions=False, fields=QUEUE_FIELDS):
	values = frappe._dict(filters or {})
	task_filters = {
		"approver": frappe.session.user,
		"status": "Completed" if values.completed_since else ("in", ("Completed", "Cancelled")),
	}
	if values.completed_since:
		task_filters["completed_at"] = (">=", get_datetime(values.completed_since))
	for field in ("workflow", "reference_doctype", "action", "completion_source"):
		if values.get(field):
			task_filters[field] = values[field]
	return _filtered_tasks(task_filters, limit=limit, include_transitions=include_transitions, fields=fields)


@frappe.whitelist()
def get_my_history(limit: int = 500) -> list[dict[str, Any]]:
	return get_personal_history(limit=int(limit), include_transitions=True)


@frappe.whitelist()
def get_source_approval_history(
	doctype: str,
	name: str,
	limit: int = 500,
) -> list[dict[str, Any]]:
	source = frappe.get_doc(doctype, name)
	source.check_permission("read")
	rows = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"status": ("in", ("Completed", "Cancelled")),
		},
		fields=QUEUE_FIELDS + ["cancelled_at", "cancellation_reason"],
		order_by="modified desc, name desc",
		limit=min(int(limit), 1000),
	)
	users = dict(
		frappe.get_all(
			"User",
			filters={"name": ("in", sorted({row.approver for row in rows}))},
			fields=["name", "full_name"],
			as_list=True,
		)
	) if rows else {}
	for row in rows:
		row["approver_name"] = users.get(row.approver) or row.approver
	return rows


@frappe.whitelist()
def get_pending_approvers(doctype: str, name: str) -> list[dict[str, Any]]:
	source = frappe.get_doc(doctype, name)
	source.check_permission("read")
	rows = None
	for adapter_path in frappe.get_hooks("workflow_approval_pending_approvers") or []:
		adapter = frappe.get_attr(adapter_path)
		result = adapter(doctype, name)
		if result is not None:
			rows = result
			break
	if rows is None:
		rows = [
			{key: row[key] for key in ("approver", "approval_round_id", "workflow_state")}
			for row in get_required_state_pending_tasks(doctype, [name])
		]

	names = dict(
		frappe.get_all(
			"User",
			filters={"name": ("in", sorted({row["approver"] for row in rows}))},
			fields=["name", "full_name"],
			as_list=True,
		)
	) if rows else {}
	for row in rows:
		row["approver_name"] = names.get(row["approver"]) or row["approver"]
	return rows


def describe_rebuild_rounds(
	reference_doctype: str,
	reference_names: list[str],
) -> list[dict[str, Any]]:
	"""Describe every stalled or conflicted round for the given documents.

	The caller decides which documents belong together. This function does not
	know about a particular DocType.
	"""
	if not reference_doctype or not reference_names:
		return []
	rows = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": ("in", list(reference_names)),
			"round_status": ("in", ("Open", "Stalled", "Conflicted")),
		},
		fields=[
			"name",
			"approval_round_id",
			"round_status",
			"reference_name",
			"source_title",
			"failure_metadata",
			"creation",
		],
		order_by="creation desc, name desc",
	)
	can_reset = _caller_is_system_manager()
	seen: set[str] = set()
	rounds: list[dict[str, Any]] = []
	for row in rows:
		round_id = row.approval_round_id
		if not round_id or round_id in seen:
			continue
		seen.add(round_id)
		metadata = engine.configuration_metadata(row)
		round_status = row.round_status
		if round_status == "Open":
			metadata = engine.preview_configuration_conflict(frappe.get_doc("Workflow Task", row.name))
			if not metadata:
				continue
			round_status = "Conflicted"
		rounds.append(
			{
				"round_id": round_id,
				"round_status": round_status,
				"reference_name": row.reference_name,
				"source_title": row.source_title or row.reference_name,
				"configuration_change": metadata,
				"can_reset": can_reset,
			}
		)
	return rounds


def _banner_from_rows(
	rows: list[object],
	*,
	rounds: list[dict[str, Any]] | None = None,
	pending: list[PendingApproverTask] | None = None,
) -> dict[str, Any]:
	if not rows and not rounds:
		return {
			"round_id": None,
			"round_status": None,
			"pending_approvers": [],
			"can_reset": _caller_is_system_manager(),
			"configuration_change": None,
			"rounds": rounds or [],
		}
	stalled = rounds or []
	if stalled:
		first = stalled[0]
		return {
			"round_id": first["round_id"],
			"round_status": first["round_status"],
			"pending_approvers": [],
			"can_reset": first["can_reset"],
			"configuration_change": first["configuration_change"],
			"rounds": stalled,
		}
	round_id = rows[0].approval_round_id
	approvers = sorted({row["approver"] for row in pending or []})
	names = (
		dict(
			frappe.get_all(
				"User",
				filters={"name": ("in", approvers)},
				fields=["name", "full_name"],
				as_list=True,
			)
		)
		if approvers
		else {}
	)
	return {
		"round_id": round_id,
		"round_status": "Open",
		"pending_approvers": [
			{"approver": approver, "approver_name": names.get(approver) or approver}
			for approver in approvers
		],
		"can_reset": False,
		"configuration_change": None,
		"rounds": [],
	}


def _active_round_rows(reference_doctype: str, reference_names: list[str]) -> list[object]:
	if not reference_names:
		return []
	return frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": ("in", reference_names),
			"round_status": ("in", ("Open", "Stalled", "Conflicted")),
		},
		fields=[
			"approval_round_id",
			"round_status",
			"approver",
			"status",
			"creation",
			"failure_metadata",
		],
		order_by="creation desc, name desc",
		limit=100,
	)


@frappe.whitelist()
def get_form_approval_banner(doctype: str, name: str) -> dict[str, Any]:
	"""Pending approvers, or a rebuild indicator for a stalled round."""
	source = frappe.get_doc(doctype, name)
	source.check_permission("read")
	reference_doctype = doctype
	reference_names = [name]
	if doctype == "User Timesheet":
		reference_doctype = "User Timesheet Position"
		reference_names = frappe.get_all(
			"User Timesheet Position",
			filters={"user_timesheet": name},
			pluck="name",
		)
	if not reference_names:
		return {
			"round_id": None,
			"round_status": None,
			"pending_approvers": [],
			"can_reset": False,
			"configuration_change": None,
			"rounds": [],
		}
	rows = _active_round_rows(reference_doctype, reference_names)
	rounds = describe_rebuild_rounds(reference_doctype, reference_names)
	pending = [] if rounds else get_required_state_pending_tasks(reference_doctype, reference_names)
	return _banner_from_rows(rows, rounds=rounds, pending=pending)


def _caller_is_system_manager() -> bool:
	if frappe.session.user == "Administrator":
		return True
	return "System Manager" in set(frappe.get_roles())


@frappe.whitelist()
def get_transitions(
	doc: object,
	workflow: object | None = None,
	raise_exception: bool = False,
) -> list[dict[str, Any]]:
	"""Expose only transition options on the caller's active task."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.model.workflow import get_transitions as core_get_transitions

		return core_get_transitions(doc, workflow, raise_exception)
	doctype, name = _source_identity(doc)
	if not doctype or not name:
		return []
	task_names = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"approver": frappe.session.user,
			"status": "Working",
			"round_status": "Open",
		},
		pluck="name",
		limit=2,
	)
	if len(task_names) != 1:
		if raise_exception:
			raise engine.WorkflowApprovalConflictError(_("No active Workflow Task"))
		return []
	task = frappe.get_doc("Workflow Task", task_names[0])
	task.check_permission("read")
	return [
		{
			"state": row.state,
			"action": row.action,
			"next_state": row.next_state,
			"allowed": row.allowed_role,
			"custom_transition_uuid": row.transition_uuid,
			"custom_comment_is_required": row.comment_is_required,
		}
		for row in task.available_workflow_transitions
	]


@frappe.whitelist()
def get_common_transition_actions(
	docs: str | list[dict[str, Any]],
	doctype: str,
) -> list[str]:
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.model.workflow import (
			get_common_transition_actions as core_get_common_transition_actions,
		)

		return core_get_common_transition_actions(docs, doctype)
	documents = _as_list(docs)
	common: set[str] | None = None
	for document in documents:
		if isinstance(document, dict) and not document.get("doctype"):
			document = {**document, "doctype": doctype}
		actions = {row["action"] for row in get_transitions(document)}
		common = actions if common is None else common.intersection(actions)
		if not common:
			return []
	return sorted(common or [])


@frappe.whitelist(methods=["POST"])
def reset_round(round_id: str, reason: object) -> dict[str, Any]:
	"""Audited System Manager reset for stalled or conflicted rounds."""
	_require_post()
	_require_system_manager()
	normalized_reason = engine.normalize_comment(reason, required=True)
	task_names = engine._round_task_names(round_id)
	if not task_names:
		raise frappe.DoesNotExistError(_("Approval round does not exist"))
	task = frappe.get_doc("Workflow Task", task_names[0])
	engine._lock_domain_dependencies(task.reference_doctype, task.reference_name)
	source = frappe.get_doc(
		task.reference_doctype,
		task.reference_name,
		for_update=True,
	)
	task = frappe.get_doc("Workflow Task", task_names[0], for_update=True)
	if task.round_status not in {"Stalled", "Conflicted", "Open"}:
		raise engine.WorkflowApprovalConflictError(_("Approval round cannot be reset"))
	reset_reason = _("{0} Reset by {1}: {2}").format(
		"System Manager",
		frappe.session.user,
		normalized_reason,
	)
	if engine.configuration_metadata(task) or engine.preview_configuration_conflict(task, source=source):
		rebuilt = engine.rebuild_configuration_conflict(source, round_id, reset_reason)
		source.add_comment(
			"Workflow",
			_("Approval round reset by {0}: {1}. Carried: {2}. Dropped: {3}.").format(
				frappe.bold(frappe.session.user),
				frappe.utils.escape_html(normalized_reason),
				_vote_audit(rebuilt["carried"]),
				_vote_audit(rebuilt["dropped"]),
			),
		)
		return {"round_id": round_id, "new_tasks": rebuilt["new_tasks"]}
	engine._cancel_round(round_id, reset_reason)
	source.add_comment(
		"Workflow",
		_("Approval round reset by {0}: {1}").format(
			frappe.bold(frappe.session.user),
			normalized_reason,
		),
	)
	return {
		"round_id": round_id,
		"new_tasks": engine.reconcile_source(source),
	}


class RebuildRoundFailure(TypedDict):
	round_id: str
	error: str


class RebuildRoundsResult(TypedDict):
	succeeded: list[str]
	failed: list[RebuildRoundFailure]


@frappe.whitelist(methods=["POST"])
def reset_rounds(round_ids: str | list[str], reason: object) -> RebuildRoundsResult:
	"""Rebuild a group with one reason and independent results for each round."""
	_require_post()
	_require_system_manager()
	normalized_reason = engine.normalize_comment(reason, required=True)
	identifiers = list(dict.fromkeys(str(value) for value in _as_list(round_ids)))
	if not identifiers or len(identifiers) > 500:
		frappe.throw(_("Select between 1 and 500 approval rounds to rebuild"))
	result: RebuildRoundsResult = {"succeeded": [], "failed": []}
	for round_id in identifiers:
		try:
			reset_round(round_id, normalized_reason)
			frappe.db.commit()
			result["succeeded"].append(round_id)
		except Exception as exc:
			frappe.db.rollback()
			result["failed"].append({"round_id": round_id, "error": str(exc)})
	return result


def _vote_audit(votes: list[object]) -> str:
	labels = [
		_("{0} voted {1}").format(
			getattr(vote, "approver", None) or vote.get("approver"),
			getattr(vote, "action", None) or vote.get("action"),
		)
		for vote in votes
	]
	return ", ".join(labels) if labels else _("none")


@frappe.whitelist(methods=["POST"])
def retry_finalization(round_id: str) -> dict[str, Any]:
	"""Audited System Manager retry for a failed durable finalization."""
	_require_post()
	_require_system_manager()
	task_names = engine._round_task_names(round_id)
	if not task_names:
		raise frappe.DoesNotExistError(_("Approval round does not exist"))
	task = frappe.get_doc("Workflow Task", task_names[0])
	if task.finalization_status != "Failed":
		raise engine.WorkflowApprovalConflictError(_("Finalization is not failed"))
	engine._set_round_values(
		round_id,
		{
			"round_status": "Finalizing",
			"finalization_status": "Queued",
			"failure_metadata": None,
			"submission_queue": None,
		},
	)
	source = frappe.get_doc(task.reference_doctype, task.reference_name)
	source.add_comment(
		"Workflow",
		_("Approval finalization retried by {0}").format(
			frappe.bold(frappe.session.user)
		),
	)
	from dinext_common.workflow_approval.finalization import repair_round

	repair_round(round_id)
	return {"round_id": round_id, "status": "retried"}


def _number_card(
	value: int,
	route: str,
	route_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
	result = {
		"value": value,
		"fieldtype": "Int",
		"route": ["query-report", route],
	}
	if route_options:
		result["route_options"] = route_options
	return result


@frappe.whitelist()
def open_approval_count() -> dict[str, Any]:
	return _queue_card({})


@frappe.whitelist()
def new_approval_count() -> dict[str, Any]:
	day, _ = _queue_day_filter()
	filters = {"created_on": str(day)}
	return _queue_card(filters)


def _queue_card(filters):
	route_options = dict.fromkeys(
		("created_today", "created_on", "workflow", "reference_doctype", "workflow_state", "action", "minimum_age"),
		"",
	)
	fields = ("creation",) if filters else ()
	return _number_card(
		len(get_personal_queue(filters, fields=fields)),
		"My Approvals",
		{**route_options, **filters, "ignore_prepared_report": True},
	)


def _completed_approval_card(*, automatic_only=False):
	filters = {"completed_since": str(add_days(now_datetime(), -30))}
	if automatic_only:
		filters["completion_source"] = "Automatic Unchanged"
	route_options = dict.fromkeys(
		("workflow", "reference_doctype", "action", "completion_source", "from_date", "to_date"), ""
	)
	return _number_card(
		len(get_personal_history(filters, fields=())),
		"My Approval History",
		{**route_options, **filters, "ignore_prepared_report": True},
	)


@frappe.whitelist()
def completed_approval_count() -> dict[str, Any]:
	return _completed_approval_card()


@frappe.whitelist()
def automatic_approval_count() -> dict[str, Any]:
	return _completed_approval_card(automatic_only=True)


@frappe.whitelist()
def attention_approval_count() -> dict[str, Any]:
	rows = _filtered_tasks(
		{"approver": frappe.session.user, "round_status": ("in", ("Stalled", "Conflicted"))},
		limit=10000,
	)
	return _number_card(len(rows), "My Approvals")


def _control_rounds(round_status):
	rounds = {}
	for row in _monitoring_candidates(("approval_round_id", "round_status", "creation"), 10000):
		rounds.setdefault(row.approval_round_id, row)
	return [row for row in rounds.values() if _round_status_matches(row.round_status, round_status)]


@frappe.whitelist()
def open_control_round_count() -> dict[str, Any]:
	rows = _control_rounds("Open")
	return _number_card(len(rows), "Approval Monitoring", {"round_status": "Open"})


@frappe.whitelist()
def attention_control_round_count() -> dict[str, Any]:
	rows = _control_rounds("Attention")
	return _number_card(
		len(rows),
		"Approval Monitoring",
		{"round_status": "Attention"},
	)


@frappe.whitelist()
def longest_control_wait() -> dict[str, Any]:
	from frappe.utils import now_datetime, time_diff_in_hours

	from dinext_common.workflow_approval.control import longest_open_round_days

	now = now_datetime()
	rows = _control_rounds("Open")
	result = _number_card(
		longest_open_round_days(max(0, time_diff_in_hours(now, row.creation)) for row in rows),
		"Approval Monitoring",
		{"round_status": "Open"},
	)
	result["fieldtype"] = "Float"
	return result


@frappe.whitelist()
def control_decision_count() -> dict[str, Any]:
	from dinext_common.workflow_approval.control import aggregate_duration, manual_total

	since = add_days(now_datetime(), -30)
	tasks = get_monitored_tasks(
		{"status": "Completed", "completed_since": since},
	)
	rows = aggregate_duration(tasks, "Document Type", {})
	return _number_card(
		manual_total(rows),
		"Approval Duration",
		{
			"from_date": str(getdate(since)),
			"to_date": str(getdate(now_datetime())),
			"group_by": "Document Type",
			"chart": "Completed duration",
		},
	)


@frappe.whitelist()
def get_approval_dashboard() -> dict[str, Any]:
	"""Return personal queue/history/chart and source-safe monitoring rows."""
	queue = get_my_queue()
	history = get_my_history()
	by_doctype: dict[str, int] = {}
	for row in queue:
		doctype = row["reference_doctype"]
		by_doctype[doctype] = by_doctype.get(doctype, 0) + 1

	monitoring = get_monitoring_rows(limit=1000)
	return {
		"queue": queue,
		"history": history,
		"by_doctype": [
			{"doctype": doctype, "count": count}
			for doctype, count in sorted(by_doctype.items())
		],
		"can_monitor": bool(get_monitorable_workflows()),
		"monitoring": monitoring,
	}


def _monitoring_candidates(fields, limit):
	return _select_task_rows(
		{"round_status": ("in", MONITORING_STATUSES), "source_deleted_at": ("is", "not set")},
		fields=fields,
		order_by="creation asc, name asc",
		limit=int(limit),
		monitored_only=True,
	)


@frappe.whitelist()
def get_monitoring_rows(
	filters: str | dict[str, Any] | None = None,
	limit: int = 10000,
) -> list[dict[str, Any]]:
	values = frappe.parse_json(filters) if isinstance(filters, str) else dict(filters or {})
	grouped: dict[str, dict[str, Any]] = {}
	for row in _monitoring_candidates(QUEUE_FIELDS, limit):
		payload = grouped.setdefault(
			row.approval_round_id,
			{
				**{field: row.get(field) for field in QUEUE_FIELDS if field != "source_deleted_at"},
				"pending_approvers": [],
				"active_task_count": 0,
				"available_actions": [],
				"transition_uuids": [],
			},
		)
		manifest = frappe.parse_json(row.round_manifest) or {}
		for transition in manifest.get("transitions") or []:
			if transition.get("action") not in payload["available_actions"]:
				payload["available_actions"].append(transition.get("action"))
			if transition.get("transition_uuid") not in payload["transition_uuids"]:
				payload["transition_uuids"].append(transition.get("transition_uuid"))
		if row.status == "Working":
			payload["pending_approvers"].append(row.approver or row.user)
			payload["active_task_count"] += 1
	result = []
	from frappe.utils import now_datetime, time_diff_in_hours

	for row in grouped.values():
		row["pending_approvers"] = ", ".join(
			sorted({approver for approver in row["pending_approvers"] if approver})
		)
		row["available_actions"] = ", ".join(
			sorted(filter(None, row["available_actions"]))
		)
		row["transition_uuids"] = ", ".join(
			sorted(filter(None, row["transition_uuids"]))
		)
		row["age_hours"] = max(
			0,
			time_diff_in_hours(now_datetime(), row["creation"]),
		)
		if _monitor_row_matches(row, values):
			result.append(frappe._dict(row))
	return result


def _monitor_row_matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
	return all(
		(
			not filters.get("workflow") or row["workflow"] == filters["workflow"],
			not filters.get("reference_doctype")
			or row["reference_doctype"] == filters["reference_doctype"],
			not filters.get("workflow_state")
			or row["workflow_state"] == filters["workflow_state"],
			not filters.get("round_status")
			or _round_status_matches(row.get("round_status"), filters["round_status"]),
			not filters.get("action")
			or filters["action"] in row["available_actions"].split(", "),
			not filters.get("transition_uuid")
			or filters["transition_uuid"] in row["transition_uuids"].split(", "),
			not filters.get("pending_approver")
			or filters["pending_approver"] in row["pending_approvers"].split(", "),
			not filters.get("minimum_age_hours")
			or row["age_hours"] >= float(filters["minimum_age_hours"]),
		)
	)


def _round_status_matches(status: str | None, expected: str) -> bool:
	choice = canonical_choice(
		expected,
		("Open", "Stalled", "Conflicted", "Attention"),
	)
	if choice == "Attention":
		return status in {"Stalled", "Conflicted"}
	return status == choice


def canonical_choice(value: str | None, choices: tuple[str, ...]) -> str:
	"""Match a filter value in the request language or in English."""
	text = str(value or "").strip()
	if not text:
		return choices[0]
	for choice in choices:
		if text == choice or text == _(choice):
			return choice
	return text


def approver_display_names(approvers: list[str]) -> dict[str, str]:
	idents = sorted({approver for approver in approvers if approver})
	if not idents:
		return {}
	rows = frappe.get_all(
		"User",
		filters={"name": ("in", idents)},
		fields=["name", "full_name"],
	)
	return {
		row.name: (row.full_name or row.name)
		for row in rows
	}


def get_monitored_tasks(
	filters: str | dict[str, Any] | None = None,
	limit: int = 10000,
) -> list[dict[str, Any]]:
	"""Return source-readable tasks from workflows the user monitors."""
	values = frappe.parse_json(filters) if isinstance(filters, str) else dict(filters or {})
	task_filters: dict[str, Any] = {}
	if values.get("status"):
		task_filters["status"] = values["status"]
	if values.get("round_status"):
		choice = canonical_choice(
			values["round_status"],
			("Open", "Stalled", "Conflicted", "Attention"),
		)
		if choice == "Attention":
			task_filters["round_status"] = ("in", ["Stalled", "Conflicted"])
		else:
			task_filters["round_status"] = choice
	if values.get("completed_since"):
		task_filters["completed_at"] = (">=", values["completed_since"])
	if values.get("workflow"):
		task_filters["workflow"] = values["workflow"]
	if values.get("reference_doctype"):
		task_filters["reference_doctype"] = values["reference_doctype"]
	task_filters["source_deleted_at"] = ("is", "not set")
	return _select_task_rows(
		task_filters,
		fields=MONITORED_TASK_FIELDS,
		order_by="creation asc, name asc",
		limit=int(limit),
		monitored_only=True,
	)


def _card_state_values(state: str) -> list[str]:
	"""English workflow states and the Russian values stored before the timesheet migration."""
	groups = (
		("Approved", "Согласовано", "Согласован"),
		("Pending Approval", "На согласовании"),
	)
	for group in groups:
		if state in group:
			return list(group)
	return [state]


@frappe.whitelist()
def get_legacy_number_card_result(filters: str | dict[str, Any]) -> dict[str, Any]:
	"""Return current, readable source populations for the six approval cards."""
	values = frappe.parse_json(filters) if isinstance(filters, str) else dict(filters)
	doctype = values.get("doc")
	state = values.get("state")
	route = values.get("route")
	if not doctype or not state or not route:
		raise frappe.ValidationError(_("Card filters require doc, state, and route"))
	completed = state in {"Согласовано", "Согласован", "Approved"}
	task_filters: dict[str, Any] = {
		"approver": frappe.session.user,
		"reference_doctype": doctype,
		"status": "Completed" if completed else "Working",
		"round_status": "Transitioned" if completed else "Open",
		"source_deleted_at": ["is", "not set"],
		"next_state" if completed else "workflow_state": ["in", _card_state_values(state)],
	}
	# Read only the fields needed for source authorization and pending target selection.
	rows = frappe.get_all(
		"Workflow Task",
		filters=task_filters,
		fields=[
			"name", "workflow", "reference_name", "reference_doctype", "approver",
			"approval_round_id", "source_deleted_at",
		],
		limit_page_length=0,
	)
	if completed and rows:
		latest_round = {}
		# Round metadata is an internal authorization input, never returned to the caller.
		for task in frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": doctype,
				"reference_name": ["in", list({row.reference_name for row in rows})],
				"source_deleted_at": ["is", "not set"],
			},
			fields=["reference_name", "approval_round_id"],
			order_by="creation desc, name desc",
			limit_page_length=0,
		):
			latest_round.setdefault(task.reference_name, task.approval_round_id)
		rows = [row for row in rows if row.approval_round_id == latest_round.get(row.reference_name)]
	if not completed:
		required = required_target_task_names(rows)
		rows = [row for row in rows if row.name in required]
	unique = {row.reference_name: row for row in rows}
	names = [
		name for name, row in unique.items() if has_workflow_task_permission(row, "read", frappe.session.user)
	]
	if names:
		state_field = {"User Timesheet Position": "status", "Application For Leave": "status"}.get(
			doctype, "workflow_state"
		)
		filters = {
			"name": ["in", names],
			"docstatus": ["!=", 2],
			state_field: ["in", _card_state_values(state)],
		}
		if state_field != "workflow_state" and frappe.get_meta(doctype).has_field("workflow_state"):
			filters["workflow_state"] = ["in", _card_state_values(state)]
		previous_cmd = frappe.form_dict.get("cmd")
		try:
			# Include the destination list's display rules without bypassing source permissions.
			frappe.form_dict.cmd = "frappe.desk.reportview.get"
			names = frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0)
		finally:
			if previous_cmd is None:
				frappe.form_dict.pop("cmd", None)
			else:
				frappe.form_dict.cmd = previous_cmd
	names = sorted(set(names))
	return {
		"value": len(names),
		"fieldtype": "Data",
		"route_options": {"name": ["in", names]} if names else {"name": ["is", "not set"]},
		"route": ["list", route],
	}
