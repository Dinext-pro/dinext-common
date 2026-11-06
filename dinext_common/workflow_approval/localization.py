# ruff: noqa: RUF001
"""Localize active workflow records without changing recorded decisions."""

from collections import Counter, defaultdict

import frappe

from dinext_common.workflow_approval.policy import (
	policy_from_legacy_flag,
	required_approvals,
	transition_semantic_hash,
)


_REVIEW_STATES = {
	"На согласовании": "Pending Approval",
	"Согласовано": "Approved",
	"Отклонено": "Rejected",
}
_EDITING_STATES = {"Редактирование": "Editing", **_REVIEW_STATES}
STATE_NAMES = {
	"AFL Workflow": _EDITING_STATES,
	"UTP Workflow": _EDITING_STATES,
	"Expense_Claim_Workflow": {"Черновик": "Draft", **_REVIEW_STATES},
}
ACTION_NAMES = {
	"Передать на согласование": "Submit for Approval",
	"Согласовано": "Approve",
	"Не согласовано": "Reject",
	"Остановить Воркфлоу": "Stop Workflow",
	"Редактировать": "Edit",
}
_OPTIONALITY_WORKFLOWS = {
	*STATE_NAMES,
	"Dinext Budget Approval",
	"Dinext Project Scorecard Approval",
	"Goal Approval",
	"Project Approval",
	"Project Gate Checkpoint Workflow",
	"Project Stage Workflow",
	"Purchase_Invoice_Workflow",
	"Sales_Invoice_Workflow",
}
_ACTIVE_ROUND_STATUSES = ("Open", "Stalled", "Conflicted", "Finalizing")
_LABEL_FIELDS = ("state", "action", "next_state")
_VOTE_FLAGS = ("comment_is_required", "reset_on_change", "auto_complete_unchanged")
_UTP_LEGACY_VOTES = {"Approve": "Согласовано", "Reject": "Не согласовано"}
_CARD_NAMES = (
	"Моих Заявок на согласовании",
	"Моих Заявок Согласовано",
	"Моих Заявок Отклонено",
	"Заявки на отсутствие у меня на согласовании-2",
	"Заявки на отсутствие согласованные мной-1",
	"Заявок EC на согласовании",
	"Заявок EC Согласовано",
	"Заявок EC Отклонено",
	"Заявок EC у меня на согласовании",
	"Заявок EC Согласованных мной",
)


def state_name(workflow, value):
	return STATE_NAMES.get(workflow, {}).get(value, value)


def action_name(workflow, value):
	return ACTION_NAMES.get(value, value) if workflow in STATE_NAMES else value


def _labels(workflow, transition):
	return {
		"state": state_name(workflow, transition.get("state")),
		"action": action_name(workflow, transition.get("action")),
		"next_state": state_name(workflow, transition.get("next_state")),
	}


def _same_named_transition(workflow, snapshot, current):
	return (
		bool(current.get("transition_uuid"))
		and snapshot.get("transition_uuid") == current["transition_uuid"]
		and _labels(workflow, snapshot) == {key: current[key] for key in _LABEL_FIELDS}
		and all(
			bool(snapshot.get(field)) == bool(current.get(field))
			for field in _VOTE_FLAGS
			if field in snapshot
		)
	)


def renamed_transition(workflow, snapshot, current):
	"""Return the new labels and hash only when the old rule is provably identical."""
	if not _same_named_transition(workflow, snapshot, current):
		return None
	old_labels = {field: snapshot.get(field) for field in _LABEL_FIELDS}
	if _labels(workflow, snapshot) == old_labels:
		return None
	if snapshot.get("transition_semantic_hash") != transition_semantic_hash({**current, **old_labels}):
		return None
	return {**_labels(workflow, snapshot), "transition_semantic_hash": current["transition_semantic_hash"]}


def preserve_fixture_transition_ids(doc, method=None):
	"""Keep live UUIDs for semantically equivalent rows when Frappe reloads fixtures."""
	if not frappe.flags.in_fixtures or doc.name not in _OPTIONALITY_WORKFLOWS:
		return
	if not frappe.db.exists("Workflow", doc.name):
		return
	from dinext_common.workflow_approval.engine import _transition_dict

	def identity(row):
		transition = _transition_dict(row)
		if not row.get("custom_parallel_approval_policy"):
			transition["policy"] = policy_from_legacy_flag(row.get("custom_all_users_with_role"))
		return transition_semantic_hash({**transition, **_labels(doc.name, transition)})

	existing = defaultdict(list)
	for row in frappe.get_doc("Workflow", doc.name).transitions:
		if row.custom_transition_uuid:
			existing[identity(row)].append(row.custom_transition_uuid)

	incoming = [(row, identity(row)) for row in doc.transitions]
	counts = Counter(key for _, key in incoming)
	for row, key in incoming:
		matches = existing[key]
		if len(matches) == 1 and counts[key] == 1:
			row.custom_transition_uuid = matches[0]


