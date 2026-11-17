"""Atomic task-based approval engine for standard Frappe Workflows."""

from __future__ import annotations

import json
from collections import defaultdict
from contextlib import contextmanager, nullcontext, suppress
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal, NotRequired, TypedDict

import frappe
from frappe import _
from frappe.model.workflow import (
	apply_workflow as core_apply_workflow,
)
from frappe.model.workflow import (
	get_workflow,
	get_workflow_name,
	has_approval_access,
	is_transition_condition_satisfied,
)
from frappe.utils import get_datetime, now_datetime
from frappe.utils.user import get_users_with_role

from dinext_common.workflow_approval import request_receipts
from dinext_common.workflow_approval.fingerprint import (
	ContentFingerprint,
	fingerprint_document,
)
from dinext_common.workflow_approval.policy import (
	ZeroEligibleApproversError,
	classify_round_configuration,
	configuration_change_metadata,
	is_threshold_reachable,
	make_task_name,
	normalize_policy,
	required_approvals,
	transition_semantic_hash,
)
from dinext_common.workflow_approval.validation import normalize_comment

ACTIVE_ROUND_STATUSES = ("Open", "Stalled", "Finalizing", "Conflicted")
MAX_AUTOMATIC_TRANSITIONS = 20
CONFIGURATION_WITHDRAWAL_REASON = "Workflow transition configuration changed"


class WorkflowApprovalError(frappe.ValidationError):
	"""Base exception for approval contract failures."""


class WorkflowApprovalConflictError(WorkflowApprovalError):
	"""Raised when a vote no longer matches current source or workflow state."""


class WorkflowSourceChangedError(WorkflowApprovalConflictError):
	"""The user confirmed an older revision of the document."""


class WorkflowTemporarilyUnavailableError(WorkflowApprovalError):
	http_status_code = 503


class ExpiredWorkflowActionError(WorkflowApprovalConflictError):
	"""The signed confirmation no longer matches the current task projection."""


class MissingApproverTransition(TypedDict):
	transition_uuid: str
	action: str
	next_state: str
	role: str


class WorkflowRoundError(TypedDict):
	code: Literal["no_eligible_approvers"]
	doctype: str
	name: str
	workflow: str
	state: str
	transitions: list[MissingApproverTransition]


def round_error_message(details: WorkflowRoundError) -> str:
	transitions = ", ".join(
		_("{0} → {1} (role {2})", context="Workflow").format(
			_(row["action"], context="Workflow"), _(row["next_state"]), _(row["role"]),
		)
		for row in details["transitions"]
	)
	return _(
		"Could not open an approval round for {0} {1} in Workflow {2} at {3}. "
		"No eligible approvers for {4}."
	).format(
		_(details["doctype"]), details["name"], details["workflow"], _(details["state"]), transitions,
	)


class NoEligibleApproversError(WorkflowApprovalConflictError):
	"""The configured round has outgoing transitions without eligible users."""

	def __init__(self, details: WorkflowRoundError):
		self.details = details
		super().__init__(round_error_message(details))


class AutomationCycleError(WorkflowApprovalError):
	"""Raised when automatic approvals repeat a state or exceed their bound."""


class VoteResult(TypedDict):
	pending_submission: NotRequired[str]
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
	visited: set[tuple[str, str, str, str]] = field(default_factory=set)
	transition_count: int = 0

	def permits(self, workflow: str, state: str, content_fingerprint: str, process_id: str = "") -> bool:
		return (process_id, workflow, state, content_fingerprint) not in self.visited and self.transition_count < self.max_transitions

	def visit(self, workflow: str, state: str, content_fingerprint: str, process_id: str = "") -> None:
		key = (process_id, workflow, state, content_fingerprint)
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


def _round_manifest_for(doc, workflow, state: str, transitions):
	ordered = sorted(transitions, key=lambda row: (int(row.get("idx") or 0), row.get("transition_uuid") or ""))
	missing: list[MissingApproverTransition] = [
		{
			"transition_uuid": row.get("transition_uuid") or "",
			"action": row.get("action") or "",
			"next_state": row.get("next_state") or "",
			"role": row.get("allowed") or "",
		}
		for row in ordered
		if not row.get("eligible_approvers")
	]
	if missing:
		raise NoEligibleApproversError({
			"code": "no_eligible_approvers",
			"doctype": doc.doctype,
			"name": doc.name,
			"workflow": workflow.name,
			"state": state,
			"transitions": missing,
		})
	return build_round_manifest(ordered)


def manifest_matches_configuration(
	manifest: dict[str, Any],
	current_hashes: dict[str, str],
) -> bool:
	"""Match snapshot rows to configuration by semantic hash and UUID.

	An empty UUID on either side still matches the same semantic hash. A
	non-empty UUID must be the same value, so a replaced identifier stays
	fail-closed.
	"""
	snapshot = [
		(str(row.get("transition_uuid") or ""), str(row.get("transition_semantic_hash") or ""))
		for row in (manifest.get("transitions") or [])
	]
	configured = [
		(str(uuid or ""), str(semantic or ""))
		for uuid, semantic in current_hashes.items()
	]
	if len(snapshot) != len(configured):
		return False
	used: set[int] = set()
	for snap_uuid, snap_hash in snapshot:
		candidates = [
			index
			for index, (cfg_uuid, cfg_hash) in enumerate(configured)
			if index not in used
			and cfg_hash == snap_hash
			and (not snap_uuid or not cfg_uuid or snap_uuid == cfg_uuid)
		]
		exact = [
			index
			for index in candidates
			if snap_uuid and configured[index][0] == snap_uuid
		]
		if len(exact) == 1:
			found = exact[0]
		elif len(candidates) == 1:
			found = candidates[0]
		else:
			return False
		used.add(found)
	return True


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
	from dinext_common.workflow_approval.scenarios import service
	if service.is_ready():
		return service.workflow_context(doc)
	workflow_name = get_workflow_name(_value(doc, "doctype"))
	if not workflow_name:
		return None
	workflow = get_workflow(_value(doc, "doctype"))
	state_field = workflow.workflow_state_field
	return workflow_name, workflow, state_field, str(_value(doc, state_field) or "")


def _fingerprint_exclusions(doctype: str, workflow: object | None = None) -> set[str]:
	from dinext_common.workflow_approval.exclusions import configured_exclusions

	exclusions = configured_exclusions(workflow)
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
		excluded_fields=_fingerprint_exclusions(str(_value(doc, "doctype") or ""), workflow),
	)


def _eligible_approvers(doc: object, transition: object) -> list[str] | None:
	"""Return None when every eligible role member gets a false condition."""
	role = str(_value(transition, "allowed") or "")
	users = (
		frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"}, pluck="name")
		if role == "All"
		else get_users_with_role(role)
	)
	eligible = []
	evaluated = False
	evaluation_failed = False
	previous_user = frappe.session.user
	for user in sorted(set(users)):
		try:
			frappe.session.user = user
			if not has_approval_access(user, doc, transition) or not _has_source_read_permission(doc, user):
				continue
			try:
				satisfied = is_transition_condition_satisfied(transition, doc)
			except (frappe.db.InternalError, frappe.QueryDeadlockError, frappe.QueryTimeoutError):
				raise
			except Exception:
				evaluation_failed = True
				continue
			evaluated = True
			if satisfied:
				eligible.append(user)
		finally:
			frappe.session.user = previous_user
	if evaluation_failed:
		return []
	if evaluated and not eligible:
		return None
	return eligible


