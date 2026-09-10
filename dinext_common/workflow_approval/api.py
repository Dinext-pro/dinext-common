"""Whitelisted task-based API and compatibility adapters."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.permissions import (
	get_monitorable_workflows,
	has_workflow_task_permission,
	is_workflow_monitor,
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
	"completed_at",
	"cancelled_at",
	"cancellation_reason",
	"action",
	"next_state",
	"completion_source",
	"reused_from_workflow_task",
	"policy",
	"threshold",
	"round_manifest",
	"vote_comment",
]


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


def _find_task_for_action(doctype: str, name: str, action: str, user: str) -> str:
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
	matches = [
		task_name
		for task_name in task_names
		if frappe.db.exists(
			"Available Workflow Transitions",
			{"parent": task_name, "action": action},
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
	comment: object = None,
	request_id: str | None = None,
	completion_source: str = "Manual",
) -> engine.VoteResult:
	task_name = _find_task_for_action(doctype, name, action, frappe.session.user)
	return engine.cast_vote(
		task_name,
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
) -> None:
	"""Compatibility override for the standard Frappe bulk method."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.model.workflow import bulk_workflow_approval as core_bulk_workflow_approval

		return core_bulk_workflow_approval(docnames, doctype, action)
	names = [str(name) for name in _as_list(docnames)]
	if len(names) < 20:
		bulk_vote(doctype, names, action, comment, request_id)
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
			queue="short",
			timeout=1000,
		)
		return None
	frappe.throw(
		_("Bulk approval only supports up to 500 documents."),
		title=_("Too Many Documents"),
	)


def _task_row(task: object) -> dict[str, Any]:
	return {
		field: getattr(task, field, None)
		for field in QUEUE_FIELDS
	}


def _filtered_tasks(filters: dict[str, Any], *, limit: int = 500) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"Workflow Task",
		filters=filters,
		fields=QUEUE_FIELDS,
		order_by="modified desc, name asc",
		limit=limit,
	)
	result = []
	for row in rows:
		task = frappe.get_doc("Workflow Task", row["name"])
		if has_workflow_task_permission(task, "read", frappe.session.user):
			payload = dict(row)
			payload["available_transitions"] = [
				{
					"transition_uuid": transition.transition_uuid,
					"action": transition.action,
					"next_state": transition.next_state,
					"comment_is_required": bool(transition.comment_is_required),
				}
				for transition in getattr(task, "available_workflow_transitions", [])
			]
			result.append(payload)
	return result


@frappe.whitelist()
def get_my_queue(limit: int = 500) -> list[dict[str, Any]]:
	return _filtered_tasks(
		{
			"approver": frappe.session.user,
			"status": "Working",
			"round_status": "Open",
		},
		limit=int(limit),
	)


@frappe.whitelist()
def get_my_history(limit: int = 500) -> list[dict[str, Any]]:
	return _filtered_tasks(
		{
			"approver": frappe.session.user,
			"status": ("in", ("Completed", "Cancelled")),
		},
		limit=int(limit),
	)


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
		rows = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": doctype,
				"reference_name": name,
				"status": "Working",
				"round_status": "Open",
			},
			fields=["approver", "approval_round_id", "workflow_state"],
			order_by="approver asc",
		)
	names = dict(
		frappe.get_all(
			"User",
			filters={"name": ("in", sorted({row.approver for row in rows}))},
			fields=["name", "full_name"],
			as_list=True,
		)
	) if rows else {}
	for row in rows:
		row["approver_name"] = names.get(row.approver) or row.approver
	return rows


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
	source = frappe.get_doc(
		task.reference_doctype,
		task.reference_name,
		for_update=True,
	)
	if task.round_status not in {"Stalled", "Conflicted", "Open"}:
		raise engine.WorkflowApprovalConflictError(_("Approval round cannot be reset"))
	engine._cancel_round(
		round_id,
		_("{0} Reset by {1}: {2}").format(
			"System Manager",
			frappe.session.user,
			normalized_reason,
		),
	)
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
	return _number_card(len(get_my_queue(limit=10000)), "My Approvals")


