"""Optional Common-owned adapters for aggregate Timesheets approval actions."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any, TypedDict

import frappe
from frappe import _

from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.scenarios import service

POSITION = "User Timesheet Position"
_originals = {}


class TimesheetActionsResponse(TypedDict):
	actions: list[dict[str, Any]]


class TimesheetActionResponse(TypedDict):
	timesheet: str
	results: list[dict[str, Any]]
	messages: list[str]
	processed: int
	total: int


def _producer():
	return importlib.import_module("dinext_timesheets.workflow_approval")


def _enabled():
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	return is_engine_enabled() and service.is_ready()


def _request_cache_key(parent, request_id: str) -> str:
	identity = [getattr(frappe.local, "site", None), frappe.session.user, parent.name,
		str(parent.creation), request_id]
	return "timesheet_workflow_request:" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def _replay_parent_action(parent, action: str, request_id: str | None, targets=None) -> TimesheetActionResponse | None:
	if not request_id:
		return None
	key = _request_cache_key(parent, request_id)
	cached = frappe.cache.get_value(key)
	if cached:
		if cached["action"] != action:
			raise engine.WorkflowApprovalConflictError(_("The action is not available for the timesheet positions"))
		if targets is not None:
			validate_targets(cached["targets"], targets)
		for target in cached["targets"]:
			frappe.get_doc(POSITION, target["name"]).check_permission("read")
		return cached["response"]
	names = frappe.get_all(POSITION, filters={"user_timesheet": parent.name}, pluck="name")
	if not names:
		return None
	prefix = request_id + ":"
	rows = frappe.get_all("Workflow Task", filters={"reference_doctype": POSITION,
		"reference_name": ("in", names), "approver": frappe.session.user, "status": "Completed",
		"correlation_id": ("like", prefix + "%")}, fields=["name", "reference_name", "workflow",
		"workflow_process", "transition_uuid", "action", "correlation_id", "source_created_at"], order_by="name asc")
	rows = [row for row in rows if str(row.correlation_id or "").startswith(prefix)]
	if not rows:
		return None
	from frappe.utils import get_datetime

	valid = []
	for row in rows:
		source = frappe.get_doc(POSITION, row.reference_name)
		source.check_permission("read")
		if row.source_created_at and get_datetime(row.source_created_at) != get_datetime(source.creation):
			continue
		if row.action != action:
			raise engine.WorkflowApprovalConflictError(_("The action is not available for the timesheet positions"))
		valid.append(row)
	if not valid:
		return None
	valid.sort(key=lambda row: (str(row.correlation_id).removeprefix(prefix).zfill(6), row.name))
	expected = [{"name": row.reference_name, "workflow": row.workflow, "process_id": row.workflow_process,
		"task_name": row.name, "transition_uuid": row.transition_uuid} for row in valid]
	if targets is not None:
		validate_targets(expected, targets)
	results = [engine.cast_vote(row.name, action=action, transition_uuid=row.transition_uuid,
		request_id=row.correlation_id, completion_source="Bulk") for row in valid]
	return {"timesheet": parent.name, "results": results, "messages": [], "processed": len(valid), "total": len(valid)}


def _remember_parent_action(parent, action: str, request_id: str | None, targets, response) -> None:
	if not request_id:
		return
	key = _request_cache_key(parent, request_id)
	payload = deepcopy({"action": action, "targets": targets, "response": response})
	frappe.db.after_commit.add(lambda: frappe.cache.set_value(key, payload, expires_in_sec=24 * 60 * 60))


def group_position_actions(current: dict[str, str], options: dict[str, list[dict]]) -> list[dict]:
	"""Keep each eligible position's identity and omit action names ambiguous on any position."""
	ambiguous = {action for items in options.values()
		for action, count in Counter(item["action"] for item in items).items() if count > 1}
	grouped = {}
	for name, items in options.items():
		for item in items:
			action = item["action"]
			if action in ambiguous:
				continue
			row = grouped.setdefault(action, {"action": action, "comment_is_required": False,
				"confirm_return_to_editing": False, "positions": [], "targets": []})
			row["comment_is_required"] |= bool(item.get("comment_is_required"))
			row["confirm_return_to_editing"] |= current.get(name) == "Approved" and item["next_state"] == "Editing"
			position = {"name": name, "mode": item["mode"], "task": item.get("task"),
				"next_state": item["next_state"], "workflow": item.get("workflow"),
				"process_id": item.get("process_id"), "transition_uuid": item.get("transition_uuid")}
			row["positions"].append(position)
			row["targets"].append({key: position.get(key) for key in (
				"name", "workflow", "process_id", "transition_uuid", "next_state")}
				| {"task_name": position.get("task")})
	return sorted(grouped.values(), key=lambda row: row["action"])