def _has_source_read_permission(doc: object, user: str) -> bool:
	"""Evaluate even third-party permission hooks that consult the session user."""
	previous_user = frappe.session.user
	try:
		if previous_user != user:
			frappe.session.user = user
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
			frappe.session.user = previous_user


def _current_transitions(doc: object, workflow: object, state: str) -> list[dict[str, Any]]:
	rows = []
	for transition in workflow.transitions:
		if _value(transition, "state") != state:
			continue
		approvers = _eligible_approvers(doc, transition)
		if approvers is not None:
			rows.append({**_transition_dict(transition), "eligible_approvers": approvers})
	return rows


def _configured_transition_hashes(workflow: object, state: str) -> dict[str, str]:
	"""Read configuration identity without recomputing snapshot eligibility/conditions."""
	return {
		str(_value(transition, "custom_transition_uuid") or ""): _transition_dict(transition)[
			"transition_semantic_hash"
		]
		for transition in _value(workflow, "transitions", [])
		if _value(transition, "state") == state
	}


def _source_snapshot(doc: object) -> dict[str, Any]:
	from dinext_common.workflow_approval.permissions import public_source_title_field

	meta = _value(doc, "meta")
	title_field = public_source_title_field(meta) if meta else None
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


def _round_task_names(round_id: str, *, for_update: bool = False) -> list[str]:
	return frappe.db.get_values(
		"Workflow Task",
		{"approval_round_id": round_id},
		"name",
		pluck=True,
		for_update=for_update,
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


class WorkflowDomainRollbackError(frappe.ValidationError):
	"""A domain validation requires rolling back the entire vote."""


def domain_handler(doctype: str, operation: str):
	paths = frappe.get_hooks("workflow_approval_domain_handlers", default={}).get(doctype, {}).get(operation)
	return frappe.get_attr(paths[-1]) if paths else None


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
	for task_name in _round_task_names(round_id, for_update=True):
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


def _mark_conflicted(
	round_id: str,
	reason: str,
	metadata: dict[str, Any] | None = None,
) -> None:
	_set_round_values(
		round_id,
		{
			"round_status": "Conflicted",
			"failure_metadata": serialize_manifest(metadata or {"reason": reason}),
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
	from dinext_common.workflow_approval.deadlines.lifecycle import prepare_task
	from dinext_common.workflow_approval.deadlines.lifecycle import snapshot as deadline_snapshot
	workflow_doc = frappe.get_doc("Workflow", workflow_name)
	from dinext_common.workflow_approval.scenarios import service
	scenario_process_id = service.get_context(doc)["process_id"] if service.is_ready() else None
	deadline_assignments = manifest.setdefault("deadline_assignments", {})
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
				"workflow_process": scenario_process_id,
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
		prepare_task(task, workflow_doc, inherited=deadline_assignments.get(approver))
		if task.deadline_assignment_id:
			deadline_assignments[approver] = deadline_snapshot(task)
		task.insert(ignore_permissions=True)
		tasks.append(task)
	if deadline_assignments:
		_set_round_values(round_id, {"round_manifest": serialize_manifest(manifest)})
		for task in tasks:
			task.round_manifest = serialize_manifest(manifest)
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
	existing = {
		row.name: row
		for row in frappe.db.get_values(
			"Workflow Task",
			{"approval_round_id": active.approval_round_id},
			["name", "status", "cancellation_reason"],
			order_by="name asc",
			for_update=True,
			as_dict=True,
		)
	}
	missing_approvers = set()
	for approver, transitions in task_transitions.items():
		task_name = make_task_name(active.approval_round_id, approver)
		task = existing.get(task_name)
		if task is None:
			missing_approvers.add(approver)
		elif task.status == "Cancelled" and active.round_status == "Open":
			_restore_withdrawn_task(task, transitions)
	from dinext_common.workflow_approval.projections import repair_round_projections

	repair_round_projections(doc, active.approval_round_id)
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


def _completed_vote_rows(round_id: str) -> list[dict[str, Any]]:
	return frappe.db.get_values(
		"Workflow Task",
		{"approval_round_id": round_id, "status": "Completed"},
		[
			"name",
			"approver",
			"action",
			"transition_uuid",
			"transition_semantic_hash",
			"vote_comment",
		],
		as_dict=True,
		for_update=True,
		order_by="name asc",
	)


def _classify_round(
	manifest: dict[str, Any],
	workflow: object,
	state: str,
	round_id: str,
) -> dict[str, list[dict[str, Any]]]:
	current = [
		_transition_dict(transition)
		for transition in _value(workflow, "transitions", [])
		if _value(transition, "state") == state
	]
	return classify_round_configuration(
		manifest.get("transitions") or [],
		current,
		_completed_vote_rows(round_id),
	)


def configuration_metadata(task: object) -> dict[str, Any] | None:
	"""Return the configuration-change breakdown stored on a conflicted round."""
	value = _value(task, "failure_metadata")
	if not value:
		return None
	try:
		parsed = json.loads(value) if isinstance(value, str) else dict(value)
	except (TypeError, ValueError):
		return None
	if not isinstance(parsed, dict) or parsed.get("reason") != "configuration_changed":
		return None
	return parsed


def preview_configuration_conflict(
	task: object,
	*,
	source: object | None = None,
) -> dict[str, Any] | None:
	"""Describe live drift before a failed request or source save persists it."""
	if _value(task, "round_status") != "Open":
		return None
	if source is None:
		try:
			source = frappe.get_doc(task.reference_doctype, task.reference_name)
		except frappe.DoesNotExistError:
			return None
	context = _workflow_context(source)
	if not context:
		return None
	workflow_name, workflow, _state_field, state = context
	if workflow_name != task.workflow or state != task.workflow_state:
		return None
	classification = _classify_round(_parse_manifest(task), workflow, state, task.approval_round_id)
	return configuration_change_metadata(classification) if classification["void"] else None


def _persist_round_configuration(round_id: str) -> None:
	"""Reconcile only the round after the rejected caller transaction rolls back."""
	# A separate connection keeps this commit from clearing the request's other
	# rollback callbacks or committing any of its rejected business changes.
	previous_db = frappe.local.db
	frappe.connect(set_admin_as_user=False)
	try:
		pointer = frappe.db.get_value(
			"Workflow Task",
			{"approval_round_id": round_id},
			["name", "reference_doctype", "reference_name"],
			as_dict=True,
		)
		if not pointer:
			return
		_lock_domain_dependencies(pointer.reference_doctype, pointer.reference_name)
		try:
			source = frappe.get_doc(pointer.reference_doctype, pointer.reference_name, for_update=True)
		except frappe.DoesNotExistError:
			return
		task = frappe.get_doc("Workflow Task", pointer.name, for_update=True)
		from dinext_common.workflow_approval.scenarios import service

		if service.is_ready() and not service.task_is_current(source, task):
			return
		context = _workflow_context(source)
		if not context or task.round_status != "Open":
			return
		workflow_name, workflow, _state_field, state = context
		if workflow_name != task.workflow or state != task.workflow_state:
			return
		classification = _classify_round(_parse_manifest(task), workflow, state, round_id)
		if classification["void"]:
			_mark_conflicted(round_id, _("Workflow transition configuration changed"),
				metadata=configuration_change_metadata(classification))
			frappe.db.commit()
		elif classification["dropped"] or classification["add"]:
			if _amend_open_round(source, task, workflow, state, classification) is not None:
				frappe.db.commit()
	finally:
		frappe.db.close()
		frappe.local.db = previous_db


def _replace_available_transitions(task_name: str, transitions: list[dict[str, Any]]) -> None:
	frappe.db.delete(
		"Available Workflow Transitions",
		{"parent": task_name, "parenttype": "Workflow Task"},
	)
	for transition in transitions:
		frappe.get_doc(
			{
				"doctype": "Available Workflow Transitions",
				"parent": task_name,
				"parenttype": "Workflow Task",
				"parentfield": "available_workflow_transitions",
				"idx": int(transition.get("idx") or 0),
				"state": transition.get("state") or "",
				"action": transition.get("action") or "",
				"next_state": transition.get("next_state") or "",
				"transition_uuid": transition.get("transition_uuid") or "",
				"transition_semantic_hash": transition.get("transition_semantic_hash") or "",
				"transition_idx": int(transition.get("idx") or 0),
				"allowed_role": transition.get("allowed") or "",
				"policy": transition.get("policy") or "",
				"threshold": transition.get("threshold") or 0,
				"comment_is_required": bool(transition.get("comment_is_required")),
				"send_email_to_creator": bool(transition.get("send_email_to_creator")),
				"auto_complete_unchanged": bool(transition.get("auto_complete_unchanged")),
				"email_template": transition.get("email_template"),
				"attach_document_pdf": bool(transition.get("attach_document_pdf")),
				"eligible_approvers": json.dumps(
					transition.get("eligible_approvers") or [],
					ensure_ascii=False,
				),
			}
		).insert(ignore_permissions=True)


def _retire_working_task(task_name: str) -> None:
	from dinext_common.workflow_approval.projections import close_task_projection, delivery_snapshot

	task = frappe.get_doc("Workflow Task", task_name)
	snapshot = delivery_snapshot(task) or {"legacy_unknown": True}
	snapshot["configuration_withdrawn"] = True
	_set_task_values(
		task_name,
		{
			"status": "Cancelled",
			"cancelled_at": now_datetime(),
			"cancellation_reason": _("Workflow transition configuration changed"),
			"notification_delivery_snapshot": serialize_manifest(snapshot),
		},
	)
	close_task_projection(task)


def _restore_withdrawn_task(row: object, transitions: list[dict[str, Any]]) -> None:
	from dinext_common.workflow_approval.projections import delivery_snapshot

	task = frappe.get_doc("Workflow Task", row.name)
	snapshot = delivery_snapshot(task)
	legacy_reasons = {
		CONFIGURATION_WITHDRAWAL_REASON,
		_("Workflow transition configuration changed"),
		_("Workflow transition configuration changed", lang="ru"),
	}
	if not snapshot.get("configuration_withdrawn") and row.cancellation_reason not in legacy_reasons:
		return
	if not snapshot:
		snapshot = {"legacy_unknown": True}
	snapshot.pop("configuration_withdrawn", None)
	snapshot["configuration_restored"] = True
	_replace_available_transitions(task.name, transitions)
	_set_task_values(task.name, {
		"status": "Working",
		"cancelled_at": None,
		"cancellation_reason": None,
		"notification_delivery_snapshot": serialize_manifest(snapshot),
	})


def _amend_open_round(
	doc: object,
	active: object,
	workflow: object,
	state: str,
	classification: dict[str, list[dict[str, Any]]],
) -> bool | None:
	"""Return whether the amended round finalized, or None if no amendment applies."""
	current_full = _current_transitions(doc, workflow, state)
	full_by_uuid = {str(row.get("transition_uuid") or ""): row for row in current_full}
	added: list[dict[str, Any]] = []
	for row in classification["add"]:
		uuid = str(row.get("transition_uuid") or "")
		full = full_by_uuid.get(uuid)
		if full is None and not uuid:
			snap_hash = str(row.get("transition_semantic_hash") or "")
			full = next(
				(
					item
					for item in current_full
					if str(item.get("transition_semantic_hash") or "") == snap_hash
				),
				None,
			)
		if full is not None:
			added.append(full)
	if not added and not classification["dropped"]:
		return None
	manifest, task_transitions = _round_manifest_for(doc, workflow, state, [*classification["keep"], *added])
	if entry := _parse_manifest(active).get("entry_context"):
		manifest["entry_context"] = entry
	if deadlines := _parse_manifest(active).get("deadline_assignments"):
		manifest["deadline_assignments"] = deadlines
	round_id = active.approval_round_id
	_set_round_values(round_id, {"round_manifest": serialize_manifest(manifest)})
	for task in frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id},
		fields=["name", "status", "approver"],
		order_by="name asc",
	):
		if task.status != "Working":
			continue
		desired = task_transitions.get(task.approver, [])
		if not desired:
			_retire_working_task(task.name)
			continue
		_replace_available_transitions(task.name, desired)
	_repair_open_round_tasks(doc, active, manifest)
	counts = _round_vote_counts(round_id, manifest, for_update=True)
	reached = [row for row in counts if int(row["votes"]) >= int(row["threshold"])]
	if not reached:
		return False
	winner = min(reached, key=lambda row: (int(row["idx"]), row["transition_uuid"]))
	return _finalize_round(doc, round_id, winner)


def _copy_carried_vote(
	doc: object,
	round_task: object,
	round_id: str,
	manifest: dict[str, Any],
	fingerprint: ContentFingerprint,
	vote: object,
	transition: dict[str, Any],
) -> None:
	approver = str(_value(vote, "approver") or "")
	task_name = make_task_name(round_id, approver)
	if not frappe.db.exists("Workflow Task", task_name):
		_insert_round_tasks(
			doc,
			_value(round_task, "workflow"),
			_value(round_task, "workflow_state"),
			manifest,
			{approver: [transition]},
			fingerprint,
			round_id=round_id,
			approvers={approver},
		)
	task = frappe.get_doc("Workflow Task", task_name)
	if task.status != "Working":
		return
	uuid = str(transition.get("transition_uuid") or "")
	if not any(row.transition_uuid == uuid for row in task.available_workflow_transitions):
		_replace_available_transitions(
			task.name,
			[
				*[
					{
						"state": row.state,
						"action": row.action,
						"next_state": row.next_state,
						"transition_uuid": row.transition_uuid,
						"transition_semantic_hash": row.transition_semantic_hash,
						"idx": row.transition_idx,
						"allowed": row.allowed_role,
						"policy": row.policy,
						"threshold": row.threshold,
						"comment_is_required": row.comment_is_required,
						"send_email_to_creator": row.send_email_to_creator,
						"auto_complete_unchanged": row.auto_complete_unchanged,
						"email_template": row.email_template,
						"attach_document_pdf": row.attach_document_pdf,
						"eligible_approvers": json.loads(row.eligible_approvers or "[]"),
					}
					for row in task.available_workflow_transitions
				],
				transition,
			],
		)
		task.reload()
	complete_task(
		task,
		_task_transition(task, uuid, None),
		comment=str(_value(vote, "vote_comment") or ""),
		completion_source="Carried",
		content_fingerprint=fingerprint,
	)
	from dinext_common.workflow_approval.projections import close_task_projection

	close_task_projection(frappe.get_doc("Workflow Task", task.name))


def carry_stable_votes(
	doc: object,
	round_id: str,
	votes: list[object],
) -> tuple[list[object], list[object]]:
	"""Copy completed votes whose UUID and semantic hash still exist."""
	names = _round_task_names(round_id)
	if not names:
		return [], list(votes)
	round_task = frappe.get_doc("Workflow Task", names[0])
	manifest = _parse_manifest(round_task)
	by_identity = {
		(
			str(row.get("transition_uuid") or ""),
			str(row.get("transition_semantic_hash") or ""),
		): row
		for row in manifest.get("transitions") or []
	}
	fingerprint = ContentFingerprint(
		version=str(_value(round_task, "entry_fingerprint_version") or "1"),
		digest=str(_value(round_task, "entry_fingerprint") or ""),
		canonical_json="",
	)
	carried: list[object] = []
	dropped: list[object] = []
	for vote in votes:
		key = (
			str(_value(vote, "transition_uuid") or ""),
			str(_value(vote, "transition_semantic_hash") or ""),
		)
		transition = by_identity.get(key)
		if transition is None or not _value(vote, "approver"):
			dropped.append(vote)
			continue
		_copy_carried_vote(doc, round_task, round_id, manifest, fingerprint, vote, transition)
		carried.append(vote)
	return carried, dropped


def _reached_winner(round_id: str, manifest: dict[str, Any]) -> dict[str, Any] | None:
	counts = _round_vote_counts(round_id, manifest, for_update=True)
	reached = [row for row in counts if int(row["votes"]) >= int(row["threshold"])]
	if not reached:
		return None
	return min(reached, key=lambda row: (int(row["idx"]), row["transition_uuid"]))


def rebuild_configuration_conflict(
	doc: object,
	round_id: str,
	reason: str,
) -> dict[str, Any]:
	"""Cancel a configuration conflict and open a round that keeps stable votes."""
	old_names = _round_task_names(round_id)
	old_manifest = _parse_manifest(frappe.get_doc("Workflow Task", old_names[0])) if old_names else {}
	entry_context = old_manifest.get("entry_context")
	votes = _completed_vote_rows(round_id)
	_cancel_round(round_id, reason)
	names = reconcile_source(doc, apply_automatic=False, entry_context=entry_context,
		deadline_assignments=old_manifest.get("deadline_assignments"))
	if not names:
		return {"carried": [], "dropped": votes, "new_tasks": []}
	new_round_id = frappe.db.get_value("Workflow Task", names[0], "approval_round_id")
	carried, dropped = carry_stable_votes(doc, new_round_id, votes)
	working = [
		frappe.get_doc("Workflow Task", name)
		for name in _round_task_names(new_round_id)
		if frappe.db.get_value("Workflow Task", name, "status") == "Working"
	]
	sample = frappe.get_doc("Workflow Task", names[0])
	manifest = _parse_manifest(sample)
	# A discarded completed decision is a new request, while continuing waits
	# and compatible carried decisions retain their frozen obligation.
	from dinext_common.workflow_approval.deadlines.lifecycle import FIELDS, candidates, prepare_task, snapshot
	dropped_actors = {str(_value(vote, "approver") or "") for vote in dropped}
	changed_deadlines = False
	for task in working:
		if task.approver not in dropped_actors:
			continue
		workflow = frappe.get_doc("Workflow", task.workflow)
		if not task.deadline_assignment_id and not candidates(task, workflow):
			continue
		task.update({field: None for field in (*FIELDS, "deadline_origin_task")})
		task.deadline_interval_value = 0
		prepare_task(task, workflow, started_at=task.creation)
		_set_task_values(task.name, {field: task.get(field) for field in (*FIELDS, "deadline_origin_task")})
		manifest.setdefault("deadline_assignments", {})[task.approver] = snapshot(task)
		changed_deadlines = True
	if changed_deadlines:
		_set_round_values(new_round_id, {"round_manifest": serialize_manifest(manifest)})
	if working:
		fingerprint = ContentFingerprint(
			version=str(sample.entry_fingerprint_version or "1"),
			digest=str(sample.entry_fingerprint or ""),
			canonical_json="",
		)
		_apply_automatic_votes(doc, working, manifest, fingerprint)
	winner = _reached_winner(new_round_id, manifest)
	if winner:
		_finalize_round(doc, new_round_id, winner)
	return {
		"carried": carried,
		"dropped": dropped,
		"new_tasks": _round_task_names(new_round_id),
	}


def reconcile_source(
	doc: object,
	*,
	cycle_guard: AutomationCycleGuard | None = None,
	apply_automatic: bool = True,
	entry_context: dict | None = None,
	deadline_assignments: dict | None = None,
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
	from dinext_common.workflow_approval.scenarios import service
	if service.is_ready():
		service.ensure_context(doc, persist_state=True, strict=False)
	context = _workflow_context(doc)
	if not context:
		return []
	workflow_name, workflow, _state_field, state = context
	fingerprint = get_content_fingerprint(doc, workflow)
	active_names = _active_task_names(_value(doc, "doctype"), _value(doc, "name"))
	if active_names:
		active = frappe.get_doc("Workflow Task", active_names[0])
		if active.workflow_state == state and entry_context is None:
			entry_context = _parse_manifest(active).get("entry_context")
		round_id = active.approval_round_id
		if active.round_status == "Finalizing":
			return active_names
		if active.workflow != workflow_name or active.workflow_state != state:
			_cancel_round(round_id, _("Source workflow state changed"))
		else:
			active_manifest = _parse_manifest(active)
			classification = _classify_round(active_manifest, workflow, state, round_id)
			if classification["void"]:
				_mark_conflicted(
					round_id,
					_("Workflow transition configuration changed"),
					metadata=configuration_change_metadata(classification),
				)
				return active_names
			if classification["dropped"] or classification["add"]:
				if _amend_open_round(doc, active, workflow, state, classification) is not None:
					return _round_task_names(round_id)
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
	manifest, task_transitions = _round_manifest_for(doc, workflow, state, current_rows)

	if entry_context:
		manifest["entry_context"] = entry_context
	if deadline_assignments:
		manifest["deadline_assignments"] = deadline_assignments
	round_id, tasks = _insert_round_tasks(
		doc,
		workflow_name,
		state,
		manifest,
		task_transitions,
		fingerprint,
	)
	for hook in frappe.get_hooks("workflow_approval_round_opened") or []:
		frappe.get_attr(hook)(doc, round_id)
	process_id = service.get_context(doc)["process_id"] if service.is_ready() else ""
	guard = cycle_guard or AutomationCycleGuard()
	may_automate = guard.permits(workflow_name, state, fingerprint.digest, process_id or "")
	if service.is_ready():
		may_automate = may_automate and service.automation_budget_available(doc, state_key=serialize_manifest([workflow_name, state, fingerprint.digest]))
	winner = (
		_apply_automatic_votes(doc, tasks, manifest, fingerprint, cycle_guard=guard)
		if apply_automatic and may_automate else None
	)
	if apply_automatic and not may_automate:
		message = _("Automatic Workflow processing paused. A new user action is required.")
		_set_round_values(round_id, {"failure_metadata": serialize_manifest({
			"reason": "automation_paused", "message": message})})
		doc.add_comment("Workflow", message)
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
		guard.visit(workflow_name, state, fingerprint.digest, process_id or "")
		if service.is_ready():
			service.consume_automatic_transition(doc, state_key=serialize_manifest([workflow_name, state, fingerprint.digest]))
		if not winner.get("pending_submission"):
			_finalize_round(doc, round_id, winner, cycle_guard=guard)
	return _round_task_names(round_id)


def _latest_personal_decisions(tasks: list[object]) -> dict[str, Any]:
	"""Select one personal decision per approver before checking reuse eligibility."""
	if not tasks or not tasks[0].source_created_at:
		return {}
	sample = tasks[0]
	rows = frappe.get_all(
		"Workflow Task",
		filters={
			"status": "Completed",
			"completion_source": ("in", ("Manual", "Bulk", "Signed Link")),
			"approver": ("in", [task.approver for task in tasks]),
			"reference_doctype": sample.reference_doctype,
			"reference_name": sample.reference_name,
			"source_created_at": sample.source_created_at,
			"workflow": sample.workflow,
			"workflow_state": sample.workflow_state,
		},
		fields=[
			"name",
			"approver",
			"transition_uuid",
			"transition_semantic_hash",
			"content_fingerprint",
			"content_fingerprint_version",
			"completed_at",
		],
		order_by="completed_at desc, name asc",
	)
	latest = {}
	for row in rows:
		latest.setdefault(row.approver, row)
	return latest


def _apply_automatic_votes(
	doc: object,
	tasks: list[object],
	manifest: dict[str, Any],
	fingerprint: ContentFingerprint,
	*,
	cycle_guard: AutomationCycleGuard | None = None,
) -> dict[str, Any] | None:
	eligible = [
		task for task in tasks
		if any(row.auto_complete_unchanged for row in task.available_workflow_transitions)
	]
	latest = _latest_personal_decisions(eligible)
	saved_flags = defaultdict(list)
	if latest:
		for row in frappe.get_all(
			"Available Workflow Transitions",
			filters={
				"parent": ("in", [decision.name for decision in latest.values()]),
				"parenttype": "Workflow Task",
				"parentfield": "available_workflow_transitions",
			},
			fields=["parent", "transition_uuid", "transition_semantic_hash", "auto_complete_unchanged"],
		):
			key = (row.parent, row.transition_uuid, row.transition_semantic_hash)
			saved_flags[key].append(row.auto_complete_unchanged)

	candidates = []
	for task in tasks:
		reused = latest.get(task.approver)
		if (
			not reused
			or not reused.transition_uuid
			or not reused.transition_semantic_hash
			or not reused.content_fingerprint
			or not reused.content_fingerprint_version
			or reused.content_fingerprint != fingerprint.digest
			or reused.content_fingerprint_version != fingerprint.version
		):
			continue
		if saved_flags.get((reused.name, reused.transition_uuid, reused.transition_semantic_hash)) != [1]:
			continue
		current = [
			row
			for row in task.available_workflow_transitions
			if row.transition_uuid == reused.transition_uuid
			and row.transition_semantic_hash == reused.transition_semantic_hash
		]
		if len(current) != 1 or current[0].auto_complete_unchanged != 1:
			continue
		if frappe.db.get_value("Workflow Task", task.name, "status") == "Completed":
			continue
		transition = current[0]
		candidates.append((task, transition, reused))

	reused_times: dict[str, list[str]] = {}
	rows = _round_vote_counts(tasks[0].approval_round_id, manifest) if tasks else []
	for task, transition, reused in candidates:
		key = str(_value(transition, "transition_uuid"))
		reused_times.setdefault(key, []).append(str(_value(reused, "completed_at") or ""))
		for row in rows:
			row["votes"] += int(row["transition_uuid"] == key)
	for row in rows:
		row["latest_reused_completed_at"] = max(reused_times.get(row["transition_uuid"], [""]))
	winner = select_automatic_winner(rows)
	from dinext_common.workflow_approval.queued_submission import stage_automatic
	if pending_result := stage_automatic(doc, candidates, winner, cycle_guard=cycle_guard):
		return {**winner, "pending_submission": pending_result["pending_submission"]}

	for task, transition, reused in candidates:
		from dinext_common.workflow_approval.scenarios import service
		if service.is_ready():
			service.pin_process(doc, task.get("workflow_process"))
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
				frappe.bold(frappe.utils.escape_html(task.approver)),
				frappe.bold(frappe.utils.escape_html(_(transition.action))),
			),
		)
	return winner


