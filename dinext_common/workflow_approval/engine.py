"""Atomic task-based approval engine for standard Frappe Workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, TypedDict

import frappe
from frappe import _
from frappe.model.workflow import (
	apply_workflow as core_apply_workflow,
	get_workflow,
	get_workflow_name,
	has_approval_access,
	is_transition_condition_satisfied,
)
from frappe.utils import now_datetime
from frappe.utils.user import get_users_with_role

from dinext_common.workflow_approval.fingerprint import (
	ContentFingerprint,
	find_latest_reusable_task,
	fingerprint_document,
)
from dinext_common.workflow_approval.policy import (
	ZeroEligibleApproversError,
	is_threshold_reachable,
	normalize_comment,
	normalize_policy,
	required_approvals,
	transition_semantic_hash,
)

ACTIVE_ROUND_STATUSES = ("Open", "Stalled", "Finalizing", "Conflicted")
MAX_AUTOMATIC_TRANSITIONS = 20


class WorkflowApprovalError(frappe.ValidationError):
	"""Base exception for approval contract failures."""


class WorkflowApprovalConflictError(WorkflowApprovalError):
	"""Raised when a vote no longer matches current source or workflow state."""


class AutomationCycleError(WorkflowApprovalError):
	"""Raised when automatic approvals repeat a state or exceed their bound."""


class VoteResult(TypedDict):
	task: str
	status: str
	round_status: str
	transitioned: bool
	reference_doctype: str
	reference_name: str
	workflow_state: str | None


@dataclass
class AutomationCycleGuard:
	max_transitions: int = MAX_AUTOMATIC_TRANSITIONS
	visited: set[tuple[str, str, str]] = field(default_factory=set)
	transition_count: int = 0

	def visit(self, workflow: str, state: str, content_fingerprint: str) -> None:
		key = (workflow, state, content_fingerprint)
		if key in self.visited:
			raise AutomationCycleError("Automatic workflow approval cycle detected")
		if self.transition_count >= self.max_transitions:
			raise AutomationCycleError("Automatic workflow transition limit exceeded")
		self.visited.add(key)
		self.transition_count += 1


def _value(row: object, key: str, default: Any = None) -> Any:
	if isinstance(row, dict):
		return row.get(key, default)
	if hasattr(row, "get"):
		return row.get(key, default)
	return getattr(row, key, default)


def serialize_manifest(manifest: dict[str, Any]) -> str:
	return json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def build_round_manifest(
	transitions: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
	"""Freeze transition cohorts and produce per-approver task options."""
	snapshots: list[dict[str, Any]] = []
	task_transitions: dict[str, list[dict[str, Any]]] = {}
	for transition in sorted(
		transitions,
		key=lambda row: (int(row.get("idx") or 0), str(row.get("transition_uuid") or "")),
	):
		approvers = sorted(set(transition.get("eligible_approvers") or []))
		policy = normalize_policy(transition.get("policy"))
		threshold = required_approvals(
			policy,
			transition.get("minimum_approvals"),
			len(approvers),
		)
		snapshot = {
			"action": transition.get("action") or "",
			"allowed": transition.get("allowed") or "",
			"auto_complete_unchanged": bool(transition.get("auto_complete_unchanged")),
			"comment_is_required": bool(transition.get("comment_is_required")),
			"send_email_to_creator": bool(
				transition.get("send_email_to_creator")
			),
			"email_template": transition.get("email_template"),
			"attach_document_pdf": bool(transition.get("attach_document_pdf")),
			"eligible_approvers": approvers,
			"idx": int(transition.get("idx") or 0),
			"next_state": transition.get("next_state") or "",
			"policy": policy,
			"reset_on_change": bool(transition.get("reset_on_change")),
			"state": transition.get("state") or "",
			"threshold": threshold,
			"transition_semantic_hash": transition.get("transition_semantic_hash") or "",
			"transition_uuid": transition.get("transition_uuid") or "",
		}
		snapshots.append(snapshot)
		for approver in approvers:
			task_transitions.setdefault(approver, []).append(dict(snapshot))
	return {"version": 1, "transitions": snapshots}, task_transitions


def manifest_matches_configuration(
	manifest: dict[str, Any],
	current_hashes: dict[str, str],
) -> bool:
	rows = manifest.get("transitions") or []
	snapshot_hashes = {
		str(row.get("transition_uuid") or ""): str(row.get("transition_semantic_hash") or "")
		for row in rows
	}
	return snapshot_hashes == current_hashes


def select_automatic_winner(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
	reached = [row for row in rows if int(row["votes"]) >= int(row["threshold"])]
	if not reached:
		return None
	return sorted(
		reached,
		key=lambda row: (
			str(row.get("latest_reused_completed_at") or ""),
			-int(row.get("idx") or 0),
			_inverse_text(str(row.get("transition_uuid") or "")),
		),
		reverse=True,
	)[0]


def _inverse_text(value: str) -> tuple[int, ...]:
	"""Make reverse sorting choose the lexicographically smallest text."""
	return tuple(-ord(character) for character in value)


def _transition_dict(transition: object) -> dict[str, Any]:
	policy = normalize_policy(_value(transition, "custom_parallel_approval_policy"))
	semantic_input = {
		"action": _value(transition, "action") or "",
		"allow_self_approval": _value(transition, "allow_self_approval") or 0,
		"allowed": _value(transition, "allowed") or "",
		"condition": _value(transition, "condition") or "",
		"minimum_approvals": _value(transition, "custom_minimum_approvals"),
		"next_state": _value(transition, "next_state") or "",
		"policy": policy,
		"state": _value(transition, "state") or "",
	}
	return {
		**semantic_input,
		"auto_complete_unchanged": bool(
			_value(transition, "custom_auto_complete_unchanged")
		),
		"comment_is_required": bool(_value(transition, "custom_comment_is_required")),
		"send_email_to_creator": bool(
			_value(transition, "send_email_to_creator")
		),
		"email_template": _value(transition, "custom_email_template"),
		"attach_document_pdf": bool(
			_value(transition, "custom_attach_document_pdf")
		),
		"idx": int(_value(transition, "idx") or 0),
		"reset_on_change": bool(_value(transition, "custom_reset_on_change")),
		"transition_semantic_hash": transition_semantic_hash(semantic_input),
		"transition_uuid": str(_value(transition, "custom_transition_uuid") or ""),
	}


def _workflow_context(doc: object) -> tuple[str, object, str, str] | None:
	workflow_name = get_workflow_name(_value(doc, "doctype"))
	if not workflow_name:
		return None
	workflow = get_workflow(_value(doc, "doctype"))
	state_field = workflow.workflow_state_field
	return workflow_name, workflow, state_field, str(_value(doc, state_field) or "")


def _fingerprint_exclusions(doctype: str) -> set[str]:
	exclusions: set[str] = set()
	for hook in frappe.get_hooks("workflow_approval_fingerprint_excluded_fields") or []:
		if isinstance(hook, dict):
			exclusions.update(hook.get(doctype, []) or [])
	return exclusions


def get_content_fingerprint(doc: object, workflow: object) -> ContentFingerprint:
	state_field = _value(workflow, "workflow_state_field")
	state = _value(doc, state_field) if state_field else None
	update_field = next(
		(
			_value(row, "update_field")
			for row in (_value(workflow, "states", []) or [])
			if _value(row, "state") == state and _value(row, "update_field")
		),
		None,
	)
	return fingerprint_document(
		doc,
		list(_value(_value(doc, "meta"), "fields", []) or []),
		workflow_state_field=state_field,
		workflow_update_field=update_field,
		excluded_fields=_fingerprint_exclusions(str(_value(doc, "doctype") or "")),
	)


def _eligible_approvers(doc: object, transition: object) -> list[str]:
	role = str(_value(transition, "allowed") or "")
	users = get_users_with_role(role)
	eligible = []
	for user in sorted(set(users)):
		previous_user = frappe.session.user
		try:
			if previous_user != user:
				frappe.set_user(user)
			if not has_approval_access(user, doc, transition):
				continue
			if not is_transition_condition_satisfied(transition, doc):
				continue
			if not _has_source_read_permission(doc, user):
				continue
			eligible.append(user)
		finally:
			if previous_user != user:
				frappe.set_user(previous_user)
	return eligible


def _has_source_read_permission(doc: object, user: str) -> bool:
	"""Evaluate even third-party permission hooks that consult the session user."""
	previous_user = frappe.session.user
	try:
		if previous_user != user:
			frappe.set_user(user)
		try:
			return bool(
				frappe.has_permission(
					_value(doc, "doctype"),
					ptype="read",
					doc=_value(doc, "name"),
					user=user,
					throw=False,
				)
			)
		except frappe.PermissionError:
			return False
	finally:
		if previous_user != user:
			frappe.set_user(previous_user)


def _current_transitions(doc: object, workflow: object, state: str) -> list[dict[str, Any]]:
	rows = []
	for transition in workflow.transitions:
		if _value(transition, "state") != state:
			continue
		row = _transition_dict(transition)
		row["eligible_approvers"] = _eligible_approvers(doc, transition)
		rows.append(row)
	return rows


def _configured_transition_hashes(workflow: object, state: str) -> dict[str, str]:
	"""Read configuration identity without recomputing snapshot eligibility/conditions."""
	return {
		str(_value(transition, "custom_transition_uuid")): _transition_dict(transition)[
			"transition_semantic_hash"
		]
		for transition in _value(workflow, "transitions", [])
		if _value(transition, "state") == state
		and _value(transition, "custom_transition_uuid")
	}


def _source_snapshot(doc: object) -> dict[str, Any]:
	meta = _value(doc, "meta")
	title_field = _value(meta, "title_field")
	return {
		"source_created_at": _value(doc, "creation"),
		"source_owner": _value(doc, "owner"),
		"source_title": _value(doc, title_field) if title_field else _value(doc, "name"),
	}


def _active_task_names(doctype: str, name: str) -> list[str]:
	return frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"round_status": ("in", ACTIVE_ROUND_STATUSES),
		},
		pluck="name",
		order_by="creation asc, name asc",
	)


def _round_task_names(round_id: str) -> list[str]:
	return frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id},
		pluck="name",
		order_by="name asc",
	)


def _parse_manifest(task: object) -> dict[str, Any]:
	value = _value(task, "round_manifest")
	if isinstance(value, dict):
		return value
	try:
		return json.loads(value or "{}")
	except (TypeError, ValueError):
		raise WorkflowApprovalConflictError(_("Workflow approval round manifest is invalid"))


def _set_task_values(task_name: str, values: dict[str, Any]) -> None:
	frappe.db.set_value("Workflow Task", task_name, values, update_modified=False)


def _lock_domain_dependencies(doctype: str, name: str) -> list[object]:
	"""Lock producer-owned aggregate roots before the approval source row."""
	dependencies: set[tuple[str, str]] = set()
	for adapter_path in frappe.get_hooks("workflow_approval_lock_dependencies") or []:
		for dependency in frappe.get_attr(adapter_path)(doctype, name) or []:
			if len(dependency) == 2 and all(dependency):
				dependencies.add((str(dependency[0]), str(dependency[1])))
	return [
		frappe.get_doc(dependency_doctype, dependency_name, for_update=True)
		for dependency_doctype, dependency_name in sorted(dependencies)
	]


def _set_round_values(round_id: str, values: dict[str, Any]) -> None:
	for task_name in _round_task_names(round_id):
		_set_task_values(task_name, values)


def _cancel_round(round_id: str, reason: str, *, round_status: str = "Cancelled") -> None:
	cancelled_at = now_datetime()
	for task_name in _round_task_names(round_id):
		status = frappe.db.get_value("Workflow Task", task_name, "status")
		values: dict[str, Any] = {"round_status": round_status}
		if status == "Working":
			values.update(
				{
					"status": "Cancelled",
					"cancelled_at": cancelled_at,
					"cancellation_reason": reason,
				}
			)
		_set_task_values(task_name, values)
	from dinext_common.workflow_approval.projections import close_round_projections

	close_round_projections(round_id)


def _mark_conflicted(round_id: str, reason: str) -> None:
	_set_round_values(
		round_id,
		{
			"round_status": "Conflicted",
			"failure_metadata": serialize_manifest({"reason": reason}),
		},
	)
	from dinext_common.workflow_approval.projections import close_round_projections

	close_round_projections(round_id)


def _notify_stalled_monitors(source: object, task: object) -> None:
	roles = frappe.get_all(
		"Has Role",
		filters={
			"parent": task.workflow,
			"parenttype": "Workflow",
			"parentfield": "custom_approval_monitor_roles",
		},
		pluck="role",
	)
	users = set(
		frappe.get_all(
			"Has Role",
			filters={
				"parenttype": "User",
				"parentfield": "roles",
				"role": ("in", sorted(set([*roles, "System Manager"]))),
			},
			pluck="parent",
			distinct=True,
		)
	)
	users.add("Administrator")
	subject = _("Workflow approval is stalled for {0}").format(
		task.source_title
	)
	for user in sorted(users):
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		if not frappe.has_permission(
			source.doctype,
			ptype="read",
			doc=source.name,
			user=user,
			throw=False,
		):
			continue
		if frappe.db.exists(
			"Notification Log",
			{
				"for_user": user,
				"document_type": source.doctype,
				"document_name": source.name,
				"email_content": task.approval_round_id,
			},
		):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"from_user": frappe.session.user,
				"subject": subject,
				"type": "Alert",
				"document_type": source.doctype,
				"document_name": source.name,
				"email_content": task.approval_round_id,
			}
		).insert(ignore_permissions=True)


def _insert_round_tasks(
	doc: object,
	workflow_name: str,
	state: str,
	manifest: dict[str, Any],
	task_transitions: dict[str, list[dict[str, Any]]],
	fingerprint: ContentFingerprint,
	*,
	round_id: str | None = None,
	approvers: set[str] | None = None,
	source_snapshot: dict[str, Any] | None = None,
) -> tuple[str, list[object]]:
	round_id = round_id or frappe.generate_hash(length=40)
	manifest_json = serialize_manifest(manifest)
	snapshot = source_snapshot or _source_snapshot(doc)
	tasks = []
	from dinext_common.workflow_approval.policy import make_task_name

	for approver, transitions in sorted(task_transitions.items()):
		if approvers is not None and approver not in approvers:
			continue
		task = frappe.get_doc(
			{
				"doctype": "Workflow Task",
				"name": make_task_name(round_id, approver),
				"doc": _value(doc, "doctype"),
				"wt_docname": _value(doc, "name"),
				"reference_doctype": _value(doc, "doctype"),
				"reference_name": _value(doc, "name"),
				"status": "Working",
				"round_status": "Open",
				"finalization_status": "Not Required",
				"workflow": workflow_name,
				"workflow_state": state,
				"state": state,
				"approval_round_id": round_id,
				"approver": approver,
				"user": approver,
				"entry_fingerprint": fingerprint.digest,
				"entry_fingerprint_version": fingerprint.version,
				"round_manifest": manifest_json,
				**snapshot,
			}
		)
		for transition in transitions:
			task.append(
				"available_workflow_transitions",
				{
					"state": transition["state"],
					"action": transition["action"],
					"next_state": transition["next_state"],
					"transition_uuid": transition["transition_uuid"],
					"transition_semantic_hash": transition["transition_semantic_hash"],
					"transition_idx": transition["idx"],
					"allowed_role": transition["allowed"],
					"policy": transition["policy"],
					"threshold": transition["threshold"],
					"comment_is_required": transition["comment_is_required"],
					"send_email_to_creator": transition["send_email_to_creator"],
					"auto_complete_unchanged": transition["auto_complete_unchanged"],
					"email_template": transition["email_template"],
					"attach_document_pdf": transition["attach_document_pdf"],
					"eligible_approvers": json.dumps(
						transition["eligible_approvers"],
						ensure_ascii=False,
					),
				},
			)
		task.insert(ignore_permissions=True)
		tasks.append(task)
	return round_id, tasks


def _task_transitions_from_manifest(
	manifest: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
	task_transitions: dict[str, list[dict[str, Any]]] = {}
	for transition in manifest.get("transitions", []):
		for approver in transition.get("eligible_approvers", []):
			task_transitions.setdefault(str(approver), []).append(dict(transition))
	return task_transitions


def _repair_open_round_tasks(
	doc: object,
	active: object,
	manifest: dict[str, Any],
) -> list[object]:
	"""Restore deterministic missing tasks from one source-locked open manifest."""
	from dinext_common.workflow_approval.policy import make_task_name

	task_transitions = _task_transitions_from_manifest(manifest)
	existing_names = set(
		frappe.db.get_values(
			"Workflow Task",
			{"approval_round_id": active.approval_round_id},
			"name",
			order_by="name asc",
			for_update=True,
			pluck=True,
		)
	)
	missing_approvers = {
		approver
		for approver in task_transitions
		if make_task_name(active.approval_round_id, approver) not in existing_names
	}
	if not missing_approvers:
		return []
	fingerprint = ContentFingerprint(
		version=active.entry_fingerprint_version,
		digest=active.entry_fingerprint,
		canonical_json="",
	)
	_round_id, repaired = _insert_round_tasks(
		doc,
		active.workflow,
		active.workflow_state,
		manifest,
		task_transitions,
		fingerprint,
		round_id=active.approval_round_id,
		approvers=missing_approvers,
		source_snapshot={
			"source_created_at": active.source_created_at,
			"source_owner": active.source_owner,
			"source_title": active.source_title,
		},
	)
	from dinext_common.workflow_approval.projections import create_round_projections

	create_round_projections(doc, repaired)
	return repaired


def _add_stalled_diagnostic(doc: object, message: str) -> None:
	doc.add_comment("Workflow", message)
	frappe.log_error(
		message=message,
		title=f"Workflow approval stalled: {_value(doc, 'doctype')} {_value(doc, 'name')}",
		reference_doctype=_value(doc, "doctype"),
		reference_name=_value(doc, "name"),
	)


def reconcile_source(
	doc: object,
	*,
	cycle_guard: AutomationCycleGuard | None = None,
) -> list[str]:
	"""Create or reconcile the immutable active round for a source document."""
	if _value(doc, "is_new", lambda: False)():
		return []
	doctype = str(_value(doc, "doctype") or "")
	name = str(_value(doc, "name") or "")
	if not doctype or not name:
		return []
	_lock_domain_dependencies(doctype, name)
	doc = frappe.get_doc(doctype, name, for_update=True)
	context = _workflow_context(doc)
	if not context:
		return []
	workflow_name, workflow, _state_field, state = context
	fingerprint = get_content_fingerprint(doc, workflow)
	active_names = _active_task_names(_value(doc, "doctype"), _value(doc, "name"))
	if active_names:
		active = frappe.get_doc("Workflow Task", active_names[0])
		round_id = active.approval_round_id
		if active.round_status == "Finalizing":
			return active_names
		if active.workflow_state != state:
			_cancel_round(round_id, _("Source workflow state changed"))
		else:
			active_manifest = _parse_manifest(active)
			current_hashes = _configured_transition_hashes(workflow, state)
			if not manifest_matches_configuration(active_manifest, current_hashes):
				_mark_conflicted(round_id, _("Workflow transition configuration changed"))
				return active_names
			if active.entry_fingerprint != fingerprint.digest and any(
				row.get("reset_on_change")
				for row in active_manifest.get("transitions", [])
			):
				_cancel_round(round_id, _("Source content changed"))
			else:
				if active.round_status == "Open":
					_repair_open_round_tasks(doc, active, active_manifest)
				return _round_task_names(round_id)

	current_rows = _current_transitions(doc, workflow, state)
	if not current_rows:
		return []
	try:
		manifest, task_transitions = build_round_manifest(current_rows)
	except ZeroEligibleApproversError:
		raise WorkflowApprovalConflictError(
			_("Workflow transition has no eligible approvers")
		)

	round_id, tasks = _insert_round_tasks(
		doc,
		workflow_name,
		state,
		manifest,
		task_transitions,
		fingerprint,
	)
	winner = _apply_automatic_votes(doc, tasks, manifest, fingerprint)
	from dinext_common.workflow_approval.projections import create_round_projections

	if not winner:
		create_round_projections(
			doc,
			[
				frappe.get_doc("Workflow Task", task.name)
				for task in tasks
				if frappe.db.get_value("Workflow Task", task.name, "status") == "Working"
			],
		)
	if winner:
		guard = cycle_guard or AutomationCycleGuard()
		guard.visit(workflow_name, state, fingerprint.digest)
		_finalize_round(doc, round_id, winner, cycle_guard=guard)
	return _round_task_names(round_id)


def _latest_reuse_for_transition(
	task: object,
	transition: object,
	fingerprint: ContentFingerprint,
) -> object | None:
	if not bool(_value(transition, "auto_complete_unchanged")):
		return None
	rows = frappe.get_all(
		"Workflow Task",
		filters={
			"status": "Completed",
			"approver": task.approver,
			"reference_doctype": task.reference_doctype,
			"reference_name": task.reference_name,
			"workflow": task.workflow,
			"transition_uuid": _value(transition, "transition_uuid"),
			"transition_semantic_hash": _value(transition, "transition_semantic_hash"),
		},
		fields=[
			"name",
			"status",
			"approver",
			"reference_doctype",
			"reference_name",
			"source_created_at",
			"workflow",
			"transition_uuid",
			"transition_semantic_hash",
			"content_fingerprint",
			"content_fingerprint_version",
			"completed_at",
		],
	)
	return find_latest_reusable_task(
		rows,
		approver=task.approver,
		reference_doctype=task.reference_doctype,
		reference_name=task.reference_name,
		source_created_at=task.source_created_at,
		workflow=task.workflow,
		transition_uuid=_value(transition, "transition_uuid"),
		transition_semantic_hash=_value(transition, "transition_semantic_hash"),
		content_fingerprint=fingerprint.digest,
		content_fingerprint_version=fingerprint.version,
	)


def _apply_automatic_votes(
	doc: object,
	tasks: list[object],
	manifest: dict[str, Any],
	fingerprint: ContentFingerprint,
) -> dict[str, Any] | None:
	reused_times: dict[str, list[str]] = {}
	for task in tasks:
		candidates = []
		for transition in task.available_workflow_transitions:
			reused = _latest_reuse_for_transition(task, transition, fingerprint)
			if reused:
				candidates.append((str(_value(reused, "completed_at") or ""), transition, reused))
		if not candidates:
			continue
		_completed_at, transition, reused = max(
			candidates,
			key=lambda item: (
				item[0],
				-int(_value(item[1], "transition_idx") or 0),
				_inverse_text(str(_value(item[1], "transition_uuid") or "")),
			),
		)
		complete_task(
			task,
			transition,
			comment="",
			completion_source="Automatic Unchanged",
			content_fingerprint=fingerprint,
			reused_from=str(_value(reused, "name")),
		)
		task.reload()
		_dispatch_vote_completed(task, doc, transition)
		doc.add_comment(
			"Workflow",
			_("{0} automatically reused action {1}").format(
				frappe.bold(task.approver),
				frappe.bold(transition.action),
			),
		)
		reused_times.setdefault(str(_value(transition, "transition_uuid")), []).append(
			str(_value(reused, "completed_at") or "")
		)

	rows = _round_vote_counts(tasks[0].approval_round_id, manifest) if tasks else []
	for row in rows:
		row["latest_reused_completed_at"] = max(
			reused_times.get(row["transition_uuid"], [""])
		)
	return select_automatic_winner(rows)


def _round_vote_counts(round_id: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
	completed = frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id, "status": "Completed"},
		fields=["transition_uuid", "completed_at"],
	)
	working_names = frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id, "status": "Working"},
		pluck="name",
	)
	remaining = (
		frappe.get_all(
			"Available Workflow Transitions",
			filters={"parent": ("in", working_names)},
			pluck="transition_uuid",
		)
		if working_names
		else []
	)
	return [
		{
			**transition,
			"votes": sum(
				1 for task in completed if task.transition_uuid == transition["transition_uuid"]
			),
			"remaining": remaining.count(transition["transition_uuid"]),
		}
		for transition in manifest.get("transitions", [])
	]


def _task_transition(task: object, transition_uuid: str | None, action: str | None) -> object:
	candidates = [
		row
		for row in task.available_workflow_transitions
		if (transition_uuid and row.transition_uuid == transition_uuid)
		or (not transition_uuid and action and row.action == action)
	]
	if len(candidates) != 1:
		raise WorkflowApprovalConflictError(_("Workflow action is not available for this task"))
	return candidates[0]


def complete_task(
	task: object,
	transition: object,
	*,
	comment: str,
	completion_source: str,
	content_fingerprint: ContentFingerprint,
	request_id: str | None = None,
	reused_from: str | None = None,
) -> None:
	_set_task_values(
		task.name,
		{
			"status": "Completed",
			"action": _value(transition, "action"),
			"next_state": _value(transition, "next_state"),
			"transition_uuid": _value(transition, "transition_uuid"),
			"transition_semantic_hash": _value(transition, "transition_semantic_hash"),
			"policy": _value(transition, "policy"),
			"threshold": _value(transition, "threshold"),
			"vote_comment": comment,
			"completed_at": now_datetime(),
			"completion_source": completion_source,
			"reused_from_workflow_task": reused_from,
			"content_fingerprint": content_fingerprint.digest,
			"content_fingerprint_version": content_fingerprint.version,
			"correlation_id": request_id,
		},
	)


def _dispatch_vote_completed(task: object, source: object, transition: object) -> None:
	for adapter_path in frappe.get_hooks("workflow_approval_vote_completed") or []:
		frappe.get_attr(adapter_path)(task, source, transition)


def cast_vote(
	task_name: str,
	*,
	transition_uuid: str | None = None,
	action: str | None = None,
	comment: object = None,
	request_id: str | None = None,
	completion_source: str = "Manual",
) -> VoteResult:
	"""Lock source then task, revalidate, record one vote, and finalize if reached."""
	pointer = frappe.db.get_value(
		"Workflow Task",
		task_name,
		["reference_doctype", "reference_name"],
		as_dict=True,
	)
	if not pointer:
		raise frappe.DoesNotExistError(_("Workflow Task does not exist"))
	_lock_domain_dependencies(pointer.reference_doctype, pointer.reference_name)
	source = frappe.get_doc(
		pointer.reference_doctype,
		pointer.reference_name,
		for_update=True,
	)
	task = frappe.get_doc("Workflow Task", task_name, for_update=True)
	task.check_permission("read")

	if task.approver != frappe.session.user and frappe.session.user != "Administrator":
		raise frappe.PermissionError(_("Only the snapshotted approver can complete this task"))
	if not frappe.db.get_value("User", task.approver, "enabled"):
		raise frappe.PermissionError(_("The snapshotted approver is disabled"))
	if task.status == "Completed" and request_id and task.correlation_id == request_id:
		return _vote_result(task, source, transitioned=task.round_status == "Transitioned")
	if task.status != "Working" or task.round_status != "Open":
		raise WorkflowApprovalConflictError(_("Workflow Task is no longer active"))

	context = _workflow_context(source)
	if not context:
		raise WorkflowApprovalConflictError(_("The source document has no active Workflow"))
	workflow_name, workflow, _state_field, state = context
	if workflow_name != task.workflow or state != task.workflow_state:
		raise WorkflowApprovalConflictError(_("The source workflow state has changed"))

	manifest = _parse_manifest(task)
	current_hashes = _configured_transition_hashes(workflow, state)
	if not manifest_matches_configuration(manifest, current_hashes):
		_mark_conflicted(task.approval_round_id, _("Workflow transition configuration changed"))
		raise WorkflowApprovalConflictError(_("Workflow transition configuration changed"))

	transition = _task_transition(task, transition_uuid, action)
	normalized_comment = normalize_comment(
		comment,
		required=bool(transition.comment_is_required),
	)
	fingerprint = get_content_fingerprint(source, workflow)
	complete_task(
		task,
		transition,
		comment=normalized_comment,
		completion_source=completion_source,
		content_fingerprint=fingerprint,
		request_id=request_id,
	)
	task.reload()
	_dispatch_vote_completed(task, source, transition)
	source.add_comment(
		"Workflow",
		_("{0} voted {1}{2}").format(
			frappe.bold(frappe.utils.escape_html(task.approver)),
			frappe.bold(frappe.utils.escape_html(transition.action)),
			(
				f": {frappe.utils.escape_html(normalized_comment)}"
				if normalized_comment
				else ""
			),
		),
	)
	from dinext_common.workflow_approval.projections import close_task_projection

	close_task_projection(task)

	counts = _round_vote_counts(task.approval_round_id, manifest)
	reached = [row for row in counts if row["votes"] >= row["threshold"]]
	winner = (
		min(reached, key=lambda row: (int(row["idx"]), row["transition_uuid"]))
		if reached
		else None
	)
	transitioned = False
	if winner:
		transitioned = _finalize_round(source, task.approval_round_id, winner)
	elif counts and not any(
		is_threshold_reachable(
			threshold=int(row["threshold"]),
			votes=int(row["votes"]),
			remaining=int(row["remaining"]),
		)
		for row in counts
	):
		_set_round_values(task.approval_round_id, {"round_status": "Stalled"})
		_notify_stalled_monitors(source, task)
		from dinext_common.workflow_approval.projections import close_round_projections

		close_round_projections(task.approval_round_id)
		source.add_comment(
			"Workflow",
			_("Workflow approval is stalled because no action can reach its threshold."),
		)
	refreshed_task = frappe.get_doc("Workflow Task", task.name)
	refreshed_source = frappe.get_doc(source.doctype, source.name)
	return _vote_result(refreshed_task, refreshed_source, transitioned=transitioned)


def _vote_result(task: object, source: object, *, transitioned: bool) -> VoteResult:
	context = _workflow_context(source)
	return {
		"task": task.name,
		"status": task.status,
		"round_status": task.round_status,
		"transitioned": transitioned,
		"reference_doctype": task.reference_doctype,
		"reference_name": task.reference_name,
		"workflow_state": context[3] if context else None,
	}


def _finalization_actor(round_id: str, winner: dict[str, Any]) -> str:
	actors = frappe.get_all(
		"Workflow Task",
		filters={
			"approval_round_id": round_id,
			"status": "Completed",
			"transition_uuid": winner["transition_uuid"],
		},
		pluck="approver",
		order_by="completed_at desc, name asc",
	)
	if not actors:
		raise WorkflowApprovalConflictError(_("Reached transition has no completed approver"))
	return actors[0]


def _ensure_finalization_placeholder(
	source: object,
	round_id: str,
	winner: dict[str, Any],
	actor: str,
) -> None:
	"""Suppress core role-wide actions/email until individualized next-round projection."""
	if frappe.db.exists(
		"Workflow Action",
		{
			"reference_doctype": source.doctype,
			"reference_name": source.name,
			"workflow_state": winner["next_state"],
			"custom_approval_round_id": round_id,
			"custom_workflow_task": ("is", "not set"),
		},
	):
		return
	frappe.get_doc(
		{
			"doctype": "Workflow Action",
			"reference_doctype": source.doctype,
			"reference_name": source.name,
			"workflow_state": winner["next_state"],
			"status": "Completed",
			"user": actor,
			"completed_by": actor,
			"custom_approval_round_id": round_id,
			"custom_notification_status": "Skipped",
		}
	).insert(ignore_permissions=True)


def _finalize_round(
	source: object,
	round_id: str,
	winner: dict[str, Any],
	*,
	cycle_guard: AutomationCycleGuard | None = None,
) -> bool:
	actor = _finalization_actor(round_id, winner)
	_set_round_values(
		round_id,
		{
			"round_status": "Finalizing",
			"finalization_status": "Queued",
		},
	)
	savepoint = f"workflow_finalize_{frappe.generate_hash(length=12)}"
	frappe.db.savepoint(savepoint)
	callback_managers = (
		frappe.db.before_commit,
		frappe.db.after_commit,
		frappe.db.before_rollback,
		frappe.db.after_rollback,
	)
	callback_snapshots = {
		manager: list(manager._functions) for manager in callback_managers
	}
	previous_user = frappe.session.user
	previous_flag = getattr(frappe.flags, "in_dinext_workflow_finalization", False)
	try:
		_ensure_finalization_placeholder(source, round_id, winner, actor)
		frappe.flags.in_dinext_workflow_finalization = True
		if actor != previous_user:
			frappe.set_user(actor)
		core_apply_workflow(source, winner["action"])
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.db.release_savepoint(savepoint)
		for manager, callbacks in callback_snapshots.items():
			manager._functions.clear()
			manager._functions.extend(callbacks)
		_mark_conflicted(
			round_id,
			_("Workflow core validation rejected the winning transition"),
		)
		_set_round_values(round_id, {"finalization_status": "Failed"})
		source.add_comment(
			"Workflow",
			_("Workflow finalization failed and requires a manager rebuild."),
		)
		frappe.log_error(
			title=f"Workflow approval finalization failed: {round_id}",
			reference_doctype=source.doctype,
			reference_name=source.name,
		)
		return False
	finally:
		if actor != previous_user:
			frappe.set_user(previous_user)
		frappe.flags.in_dinext_workflow_finalization = previous_flag
	frappe.db.release_savepoint(savepoint)

	refreshed = frappe.get_doc(source.doctype, source.name)
	context = _workflow_context(refreshed)
	if context and context[3] == winner["next_state"]:
		_finish_round(round_id, winner)
		reconcile_source(refreshed, cycle_guard=cycle_guard)
		return True

	submission_queue = frappe.db.get_value(
		"Submission Queue",
		{
			"ref_doctype": source.doctype,
			"ref_docname": source.name,
			"status": "Queued",
		},
		"name",
		order_by="creation desc",
	)
	if not submission_queue:
		_mark_conflicted(
			round_id,
			_("Workflow core did not create the expected Submission Queue"),
		)
		_set_round_values(round_id, {"finalization_status": "Failed"})
		return False
	_set_round_values(round_id, {"submission_queue": submission_queue})
	return False


def _finish_round(round_id: str, winner: dict[str, Any]) -> None:
	now = now_datetime()
	for task_name in _round_task_names(round_id):
		status = frappe.db.get_value("Workflow Task", task_name, "status")
		values: dict[str, Any] = {
			"round_status": "Transitioned",
			"finalization_status": "Finished",
		}
		if status == "Working":
			values.update(
				{
					"status": "Cancelled",
					"cancelled_at": now,
					"cancellation_reason": _("Another transition reached its threshold"),
				}
			)
		_set_task_values(task_name, values)
	from dinext_common.workflow_approval.projections import close_round_projections

	close_round_projections(round_id)
	frappe.db.delete(
		"Workflow Action",
		{
			"custom_approval_round_id": round_id,
			"custom_workflow_task": ("is", "not set"),
		},
	)


def validate_source_change(doc: object) -> None:
	"""Block direct workflow-state mutations outside a finalizing round."""
	if getattr(frappe.flags, "in_dinext_workflow_finalization", False):
		return
	context = _workflow_context(doc)
	if not context:
		return
	_workflow_name, _workflow, state_field, next_state = context
	before = _value(doc, "_doc_before_save")
	if not before:
		return
	current_state = _value(before, state_field)
	if current_state == next_state:
		return
	finalizing = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": _value(doc, "doctype"),
			"reference_name": _value(doc, "name"),
			"round_status": "Finalizing",
			"next_state": next_state,
		},
		fields=["submission_queue"],
		limit=2,
	)
	if finalizing:
		from rq import get_current_job

		job = get_current_job()
		if job and any(
			row.submission_queue
			and frappe.db.get_value(
				"Submission Queue",
				row.submission_queue,
				"job_id",
			)
			== job.id
			for row in finalizing
		):
			return
	frappe.throw(
		_("Workflow state can only be changed through an active Workflow Task"),
		WorkflowApprovalConflictError,
	)


def archive_source(doc: object) -> None:
	"""Keep task history while severing links and cancelling active work."""
	task_names = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": _value(doc, "doctype"),
			"reference_name": _value(doc, "name"),
		},
		pluck="name",
	)
	deleted_at = now_datetime()
	rounds = set()
	for task_name in task_names:
		task = frappe.get_doc("Workflow Task", task_name)
		rounds.add(task.approval_round_id)
		values: dict[str, Any] = {"source_deleted_at": deleted_at}
		if task.status == "Working":
			values.update(
				{
					"status": "Cancelled",
					"round_status": "Cancelled",
					"cancelled_at": deleted_at,
					"cancellation_reason": _("Source document deleted"),
				}
			)
		_set_task_values(task_name, values)
	from dinext_common.workflow_approval.projections import close_round_projections

	for round_id in filter(None, rounds):
		close_round_projections(round_id)


def apply_domain_transition(
	doctype: str,
	name: str,
	next_state: str,
	*,
	reason: str,
	actor: str | None = None,
) -> object:
	"""Apply one trusted producer cascade through a real configured transition."""
	_lock_domain_dependencies(doctype, name)
	source = frappe.get_doc(doctype, name, for_update=True)
	context = _workflow_context(source)
	if not context:
		raise WorkflowApprovalConflictError(_("The source document has no active Workflow"))
	_workflow_name, workflow, _state_field, state = context
	if state == next_state:
		return source
	matching = []
	candidates = []
	for transition in workflow.transitions:
		if (
			_value(transition, "state") != state
			or _value(transition, "next_state") != next_state
		):
			continue
		actors = _eligible_approvers(source, transition)
		matching.append((transition, actors))
		if actors and (not actor or actor in actors):
			candidates.append((transition, actors))
	if len(matching) == 1 and not matching[0][1]:
		raise WorkflowApprovalConflictError(_("Domain transition has no eligible actor"))
	if actor and not candidates and any(actors for _transition, actors in matching):
		raise frappe.PermissionError(_("The requested domain transition is not permitted"))
	if len(candidates) != 1:
		raise WorkflowApprovalConflictError(
			_("No unique configured domain transition from {0} to {1}").format(
				state,
				next_state,
			)
		)
	transition, actors = candidates[0]
	actor = actor or actors[0]
	active_rounds = {
		frappe.db.get_value("Workflow Task", task_name, "approval_round_id")
		for task_name in _active_task_names(doctype, name)
	}
	for active_round_id in filter(None, active_rounds):
		_cancel_round(active_round_id, reason)
	round_id = f"domain-{frappe.generate_hash(length=32)}"
	winner = {
		"action": transition.action,
		"next_state": transition.next_state,
	}
	_ensure_finalization_placeholder(source, round_id, winner, actor)
	previous_user = frappe.session.user
	previous_flag = getattr(frappe.flags, "in_dinext_workflow_finalization", False)
	try:
		frappe.flags.in_dinext_workflow_finalization = True
		frappe.set_user(actor)
		core_apply_workflow(source, transition.action)
	finally:
		frappe.set_user(previous_user)
		frappe.flags.in_dinext_workflow_finalization = previous_flag
		frappe.db.delete(
			"Workflow Action",
			{
				"custom_approval_round_id": round_id,
				"custom_workflow_task": ("is", "not set"),
			},
		)
	refreshed = frappe.get_doc(doctype, name)
	refreshed.add_comment("Workflow", reason)
	reconcile_source(refreshed)
	return refreshed