@frappe.whitelist()
def new_approval_count() -> dict[str, Any]:
	from dinext_common.workflow_approval.notifications import (
		_aware_utc,
		_recipient_timezone,
		get_timezone,
	)

	zone = get_timezone(_recipient_timezone(frappe.session.user))
	today = _aware_utc(frappe.utils.now_datetime()).astimezone(zone).date()
	value = sum(
		1
		for row in get_my_queue(limit=10000)
		if _aware_utc(row.creation).astimezone(zone).date() == today
	)
	return _number_card(value, "My Approvals", {"created_today": 1})


def _recent_completed_tasks(*, automatic_only: bool = False) -> list[dict[str, Any]]:
	from frappe.utils import add_days, now_datetime

	filters: dict[str, Any] = {
		"approver": frappe.session.user,
		"status": "Completed",
		"completed_at": (">=", add_days(now_datetime(), -30)),
	}
	if automatic_only:
		filters["completion_source"] = "Automatic Unchanged"
	return _filtered_tasks(
		filters,
		limit=10000,
	)


@frappe.whitelist()
def completed_approval_count() -> dict[str, Any]:
	rows = _recent_completed_tasks()
	return _number_card(len(rows), "My Approval History")


@frappe.whitelist()
def automatic_approval_count() -> dict[str, Any]:
	rows = _recent_completed_tasks(automatic_only=True)
	return _number_card(
		len(rows),
		"My Approval History",
		{
			"completion_source": "Automatic Unchanged",
		},
	)


@frappe.whitelist()
def attention_approval_count() -> dict[str, Any]:
	rows = _filtered_tasks(
		{
			"approver": frappe.session.user,
			"round_status": ("in", ("Stalled", "Conflicted")),
		},
		limit=10000,
	)
	return _number_card(len(rows), "My Approvals")


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


@frappe.whitelist()
def get_monitoring_rows(
	filters: str | dict[str, Any] | None = None,
	limit: int = 10000,
) -> list[dict[str, Any]]:
	values = frappe.parse_json(filters) if isinstance(filters, str) else dict(filters or {})
	candidates = frappe.get_all(
		"Workflow Task",
		filters={
			"round_status": ("in", ("Open", "Stalled", "Conflicted")),
		},
		fields=QUEUE_FIELDS,
		order_by="creation asc",
		limit=int(limit),
	)
	grouped: dict[str, dict[str, Any]] = {}
	for row in candidates:
		task = frappe.get_doc("Workflow Task", row.name)
		if not is_workflow_monitor(task):
			continue
		if has_workflow_task_permission(task, "read", frappe.session.user):
			payload = grouped.setdefault(
				row.approval_round_id,
				{
					**dict(row),
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
					payload["transition_uuids"].append(
						transition.get("transition_uuid")
					)
			if row.status == "Working":
				payload["pending_approvers"].append(row.approver)
				payload["active_task_count"] += 1
	result = []
	from frappe.utils import now_datetime, time_diff_in_hours

	for row in grouped.values():
		row["pending_approvers"] = ", ".join(sorted(set(row["pending_approvers"])))
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
			result.append(row)
	return result


def _monitor_row_matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
	return all(
		(
			not filters.get("workflow") or row["workflow"] == filters["workflow"],
			not filters.get("reference_doctype")
			or row["reference_doctype"] == filters["reference_doctype"],
			not filters.get("workflow_state")
			or row["workflow_state"] == filters["workflow_state"],
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


@frappe.whitelist()
def get_legacy_number_card_result(filters: str | dict[str, Any]) -> dict[str, Any]:
	"""Preserve four timesheet card DTOs while using source-aware task fields."""
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
	}
	task_filters["next_state" if completed else "workflow_state"] = state
	rows = _filtered_tasks(task_filters, limit=10000)
	if not completed:
		rows = [row for row in rows if row.source_owner != frappe.session.user]
	names = sorted({row.reference_name for row in rows})
	return {
		"value": len(names),
		"fieldtype": "Data",
		"route_options": {"name": ["in", names]},
		"route": ["list", route],
	}