def _round_vote_counts(
	round_id: str, manifest: dict[str, Any], *, for_update: bool = False
) -> list[dict[str, Any]]:
	tasks = frappe.db.get_values(
		"Workflow Task",
		{"approval_round_id": round_id, "status": ("in", ["Completed", "Working"])},
		["name", "status", "transition_uuid", "transition_semantic_hash"],
		as_dict=True,
		for_update=for_update,
		order_by="name asc",
	)
	completed = [task for task in tasks if task.status == "Completed"]
	working_names = [task.name for task in tasks if task.status == "Working"]
	remaining = (
		frappe.db.get_values(
			"Available Workflow Transitions",
			{"parent": ("in", working_names)},
			"transition_uuid",
			pluck=True,
			for_update=for_update,
		)
		if working_names
		else []
	)
	return [
		{
			**transition,
			"votes": sum(
				1 for task in completed if task.transition_uuid == transition["transition_uuid"]
				and (
					not task.transition_semantic_hash
					or task.transition_semantic_hash == transition.get("transition_semantic_hash")
				)
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
	if len(candidates) > 1 and not transition_uuid:
		raise WorkflowApprovalConflictError(
			_("Specify the transition UUID. More than one workflow action matches.")
		)
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
	receipt_recorded: bool = False,
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
			"request_receipt_recorded": int(receipt_recorded),
		},
	)


def _dispatch_vote_completed(task: object, source: object, transition: object) -> None:
	for adapter_path in frappe.get_hooks("workflow_approval_vote_completed") or []:
		frappe.get_attr(adapter_path)(task, source, transition)


def current_comment_required(task: object, transition_uuid: str, *, workflow=None) -> bool:
	workflow = workflow or frappe.get_doc("Workflow", task.workflow)
	transition = next((row for row in workflow.transitions
		if row.custom_transition_uuid == transition_uuid and row.state == task.workflow_state), None)
	if transition is None:
		raise WorkflowApprovalConflictError(_("Workflow transition configuration changed"))
	return bool(transition.get("custom_comment_is_required"))


def _vote_parameters(task_name, transition_uuid, action, comment):
	return [task_name, transition_uuid, action, normalize_comment(comment, required=False)]


def _reserve_vote_response(task, source, request_id, parameters):
	target = request_receipts.target(source, task.name)
	target["workflow"] = task.workflow
	target["process_id"] = task.get("workflow_process")
	return request_receipts.reserve("Vote", request_id, parameters, [target])


@contextmanager
def _atomic_workflow_attempt(*, rollback_on=(NoEligibleApproversError, WorkflowDomainRollbackError)):
	"""Bound database changes, callbacks and file locks to a Workflow attempt."""
	savepoint = f"workflow_attempt_{frappe.generate_hash(length=12)}"
	cascade = deepcopy(getattr(frappe.local, "workflow_scenario_cascade", None))
	notes = deepcopy(getattr(frappe.flags, "workflow_finalization_errors", None))
	messages = getattr(frappe.local, "message_log", None)
	message_count = len(messages or [])
	realtime_log = getattr(frappe.local, "_realtime_log", None)
	realtime_count = len(realtime_log or [])
	locked_documents = len(getattr(frappe.local, "locked_documents", ()))
	callbacks = (
		frappe.db.before_commit, frappe.db.after_commit,
		frappe.db.before_rollback, frappe.db.after_rollback,
	)
	saved_callbacks = [(manager, tuple(manager._functions)) for manager in callbacks]
	frappe.db.savepoint(savepoint)
	try:
		yield
	except Exception as error:
		if isinstance(error, rollback_on):
			# A database error may already have invalidated the savepoint.
			with suppress(Exception):
				frappe.db.rollback(save_point=savepoint)
			for manager, previous in saved_callbacks:
				manager.reset()
				for callback in previous:
					manager.add(callback)
			if realtime_log is None:
				from frappe.realtime import clear_realtime_log

				clear_realtime_log()
			else:
				del realtime_log[realtime_count:]
				frappe.local._realtime_log = realtime_log
			for doc in getattr(frappe.local, "locked_documents", ())[locked_documents:]:
				with suppress(Exception):
					doc.unlock()
			frappe.local.workflow_scenario_cascade = cascade
			frappe.flags.workflow_finalization_errors = notes
			if messages is not None:
				del messages[message_count:]
		with suppress(Exception):
			frappe.db.release_savepoint(savepoint)
		raise
	else:
		frappe.db.release_savepoint(savepoint)


def cast_vote(
	task_name: str,
	*,
	transition_uuid: str | None = None,
	action: str | None = None,
	comment: object = None,
	request_id: str | None = None,
	completion_source: str = "Manual",
	receipt_managed: bool = False,
	expected_creation: str | None = None,
	expected_modified: str | None = None,
	expected_transition_hash: str | None = None,
	expected_delivery_key: str | None = None,
) -> VoteResult:
	"""Lock source then task, revalidate, record one vote, and finalize if reached."""
	pointer = frappe.db.get_value(
		"Workflow Task",
		task_name,
		["reference_doctype", "reference_name"],
		as_dict=True,
	)
	if not pointer:
		if request_id and not receipt_managed:
			receipt = request_receipts.get(request_receipts.request_key("Vote", request_id))
			if receipt:
				parameters = _vote_parameters(task_name, transition_uuid, action, comment)
				return request_receipts.replay(receipt, parameters)
		raise frappe.DoesNotExistError(_("Workflow Task does not exist"))
	_lock_domain_dependencies(pointer.reference_doctype, pointer.reference_name)
	source = frappe.get_doc(
		pointer.reference_doctype,
		pointer.reference_name,
		for_update=True,
	)
	task = frappe.get_doc("Workflow Task", task_name, for_update=True)
	task.check_permission("read")

	if expected_creation and str(get_datetime(source.creation)) != expected_creation:
		raise WorkflowApprovalConflictError(_("The Workflow target no longer matches the selected document"))
	if expected_delivery_key:
		from dinext_common.workflow_approval.signed_links import _open_action

		if not _open_action(task.name, expected_delivery_key, locked_task=task):
			raise ExpiredWorkflowActionError(_("Workflow Action is no longer open"))
	operation = domain_handler(source.doctype, "vote_context")
	with _atomic_workflow_attempt(), operation() if operation else nullcontext():
		return _cast_locked_vote(
			task, source, transition_uuid, action, comment, request_id, completion_source, receipt_managed,
			expected_modified=expected_modified, expected_transition_hash=expected_transition_hash,
		)


def _cast_locked_vote(
	task, source, transition_uuid, action, comment, request_id, completion_source, receipt_managed,
	*, expected_modified=None, expected_transition_hash=None,
) -> VoteResult:
	if task.approver != frappe.session.user and frappe.session.user != "Administrator":
		raise frappe.PermissionError(_("Only the snapshotted approver can complete this task"))
	if not frappe.db.get_value("User", task.approver, "enabled"):
		raise frappe.PermissionError(_("The snapshotted approver is disabled"))
	if task.source_created_at and get_datetime(task.source_created_at) != get_datetime(source.creation):
		raise WorkflowApprovalConflictError(_("The Workflow Task belongs to another document instance"))

	receipt = None
	record_vote_response = request_id and not receipt_managed
	if record_vote_response:
		parameters = _vote_parameters(task.name, transition_uuid, action, comment)
		key = request_receipts.request_key("Vote", request_id)
		receipt = request_receipts.get(key, for_update=task.status == "Completed")
		if receipt:
			return request_receipts.replay(receipt, parameters)

	if request_id and task.correlation_id == request_id:
		if task.get("request_receipt_recorded"):
			raise WorkflowApprovalConflictError(_("The Workflow request has expired. Refresh the document before acting."))
		if task.status == "Completed":
			return _vote_result(task, source, transitioned=task.round_status == "Transitioned")
	if task.status != "Working" or task.round_status != "Open":
		raise WorkflowApprovalConflictError(_("Workflow Task is no longer active"))

	if expected_modified:
		try:
			revision = get_datetime(expected_modified)
		except (ValueError, TypeError):
			raise frappe.ValidationError(_("Invalid document revision")) from None
		if get_datetime(source.modified) != revision:
			raise WorkflowSourceChangedError(_("The document has changed. Refresh it before confirming your decision."))

	from dinext_common.workflow_approval.scenarios import service
	service.validate_task(source, task)
	context = _workflow_context(source)
	if not context:
		raise WorkflowApprovalConflictError(_("The source document has no active Workflow"))
	workflow_name, workflow, _state_field, state = context
	if workflow_name != task.workflow or state != task.workflow_state:
		raise WorkflowApprovalConflictError(_("The source workflow state has changed"))

	if expected_transition_hash:
		current = next((
			row for row in workflow.transitions
			if row.state == state and row.custom_transition_uuid == transition_uuid
		), None)
		if not current or _transition_dict(current)["transition_semantic_hash"] != expected_transition_hash:
			frappe.db.after_rollback.add(partial(_persist_round_configuration, task.approval_round_id))
			raise WorkflowSourceChangedError(_("The approval rules have changed. Refresh the document before confirming."))

	manifest = _parse_manifest(task)
	classification = _classify_round(manifest, workflow, state, task.approval_round_id)
	if classification["void"]:
		_mark_conflicted(
			task.approval_round_id,
			_("Workflow transition configuration changed"),
			metadata=configuration_change_metadata(classification),
		)
		frappe.db.after_rollback.add(partial(_persist_round_configuration, task.approval_round_id))
		raise WorkflowApprovalConflictError(_("Workflow transition configuration changed"))
	if classification["dropped"] or classification["add"]:
		finalized = _amend_open_round(source, task, workflow, state, classification)
		task.reload()
		source.reload()
		if finalized or task.status != "Working" or task.round_status != "Open":
			result = _vote_result(task, source, transitioned=task.round_status == "Transitioned")
			if record_vote_response:
				receipt = _reserve_vote_response(task, source, request_id, parameters)
			if request_id and (receipt or receipt_managed) and not task.correlation_id:
				_set_task_values(task.name, {"correlation_id": request_id, "request_receipt_recorded": 1})
			if receipt:
				request_receipts.finish(receipt.name, result)
			return result
		manifest = _parse_manifest(task)
		try:
			transition = _task_transition(task, transition_uuid, action)
		except WorkflowApprovalConflictError:
			frappe.db.after_rollback.add(partial(_persist_round_configuration, task.approval_round_id))
			raise
	else:
		transition = _task_transition(task, transition_uuid, action)
	normalized_comment = normalize_comment(
		comment,
		required=current_comment_required(task, transition.transition_uuid, workflow=workflow),
	)
	from dinext_common.workflow_approval.queued_submission import stage

	staging_attempt = (
		_atomic_workflow_attempt(rollback_on=(Exception,))
		if source.docstatus == 0 and source.meta.queue_in_background
		else nullcontext()
	)
	with staging_attempt:
		if record_vote_response:
			receipt = _reserve_vote_response(task, source, request_id, parameters)
			if receipt.response is not None:
				return request_receipts.replay(receipt, parameters)
		validate_vote = domain_handler(source.doctype, "validate_vote")
		if validate_vote:
			validate_vote(source, transition.next_state)
		pending_result = stage(task, source, transition, workflow, comment=normalized_comment,
			completion_source=completion_source, request_id=request_id,
			receipt_recorded=bool(receipt or receipt_managed))
		if pending_result:
			if receipt:
				request_receipts.finish(receipt.name, pending_result)
			return pending_result
	previous_failure = frappe.parse_json(task.failure_metadata or "{}")
	if isinstance(previous_failure, dict) and previous_failure.get("reason") == "no_eligible_approvers":
		_set_round_values(task.approval_round_id, {"failure_metadata": None})
	fingerprint = get_content_fingerprint(source, workflow)
	if service.is_ready():
		service.start_cascade(source, manual=True)
		service.pin_process(source, task.get("workflow_process"))
	complete_task(
		task,
		transition,
		comment=normalized_comment,
		completion_source=completion_source,
		content_fingerprint=fingerprint,
		request_id=request_id,
		receipt_recorded=bool(receipt or receipt_managed),
	)
	task.reload()
	_dispatch_vote_completed(task, source, transition)
	source.add_comment(
		"Workflow",
		_("{0} voted {1}{2}").format(
			frappe.bold(frappe.utils.escape_html(task.approver)),
			frappe.bold(frappe.utils.escape_html(_(transition.action))),
			(
				f": {frappe.utils.escape_html(normalized_comment)}"
				if normalized_comment
				else ""
			),
		),
	)
	from dinext_common.workflow_approval.projections import close_task_projection

	close_task_projection(task)

	# The transaction may have read a task pointer before waiting for the source lock.
	# Use a current read to include votes committed during that wait.
	counts = _round_vote_counts(task.approval_round_id, manifest, for_update=True)
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
	refreshed_task = frappe.get_doc("Workflow Task", task.name, for_update=True)
	refreshed_source = frappe.get_doc(source.doctype, source.name, for_update=True)
	result = _vote_result(refreshed_task, refreshed_source, transitioned=transitioned)
	if receipt:
		request_receipts.finish(receipt.name, result)
	return result


def _vote_result(task: object, source: object, *, transitioned: bool) -> VoteResult:
	context = _workflow_context(source)
	result: VoteResult = {
		"task": task.name,
		"status": task.status,
		"round_status": task.round_status,
		"transitioned": transitioned,
		"reference_doctype": task.reference_doctype,
		"reference_name": task.reference_name,
		"workflow_state": context[3] if context else None,
	}

	if task.round_status == "Finalizing" and task.submission_queue:
		result["pending_submission"] = task.submission_queue
	return result


def _apply_winning_transition(source, workflow, winner, *, authorize=True):
	"""Run the exact transition through Frappe with the winning actor's access."""
	from dinext_common.workflow_approval.scenarios.compat import (
		authorized_finalization,
		exact_transition,
		install,
	)

	install()
	frappe.has_permission(source.doctype, doc=source.name, throw=True)
	authority = authorized_finalization(source) if authorize else nullcontext()
	with exact_transition(source, workflow.name, winner) as execution, authority:
		result = core_apply_workflow(source, winner["action"])
	return result, execution.submission_queue


def _state_docstatus(workflow, state: str) -> int:
	target = next((row for row in workflow.states if row.state == state), None)
	if target is None:
		raise WorkflowApprovalConflictError(_("Workflow transition configuration changed"))
	return int(target.doc_status or 0)


def _source_at_workflow_state(source, workflow, state: str) -> bool:
	return (
		source.get(workflow.workflow_state_field) == state
		and source.docstatus == _state_docstatus(workflow, state)
	)


def _round_matches_source(task, source) -> bool:
	from dinext_common.workflow_approval.scenarios import service

	if (
		(task.reference_doctype, task.reference_name) != (source.doctype, source.name)
		or not task.source_created_at
		or get_datetime(task.source_created_at) != get_datetime(source.creation)
	):
		return False
	if service.is_ready():
		context = service.get_context(source)
		return context["workflow"] == task.workflow and context["process_id"] == task.get("workflow_process")
	return True


def _finalization_actor(round_id: str, winner: dict[str, Any]) -> str:
	actor = frappe.db.get_value(
		"Workflow Task",
		{
			"approval_round_id": round_id,
			"status": "Completed",
			"transition_uuid": winner["transition_uuid"],
		},
		"approver",
		order_by="completed_at desc, name asc",
		for_update=True,
	)
	if not actor:
		raise WorkflowApprovalConflictError(_("Reached transition has no completed approver"))
	return actor


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
			"status": "Open",
			"user": actor,
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
	names = _round_task_names(round_id)
	if not names:
		return False
	sample = frappe.get_doc("Workflow Task", names[0], for_update=True)
	if sample.round_status not in {"Open", "Stalled", "Finalizing"} or not _round_matches_source(sample, source):
		return False
	from dinext_common.workflow_approval.scenarios import service

	workflow = frappe.get_doc("Workflow", sample.workflow)
	actor = _finalization_actor(round_id, winner)
	previous_user = frappe.session.user
	previous_flag = getattr(frappe.flags, "in_dinext_workflow_finalization", False)
	try:
		with _atomic_workflow_attempt(rollback_on=(Exception,)):
			_set_round_values(round_id, {"round_status": "Finalizing", "finalization_status": "Queued"})
			if source.get(workflow.workflow_state_field) != sample.workflow_state:
				raise WorkflowApprovalConflictError(_("The source workflow state has changed"))
			_ensure_finalization_placeholder(source, round_id, winner, actor)
			try:
				frappe.flags.in_dinext_workflow_finalization = True
				frappe.session.user = actor
				result, submission_queue = _apply_winning_transition(source, workflow, winner)
			finally:
				frappe.session.user = previous_user
				frappe.flags.in_dinext_workflow_finalization = previous_flag
			if submission_queue:
				# Completed or carried votes already belong to this round.
				from dinext_common.workflow_approval.queued_submission import stage_existing_finalization

				stage_existing_finalization(
					sample, winner, submission_queue, initiator=previous_user, actor=actor, cycle_guard=cycle_guard,
				)
				return False
			if result is None:
				raise WorkflowApprovalConflictError(_("Workflow core did not create the expected Submission Queue"))
			refreshed = frappe.get_doc(source.doctype, source.name, for_update=True)
			if not _round_matches_source(sample, refreshed) or not _source_at_workflow_state(
				refreshed, workflow, winner["next_state"]
			):
				raise WorkflowApprovalConflictError(_("The source workflow state has changed"))
			from dinext_common.workflow_approval.email_context import entry_context_for_round

			entry = entry_context_for_round(round_id, winner)
			_finish_round(round_id, winner)
			service.finish_transition(refreshed, sample.workflow, sample.get("workflow_process"))
			reconcile_source(refreshed, cycle_guard=cycle_guard, entry_context=entry)
			return True
	except (
		WorkflowDomainRollbackError, NoEligibleApproversError,
		frappe.db.InternalError, frappe.QueryDeadlockError, frappe.QueryTimeoutError,
	):
		raise
	except Exception as caught:
		notes = getattr(frappe.flags, "workflow_finalization_errors", None)
		if not isinstance(notes, list):
			notes = []
			frappe.flags.workflow_finalization_errors = notes
		notes.append(str(caught))
		_mark_conflicted(round_id, _("Workflow core validation rejected the winning transition"))
		_set_round_values(round_id, {"finalization_status": "Failed"})
		source.add_comment("Workflow", _("Workflow finalization failed and requires a manager rebuild."))
		frappe.log_error(
			title=f"Workflow approval finalization failed: {round_id}",
			reference_doctype=source.doctype,
			reference_name=source.name,
		)
		return False


def _finish_round(round_id: str, winner: dict[str, Any]) -> None:
	now = now_datetime()
	for task_name in _round_task_names(round_id, for_update=True):
		status = frappe.db.get_value("Workflow Task", task_name, "status", for_update=True)
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
	if (getattr(doc.flags, "workflow_scenario_prepared", False)
		and getattr(doc.flags, "workflow_scenario_prepared_workflow", None) == _workflow_name
		and next_state == _workflow.states[0].state):
		return
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
	from dinext_common.workflow_approval.scenarios import service
	service.archive_source(doc)
	from frappe.workflow.doctype.workflow_action.workflow_action import clear_workflow_actions

	from dinext_common.workflow_approval.projections import close_round_projections, close_task_projection

	doctype, name = _value(doc, "doctype"), _value(doc, "name")
	tasks = frappe.get_all(
		"Workflow Task",
		filters={"reference_doctype": doctype, "reference_name": name},
		fields=["name", "approval_round_id", "round_status", "status", "finalization_status"],
		order_by="name asc",
	)
	deleted_at = now_datetime()
	reason = _("Source document deleted")
	rounds = {task.approval_round_id for task in tasks if task.approval_round_id}
	active_rounds = {
		task.approval_round_id
		for task in tasks
		if task.approval_round_id and task.round_status in ACTIVE_ROUND_STATUSES
	}
	for round_id in sorted(active_rounds):
		_cancel_round(round_id, reason)
	for task in tasks:
		values: dict[str, Any] = {"source_deleted_at": deleted_at}
		if task.finalization_status == "Queued":
			values["finalization_status"] = "Failed"
		if task.status == "Working" and task.approval_round_id not in active_rounds:
			values.update(
				{
					"status": "Cancelled",
					"round_status": "Cancelled",
					"cancelled_at": deleted_at,
					"cancellation_reason": reason,
				}
			)
		_set_task_values(task.name, values)
		if not task.approval_round_id and task.status == "Working":
			close_task_projection(frappe.get_doc("Workflow Task", task.name))
	for round_id in sorted(rounds - active_rounds):
		close_round_projections(round_id)
	clear_workflow_actions(doctype, name)
	frappe.db.set_value(
		"Submission Queue",
		{"ref_doctype": doctype, "ref_docname": name, "status": "Queued"},
		{"status": "Failed", "ended_at": deleted_at, "exception": reason},
		update_modified=False,
	)


@_atomic_workflow_attempt()
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
	from dinext_common.workflow_approval.scenarios import service
	if service.is_ready():
		service.ensure_context(source, persist_state=True)
	context = _workflow_context(source)
	if not context:
		raise WorkflowApprovalConflictError(_("The source document has no active Workflow"))
	_workflow_name, workflow, state_field, state = context
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
		if actors is None:
			continue
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
	if service.is_ready():
		if not service.automation_budget_available(source):
			reconcile_source(source, apply_automatic=False)
			return source
		service.pin_process(source)
		service.consume_automatic_transition(source)
	actor = actor or actors[0]
	active_rounds = {
		frappe.db.get_value("Workflow Task", task_name, "approval_round_id")
		for task_name in _active_task_names(doctype, name)
	}
	for active_round_id in filter(None, active_rounds):
		_cancel_round(active_round_id, reason)
	round_id = f"domain-{frappe.generate_hash(length=32)}"
	winner = _transition_dict(transition)
	_ensure_finalization_placeholder(source, round_id, winner, actor)
	previous_user = frappe.session.user
	previous_flag = getattr(frappe.flags, "in_dinext_workflow_finalization", False)
	try:
		frappe.flags.in_dinext_workflow_finalization = True
		frappe.session.user = actor
		use_authorized_transition = domain_handler(doctype, "use_authorized_transition")
		result, queue = _apply_winning_transition(
			source, workflow, winner,
			authorize=bool(use_authorized_transition and use_authorized_transition(state_field)),
		)
		if queue or result is None:
			raise WorkflowDomainRollbackError(_("The source workflow state has changed"))
	finally:
		frappe.session.user = previous_user
		frappe.flags.in_dinext_workflow_finalization = previous_flag
		frappe.db.delete(
			"Workflow Action",
			{
				"custom_approval_round_id": round_id,
				"custom_workflow_task": ("is", "not set"),
			},
		)
	refreshed = frappe.get_doc(doctype, name)
	if not _source_at_workflow_state(refreshed, workflow, next_state):
		raise WorkflowDomainRollbackError(_("The source workflow state has changed"))
	refreshed.add_comment("Workflow", reason)
	service.finish_transition(refreshed)
	reconcile_source(refreshed, entry_context={
		"kind": "domain", "round_id": round_id, "action": transition.action,
		"next_state": next_state, "actor": actor,
		"comments": [{"system": True, "actor": actor, "at": str(frappe.utils.now_datetime()), "text": reason}],
	})
	return refreshed