def guard_label_migration():
	"""Reject in-flight legacy finalizations before fixture imports can commit."""
	if not frappe.db.table_exists("Workflow Task"):
		return
	fields = ["workflow", "workflow_state", "round_manifest", "approval_round_id"]
	if not {*fields, "round_status"}.issubset(frappe.db.get_table_columns("Workflow Task")):
		return
	for task in frappe.get_all(
		"Workflow Task",
		filters={"workflow": ("in", tuple(STATE_NAMES)), "round_status": "Finalizing"},
		fields=fields,
	):
		manifest = (frappe.parse_json(task.round_manifest) or {}) if task.round_manifest else {}
		uses_legacy_state = any(task.get(key) in STATE_NAMES[task.workflow] for key in ("state", "workflow_state"))
		personal = frappe.get_all(
			"Available Workflow Transitions", filters={"parent": task.name}, fields=list(_LABEL_FIELDS)
		)
		uses_legacy_transition = any(
			_labels(task.workflow, row) != {key: row.get(key) for key in _LABEL_FIELDS}
			for row in [*manifest.get("transitions", ()), *personal]
		)
		if uses_legacy_state or uses_legacy_transition:
			frappe.throw(f"Wait for Workflow round {task.approval_round_id} to finish before migration.")


def _utp_personal_evidence(tasks, current):
	"""Collect the original hashes preserved in personal rows by the earlier UTP migration."""
	first = tasks[0]
	evidence = defaultdict(dict)
	if first.workflow != "UTP Workflow" or any(task.round_manifest != first.round_manifest for task in tasks):
		return evidence
	if len({task.approver for task in tasks}) != len(tasks):
		return evidence
	for task in tasks:
		for child in task.available_workflow_transitions:
			uuid = child.transition_uuid
			config = current.get(uuid, {})
			old_action = _UTP_LEGACY_VOTES.get(config.get("action"))
			option = child.as_dict()
			if not old_action or not _same_named_transition(task.workflow, option, config):
				continue
			# The earlier migration changed displayed labels and the manifest hash separately.
			# The personal row can still prove the original hash using the exact old action.
			old_option = {**option, "action": old_action}
			if not renamed_transition(task.workflow, old_option, config):
				continue
			if task.status == "Completed" and task.transition_uuid == uuid:
				if (
					task.transition_semantic_hash != child.transition_semantic_hash
					or _labels(task.workflow, task) != _labels(task.workflow, option)
				):
					continue
			evidence[uuid][task.approver] = child
	for task in tasks:
		if task.status == "Completed" and task.approver not in evidence.get(task.transition_uuid, {}):
			evidence.pop(task.transition_uuid, None)
	return evidence


def _verified_utp_rename(row, current, evidence):
	"""Repair a stale manifest only when every actor's personal row proves the current rule."""
	legacy_action = _UTP_LEGACY_VOTES.get(current.get("action"))
	if (
		not legacy_action
		or row.get("action") != legacy_action
		or row.get("state") != current["state"]
		or row.get("next_state") != current["next_state"]
	):
		return None
	if not _same_named_transition("UTP Workflow", row, current):
		return None
	if row.get("allowed") != current["allowed"] or row.get("policy") != current["policy"]:
		return None
	approvers = set(row.get("eligible_approvers") or [])
	if not approvers or approvers != set(evidence):
		return None
	threshold = required_approvals(current["policy"], current["minimum_approvals"], len(approvers))
	if row.get("threshold") != threshold or any(child.threshold != threshold for child in evidence.values()):
		return None
	return {**_labels("UTP Workflow", row), "transition_semantic_hash": current["transition_semantic_hash"]}