def validate_targets(expected: list[dict], targets: object) -> None:
	"""Reject an old menu rather than rediscovering an action in a replacement process."""
	try:
		targets = json.loads(targets) if isinstance(targets, str) else targets
	except (ValueError, TypeError):
		targets = None
	fields = ("workflow", "process_id", "task_name", "transition_uuid")
	if not isinstance(targets, list) or any(not isinstance(row, dict) or
		not isinstance(row.get("name"), str) or not row["name"] for row in targets):
		raise engine.WorkflowApprovalConflictError(_("No unique active Workflow Task is available for this action"))
	by_name = {row.get("name"): row for row in targets}
	if len(by_name) != len(targets) or set(by_name) != {row["name"] for row in expected}:
		raise engine.WorkflowApprovalConflictError(_("No unique active Workflow Task is available for this action"))
	for row in expected:
		candidate = by_name[row["name"]]
		if any(field not in candidate or candidate[field] != row.get(field) for field in fields):
			raise engine.WorkflowApprovalConflictError(_("No unique active Workflow Task is available for this action"))


def _rollup_settings():
	from dinext_timesheets.timesheet_settings import matching_position_rule, timesheet_check_status

	return matching_position_rule, timesheet_check_status


def _position_status_counts(parent_name: str, changed_position) -> dict[str, int]:
	statuses = []
	for name in frappe.get_all(POSITION, filters={"user_timesheet": parent_name}, pluck="name"):
		doc = changed_position if name == changed_position.name else frappe.get_doc(POSITION, name)
		context = service.get_context(doc)
		statuses.append(context["state"] if context["workflow"] else doc.status)
	return dict(Counter(state for state in statuses if state))


def recalculate_parent(parent, changed_position, old_status: str | None) -> None:
	"""Keep Timesheets rules while reading each sibling's own selected state field."""
	if not _enabled():
		return _originals["_recalculate_parent"](parent, changed_position, old_status)
	matching_position_rule, timesheet_check_status = _rollup_settings()
	rule = matching_position_rule(_position_status_counts(parent.name, changed_position))
	if not rule or parent.ut_status == rule["timesheet_status"]:
		return
	producer = _producer()
	new_status = rule["timesheet_status"]
	if new_status == timesheet_check_status():
		names = frappe.get_all(POSITION, filters={"user_timesheet": parent.name}, pluck="name", order_by="name asc")
		producer._validate_positions(parent, [frappe.get_doc(POSITION, name) for name in names])
	parent.ut_status = new_status
	parent.ut_approval_date = frappe.utils.nowdate() if new_status == "Approved" else None
	target = rule["position_status"] if rule.get("move_all_positions") else None
	if not target:
		parent.save(ignore_permissions=True)
		return
	previous = getattr(frappe.flags, "in_timesheet_approval_cascade", False)
	frappe.flags.in_timesheet_approval_cascade = True
	try:
		parent.save(ignore_permissions=True)
		siblings = frappe.get_all(POSITION, filters={"user_timesheet": parent.name,
			"name": ("!=", changed_position.name)}, pluck="name", order_by="name asc")
		for name in siblings:
			sibling = frappe.get_doc(POSITION, name)
			context = service.get_context(sibling)
			if not context["workflow"] or context["state"] == target:
				continue
			try:
				engine.apply_domain_transition(POSITION, name, target,
					reason=_("Timesheet status {0}").format(new_status), actor=frappe.session.user)
			except Exception:
				frappe.log_error(title=f"Timesheet sibling transition failed: {name}")
				producer._note_timesheet_transition_message(
					_("Could not update a related timesheet position: {0}").format(name))
	finally:
		frappe.flags.in_timesheet_approval_cascade = previous


