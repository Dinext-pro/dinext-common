# ruff: noqa: RUF001
"""Localize active workflow records without changing recorded decisions."""

from collections import Counter, defaultdict

import frappe

from dinext_common.workflow_approval.policy import (
	policy_from_legacy_flag,
	transition_semantic_hash,
)

ACTION_NAMES = {
	"Передать на согласование": "Submit for Approval",
	"Согласовано": "Approve",
	"Не согласовано": "Reject",
	"Остановить Воркфлоу": "Stop Workflow",
	"Редактировать": "Edit",
}
_ACTIVE_ROUND_STATUSES = ("Open", "Stalled", "Conflicted", "Finalizing")
_LABEL_FIELDS = ("state", "action", "next_state")
_VOTE_FLAGS = ("comment_is_required", "reset_on_change", "auto_complete_unchanged")


def _localization_hooks():
	if not getattr(frappe.local, "site", None):
		return {}
	return frappe.get_hooks("workflow_approval_localization", default={})


def _localization_rules():
	return {
		**{
			workflow: frappe.get_attr(paths[-1])()
			for workflow, paths in _localization_hooks().items()
			if paths
		},
	}


def workflow_label_rules(workflow):
	if paths := _localization_hooks().get(workflow):
		return frappe.get_attr(paths[-1])()
	return {}


def _state_names(workflow):
	return workflow_label_rules(workflow).get("states", {})


def state_name(workflow, value):
	return _state_names(workflow).get(value, value)


def action_name(workflow, value):
	return ACTION_NAMES.get(value, value) if _state_names(workflow) else value


def _labels(workflow, transition):
	states = _state_names(workflow)
	state, action, next_state = (transition.get(key) for key in _LABEL_FIELDS)
	return {
		"state": states.get(state, state),
		"action": ACTION_NAMES.get(action, action) if states else action,
		"next_state": states.get(next_state, next_state),
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
	if not frappe.flags.in_fixtures:
		return
	if (doc.name not in _localization_hooks()
		and doc.name not in frappe.get_hooks("workflow_approval_preserve_fixture_transition_ids")):
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
	rules = _localization_rules()
	for task in frappe.get_all(
		"Workflow Task",
		filters={"workflow": ("in", tuple(rules)), "round_status": "Finalizing"},
		fields=fields,
	):
		manifest = (frappe.parse_json(task.round_manifest) or {}) if task.round_manifest else {}
		uses_legacy_state = any(
			task.get(key) in rules[task.workflow].get("states", {}) for key in ("state", "workflow_state")
		)
		personal = frappe.get_all(
			"Available Workflow Transitions", filters={"parent": task.name}, fields=list(_LABEL_FIELDS)
		)
		uses_legacy_transition = any(
			_labels(task.workflow, row) != {key: row.get(key) for key in _LABEL_FIELDS}
			for row in [*manifest.get("transitions", ()), *personal]
		)
		if uses_legacy_state or uses_legacy_transition:
			frappe.throw(f"Wait for Workflow round {task.approval_round_id} to finish before migration.")


def _rename_round_task(task, current, evidence, rules):
	from dinext_common.workflow_approval.engine import serialize_manifest

	manifest = frappe.parse_json(task.round_manifest) if task.round_manifest else None
	states = rules["states"]
	recover_legacy_transition = rules.get("recover_legacy_transition")
	updates = {
		field: states[task.get(field)]
		for field in ("state", "workflow_state")
		if task.get(field) in states
	}
	renames = {}
	verified_uuids = set()
	for row in (manifest or {}).get("transitions", []):
		uuid = row.get("transition_uuid")
		config = current.get(uuid, {})
		proven = evidence.get(uuid, {})
		values = renamed_transition(task.workflow, row, config)
		if not values and recover_legacy_transition:
			values = recover_legacy_transition(row, config, proven)
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

	current_state = states.get(task.workflow_state, task.workflow_state)
	previous_states = [old for old, canonical in states.items() if canonical == current_state]
	if previous_states:
		frappe.db.set_value(
			"Workflow Action",
			{"custom_workflow_task": task.name, "workflow_state": ("in", previous_states)},
			"workflow_state",
			current_state,
			update_modified=False,
		)


def _migrate_card_filters(names, states):
	for card in frappe.get_all("Number Card", filters={"name": ("in", names)}, fields=["name", "filters_json"]):
		filters = frappe.parse_json(card.filters_json)
		original = frappe.as_json(filters)
		if isinstance(filters, dict) and filters.get("state") in states:
			filters["state"] = states[filters["state"]]
		elif isinstance(filters, list):
			for row in filters:
				if len(row) > 3 and row[1] in ("status", "workflow_state") and isinstance(row[3], str):
					row[3] = states.get(row[3], row[3])
		if frappe.as_json(filters) != original:
			frappe.db.set_value("Number Card", card.name, "filters_json", frappe.as_json(filters), update_modified=False)


def migrate_workflow_labels():
	"""Migrate source rows and active projections after canonical fixtures are loaded."""
	from dinext_common.workflow_approval.engine import _transition_dict

	for name, rules in _localization_rules().items():
		if cards := rules.get("cards"):
			_migrate_card_filters(cards, rules["card_states"])
		for state in rules.get("optional_states", ()):
			frappe.db.set_value(
				"Workflow Document State",
				{"parent": name, "parentfield": "states", "state": state, "is_optional_state": 0},
				"is_optional_state", 1, update_modified=False,
			)
		states = rules.get("states")
		if not states:
			continue
		if not frappe.db.exists("Workflow", name):
			continue
		workflow = frappe.get_doc("Workflow", name)
		if not workflow.is_active or not set(states.values()).issubset(row.state for row in workflow.states):
			continue

		source_fields = dict.fromkeys((workflow.workflow_state_field, *rules.get("additional_state_fields", ())))
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
		collect_legacy_evidence = rules.get("collect_legacy_evidence")
		for tasks in rounds.values():
			evidence = collect_legacy_evidence(tasks, current) if collect_legacy_evidence else {}
			for task in tasks:
				_rename_round_task(task, current, evidence, rules)