def _rename_round_task(task, current, evidence):
	from dinext_common.workflow_approval.engine import serialize_manifest

	manifest = frappe.parse_json(task.round_manifest) if task.round_manifest else None
	updates = {
		field: state_name(task.workflow, task.get(field))
		for field in ("state", "workflow_state")
		if task.get(field) in STATE_NAMES[task.workflow]
	}
	renames = {}
	verified_uuids = set()
	for row in (manifest or {}).get("transitions", []):
		uuid = row.get("transition_uuid")
		config = current.get(uuid, {})
		proven = evidence.get(uuid, {})
		values = renamed_transition(task.workflow, row, config) or _verified_utp_rename(row, config, proven)
		if values:
			renames[(uuid, row.get("transition_semantic_hash"))] = values
			if child := proven.get(task.approver):
				renames[(uuid, child.transition_semantic_hash)] = values
			row.update(values)
		if (
			_same_named_transition(task.workflow, row, config)
			and row.get("transition_semantic_hash") == config["transition_semantic_hash"]
			and all(row.get(key) == config[key] for key in _LABEL_FIELDS)
		):
			verified_uuids.add(uuid)

	if renames:
		updates["round_manifest"] = serialize_manifest(manifest)
	child_updates = []
	for child in task.available_workflow_transitions:
		uuid = child.transition_uuid
		if uuid not in verified_uuids:
			continue
		key = (uuid, child.transition_semantic_hash)
		values = renames.get(key) or renamed_transition(task.workflow, child.as_dict(), current[uuid])
		if values:
			renames[key] = values
			child_updates.append((child, values))
	if task.status == "Completed":
		updates.update(renames.get((task.transition_uuid, task.transition_semantic_hash), {}))
	if updates or child_updates:
		if task.round_status == "Finalizing":
			frappe.throw(f"Wait for Workflow round {task.approval_round_id} to finish before renaming its states.")
		if updates:
			task.db_set(updates, update_modified=False)
		for child, values in child_updates:
			child.db_set(values, update_modified=False)

	previous_states = [
		old for old, canonical in STATE_NAMES[task.workflow].items()
		if canonical == state_name(task.workflow, task.workflow_state)
	]
	if previous_states:
		frappe.db.set_value(
			"Workflow Action",
			{"custom_workflow_task": task.name, "workflow_state": ("in", previous_states)},
			"workflow_state",
			state_name(task.workflow, task.workflow_state),
			update_modified=False,
		)


def _migrate_card_filters():
	for card in frappe.get_all("Number Card", filters={"name": ("in", _CARD_NAMES)}, fields=["name", "filters_json"]):
		filters = frappe.parse_json(card.filters_json)
		original = frappe.as_json(filters)
		if isinstance(filters, dict) and filters.get("state") in _REVIEW_STATES:
			filters["state"] = _REVIEW_STATES[filters["state"]]
		elif isinstance(filters, list):
			for row in filters:
				if len(row) > 3 and row[1] in ("status", "workflow_state") and isinstance(row[3], str):
					row[3] = _REVIEW_STATES.get(row[3], row[3])
		if frappe.as_json(filters) != original:
			frappe.db.set_value("Number Card", card.name, "filters_json", frappe.as_json(filters), update_modified=False)


def migrate_workflow_labels():
	"""Migrate source rows and active projections after canonical fixtures are loaded."""
	from dinext_common.workflow_approval.engine import _transition_dict

	for name, states in STATE_NAMES.items():
		if not frappe.db.exists("Workflow", name):
			continue
		workflow = frappe.get_doc("Workflow", name)
		if not workflow.is_active or not set(states.values()).issubset(row.state for row in workflow.states):
			continue

		source_fields = [workflow.workflow_state_field]
		if name == "AFL Workflow":
			source_fields.append("status")
		for old, new in states.items():
			for field in source_fields:
				frappe.db.set_value(
					workflow.document_type, {field: old}, field, new, update_modified=False
				)
			frappe.db.set_value(
				"Workflow Action",
				{
					"reference_doctype": workflow.document_type,
					"status": "Open",
					"workflow_state": old,
					"custom_workflow_task": ("is", "not set"),
				},
				"workflow_state",
				new,
				update_modified=False,
			)

		current = {row.custom_transition_uuid: _transition_dict(row) for row in workflow.transitions}
		rounds = defaultdict(list)
		for row in frappe.get_all(
			"Workflow Task",
			filters={"workflow": name, "round_status": ("in", _ACTIVE_ROUND_STATUSES)},
			fields=["name", "approval_round_id"],
		):
			rounds[row.approval_round_id or row.name].append(frappe.get_doc("Workflow Task", row.name))
		for tasks in rounds.values():
			evidence = _utp_personal_evidence(tasks, current)
			for task in tasks:
				_rename_round_task(task, current, evidence)

	_migrate_card_filters()
	frappe.db.set_value(
		"Workflow Document State",
		{"parent": "Маршрут заявки на закупку", "parentfield": "states", "state": "Черновик", "is_optional_state": 0},
		"is_optional_state",
		1,
		update_modified=False,
	)