def _position_action_items(doc) -> list[dict]:
	from dinext_common.workflow_approval.scenarios.compat import document_scope

	context = service.get_context(doc)
	if not context["workflow"]:
		return []
	identity = {"workflow": context["workflow"], "process_id": context["process_id"]}
	filters = {"reference_doctype": POSITION, "reference_name": doc.name,
		"approver": frappe.session.user, "status": "Working", "round_status": "Open",
		"workflow": context["workflow"]}
	if context["process_id"]:
		filters["workflow_process"] = context["process_id"]
	names = frappe.get_all("Workflow Task", filters=filters, pluck="name", limit=2)
	if len(names) > 1:
		return []
	if names:
		task = frappe.get_doc("Workflow Task", names[0])
		task.check_permission("read")
		return [{"action": row.action, "next_state": row.next_state,
			"comment_is_required": bool(row.comment_is_required), "mode": "vote", "task": task.name,
			"transition_uuid": row.transition_uuid, **identity}
			for row in task.available_workflow_transitions if row.action and row.next_state and row.transition_uuid]
	if context["process_id"]:
		# A completed personal vote must keep waiting for the remaining quorum.
		return []
	from frappe.model.workflow import get_transitions

	with document_scope(doc):
		try:
			transitions = get_transitions(doc)
		except (frappe.ValidationError, frappe.PermissionError):
			return []
	return [{"action": row.action, "next_state": row.next_state,
		"comment_is_required": bool(row.get("custom_comment_is_required")), "mode": "domain", "task": None,
		"transition_uuid": row.get("custom_transition_uuid"), **identity}
		for row in transitions if row.get("allow_self_approval") and row.action and row.next_state]


@frappe.whitelist()
def get_timesheet_position_actions(timesheet_name: str) -> TimesheetActionsResponse:
	"""Describe actionable child positions while retaining each selected process identity."""
	if not _enabled():
		return _originals.get("get_timesheet_position_actions", _producer().get_timesheet_position_actions)(timesheet_name)
	parent = frappe.get_doc("User Timesheet", timesheet_name)
	parent.check_permission("read")
	current, options = {}, {}
	for name in frappe.get_all(POSITION, filters={"user_timesheet": parent.name}, pluck="name", order_by="name asc"):
		doc = frappe.get_doc(POSITION, name)
		try:
			doc.check_permission("read")
		except frappe.PermissionError:
			continue
		context = service.get_context(doc)
		current[name] = str(context["state"] if context["workflow"] else doc.status or "")
		options[name] = _position_action_items(doc)
	from dinext_timesheets.timesheet_settings import matching_position_rule, timesheet_check_status

	check_status = timesheet_check_status()
	actions = group_position_actions(current, options)
	for row in actions:
		updates = {position["name"]: position["next_state"] for position in row["positions"]}
		counts = Counter(updates.get(name) or state for name, state in current.items())
		counts.pop("", None)
		rule = matching_position_rule(dict(counts))
		row["runs_timesheet_checks"] = bool(rule and check_status and rule["timesheet_status"] == check_status
			and parent.ut_status != check_status)
	return {"actions": actions}


@frappe.whitelist(methods=["POST"])
def apply_timesheet_position_action(
	timesheet_name: str, action: str, comment: object = None, request_id: str | None = None,
	track_progress: bool = False, targets: object = None,
) -> TimesheetActionResponse:
	"""Apply exact position decisions under the existing aggregate parent lock and rollup boundary."""
	if not _enabled():
		return _originals.get("apply_timesheet_position_action", _producer().apply_timesheet_position_action)(
			timesheet_name, action, comment, request_id, track_progress)
	from dinext_common.workflow_approval.api import _require_post, publish_workflow_progress

	_require_post()
	producer = _producer()
	parent = frappe.get_doc("User Timesheet", timesheet_name, for_update=True)
	parent.check_permission("read")
	replayed = _replay_parent_action(parent, action, request_id, targets)
	if replayed is not None:
		return replayed
	available = get_timesheet_position_actions(parent.name)
	chosen = next((row for row in available["actions"] if row["action"] == action), None)
	if not chosen:
		raise frappe.ValidationError(_("The action is not available for the timesheet positions"))
	if targets is not None:
		validate_targets(chosen["targets"], targets)
	comment = engine.normalize_comment(comment, required=chosen["comment_is_required"])
	frappe.flags.timesheet_transition_messages = []
	frappe.flags.workflow_finalization_errors = []
	positions = chosen["positions"]
	total, processed = len(positions), 0
	report_progress = total > 1 and bool(request_id) and str(track_progress).lower() in {"1", "true"}
	results = []
	previous_defer = getattr(frappe.flags, "defer_timesheet_rollup", None)
	frappe.flags.defer_timesheet_rollup = True
	try:
		for processed, position in enumerate(positions, start=1):
			try:
				source = frappe.get_doc(POSITION, position["name"], for_update=True)
				source.check_permission("read")
				live = service.get_context(source)
				if live["workflow"] != position["workflow"] or live["process_id"] != position["process_id"]:
					raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
				if position["mode"] != "vote":
					engine.apply_domain_transition(POSITION, position["name"], position["next_state"],
						reason=_("Timesheet action {0}").format(action), actor=frappe.session.user)
					results.append({"name": position["name"], "transitioned": True})
				elif not producer._task_no_longer_matches_source(position["task"]):
					results.append(engine.cast_vote(position["task"], action=action,
						transition_uuid=position["transition_uuid"], comment=comment,
						request_id=f"{request_id or frappe.generate_hash(length=16)}:{processed - 1}", completion_source="Bulk"))
				else:
					raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
			except engine.WorkflowApprovalConflictError as caught:
				if not any(row.get("transitioned") for row in results):
					raise
				producer._note_timesheet_transition_message(str(caught))
			if report_progress:
				publish_workflow_progress(request_id, processed, total)
	finally:
		frappe.flags.defer_timesheet_rollup = previous_defer
	parent.reload()
	if positions:
		producer._recalculate_parent(parent, frappe.get_doc(POSITION, positions[-1]["name"]), None)
	response = {"timesheet": parent.name, "results": results,
		"messages": [*(getattr(frappe.flags, "workflow_finalization_errors", None) or []),
			*(getattr(frappe.flags, "timesheet_transition_messages", None) or [])],
		"processed": processed, "total": total}
	_remember_parent_action(parent, action, request_id, chosen["targets"], response)
	return response


def install() -> None:
	"""Adapt producer imports without modifying its files or requiring the optional app."""
	try:
		producer = _producer()
	except ModuleNotFoundError as error:
		if error.name and error.name.split(".")[0] == "dinext_timesheets":
			return
		raise
	from dinext_common.workflow_approval.scenarios.compat import replace_function

	for name, replacement in (("get_timesheet_position_actions", get_timesheet_position_actions),
		("apply_timesheet_position_action", apply_timesheet_position_action),
		("_recalculate_parent", recalculate_parent)):
		if name in _originals:
			continue
		_originals[name] = getattr(producer, name)
		replace_function(_originals[name], replacement)
