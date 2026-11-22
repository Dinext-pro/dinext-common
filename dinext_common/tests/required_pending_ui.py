"""Isolated display-only fixtures for mandatory-target pending banners."""

from __future__ import annotations

import json

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

from dinext_common.tests.ui_test_helpers import (
	_assert_flag,
	_delete_tasks_for,
	_engine_paused,
	_ensure_permission_condition,
	_ensure_read_perm,
	_ensure_role,
	_ensure_user,
	_manual_task,
	_transition,
)

PREFIX = "_Cypress Required Pending"
ROLE = PREFIX + " Reader"
VIEWER = "cy.required.viewer@example.com"
REQUIRED = "cy.required.actor@example.com"
OPTIONAL = "cy.optional.actor@example.com"
MIXED = "cy.mixed.actor@example.com"
USERS = (VIEWER, REQUIRED, OPTIONAL, MIXED)
ISSUE_WORKFLOW = PREFIX + " Issue"
PREVIOUS_KEY = "cypress_required_pending_previous_issue_workflows"
FIXTURE_KEY = "cypress_required_pending_fixture"
LEGACY_SCRIPTS_KEY = "cypress_required_pending_legacy_scripts"


def _workflow(name, doctype, state_field, state, mandatory, optional, *, role=ROLE):
	for value in (state, mandatory, optional):
		if not frappe.db.exists("Workflow State", value):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": value}).insert(
				ignore_permissions=True
			)
	transitions = []
	for label, target in (("Cypress Required", mandatory), ("Cypress Optional", optional)):
		if not frappe.db.exists("Workflow Action Master", label):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": label}).insert(
				ignore_permissions=True
			)
		row = _transition(label, target, policy="Any", uuid=name + label, allowed=role)
		row["state"] = state
		transitions.append(row)
	return frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": name,
			"document_type": doctype,
			"workflow_state_field": state_field,
			"is_active": 0,
			"send_email_alert": 0,
			"states": [
				{
					"state": value,
					"doc_status": "0",
					"allow_edit": "All",
					"is_optional_state": int(value == optional),
				}
				for value in (state, mandatory, optional)
			],
			"transitions": transitions,
		}
	).insert(ignore_permissions=True)


def _tasks(source, workflow, state, mandatory, optional, *, users=USERS, role=ROLE, second=False):
	viewer, required, optional_actor, mixed = users
	round_id = frappe.generate_hash(length=40)
	for actor, targets in [
		(required, [optional] if second else [mandatory]),
		(optional_actor, [optional]),
		(mixed, [mandatory, optional]),
		(viewer, [mandatory, optional]),
	]:
		name = _manual_task(
			doctype=source.doctype,
			name=source.name,
			workflow=workflow.name,
			state=state,
			approver=actor,
			round_status="Open",
			status="Working",
			round_id=round_id,
		)
		task = frappe.get_doc("Workflow Task", name)
		for target in targets:
			task.append(
				"available_workflow_transitions",
				{
					"state": state,
					"action": "Cypress Required" if target == mandatory else "Cypress Optional",
					"next_state": target,
					"allowed_role": role,
					"policy": "Any",
					"threshold": 1,
				},
			)
		# Workflow Tasks are immutable; their fixture options are inserted as child rows.
		for index, row in enumerate(task.available_workflow_transitions, 1):
			row.parent = task.name
			row.parenttype = "Workflow Task"
			row.parentfield = "available_workflow_transitions"
			row.idx = index
			row.db_insert()
	return round_id


@whitelist_for_tests
def cleanup_required_pending_cypress():
	fixture = frappe.db.get_default(FIXTURE_KEY)
	issues = frappe.get_all("Issue", filters={"subject": "Cypress Required Pending"}, pluck="name")
	previous_flag = frappe.flags.get("in_workflow_task_retention")
	try:
		_delete_tasks_for("Issue", issues)
	finally:
		frappe.flags.in_workflow_task_retention = previous_flag
	for name in issues:
		frappe.delete_doc("Issue", name, force=True, ignore_permissions=True)
	frappe.delete_doc_if_exists("Workflow", ISSUE_WORKFLOW, force=True)
	previous = frappe.db.get_default(PREVIOUS_KEY)
	if previous is not None:
		for name in json.loads(previous):
			if frappe.db.exists("Workflow", name):
				frappe.db.set_value("Workflow", name, "is_active", 1, update_modified=False)
	legacy_scripts = frappe.db.get_default(LEGACY_SCRIPTS_KEY)
	if legacy_scripts:
		for name in json.loads(legacy_scripts):
			if frappe.db.exists("Client Script", name):
				frappe.db.set_value("Client Script", name, "enabled", 1, update_modified=False)
	frappe.db.set_default(LEGACY_SCRIPTS_KEY, None)
	for user in USERS:
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	frappe.db.delete("Custom DocPerm", {"role": ROLE})
	frappe.db.delete("DocType Permission Condition", {"role": ROLE})
	if frappe.db.exists("Role", ROLE):
		frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
	frappe.db.set_default(FIXTURE_KEY, None)
	frappe.db.set_default(PREVIOUS_KEY, None)
	frappe.cache.hdel("workflow", "Issue")
	frappe.clear_cache()
	return {"cleaned": True, "had_fixture": bool(fixture)}


@whitelist_for_tests
def seed_required_pending_cypress():
	_assert_flag()
	cleanup_required_pending_cypress()
	previous = frappe.get_all("Workflow", filters={"document_type": "Issue", "is_active": 1}, pluck="name")
	frappe.db.set_default(PREVIOUS_KEY, json.dumps(previous))
	# Legacy localhost scripts still request a removed pre-bundle asset. Isolate
	# that unrelated loader for this suite and restore its enabled state afterward.
	legacy_scripts = [
		row.name
		for row in frappe.get_all(
			"Client Script", filters={"dt": "Issue", "enabled": 1}, fields=["name", "script"]
		)
		if "/assets/dinext_common/js/form_conflict_merge.js" in (row.script or "")
	]
	frappe.db.set_default(LEGACY_SCRIPTS_KEY, json.dumps(legacy_scripts))
	for name in legacy_scripts:
		frappe.db.set_value("Client Script", name, "enabled", 0, update_modified=False)
	_ensure_role(ROLE)
	for doctype in (
		"Issue",
		"Kanban Board",
		"Report",
		"Support Settings",
	):
		_ensure_read_perm(doctype, ROLE)
	_ensure_permission_condition("Issue_Permissions", ROLE)
	for user, title in [
		(VIEWER, "Cypress Pending Viewer"),
		(REQUIRED, "Cypress Required Actor"),
		(OPTIONAL, "Cypress Optional Actor"),
		(MIXED, "Cypress Mixed Actor"),
	]:
		_ensure_user(user, title, [ROLE, "Desk User", "System Manager"])
	issue_workflow = _workflow(ISSUE_WORKFLOW, "Issue", "status", "Open", "Closed", "Replied")
	for name in previous:
		frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
	frappe.db.set_value("Workflow", issue_workflow.name, "is_active", 1, update_modified=False)
	frappe.cache.hdel("workflow", "Issue")
	with _engine_paused():
		issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Cypress Required Pending", "status": "Open"}
		).insert(ignore_permissions=True)
	_tasks(issue, issue_workflow, "Open", "Closed", "Replied")
	from dinext_common.tests.ui_test_helpers import PASSWORD

	fixture = {
		"viewer": VIEWER,
		"password": PASSWORD,
		"issue": issue.name,
		"required": "Cypress Required Actor",
		"optional": "Cypress Optional Actor",
		"mixed": "Cypress Mixed Actor",
		"viewer_name": "Cypress Pending Viewer",
	}
	frappe.db.set_default(FIXTURE_KEY, json.dumps(fixture))
	frappe.clear_cache()
	return fixture


@whitelist_for_tests
def set_required_pending_optional(optional: int):
	fixture = frappe.db.get_default(FIXTURE_KEY)
	if not fixture or frappe.session.user not in (VIEWER, "Administrator"):
		frappe.throw("Only the fixture viewer may change its display metadata", frappe.PermissionError)
	if int(optional) not in (0, 1):
		frappe.throw("Unknown fixture metadata")
	frappe.db.set_value(
		"Workflow Document State", {"parent": ISSUE_WORKFLOW, "state": "Closed"}, "is_optional_state", int(optional)
	)
	return {"optional": int(optional)}


@whitelist_for_tests
def set_workflow_comments_cypress(mode: str):
	"""Record display-only decisions on this suite's Issue."""
	_assert_flag()
	fixture = frappe.parse_json(frappe.db.get_default(FIXTURE_KEY) or "null")
	if not fixture or frappe.session.user not in (VIEWER, "Administrator"):
		frappe.throw("Only the fixture viewer may edit its comment fixtures", frappe.PermissionError)
	return _set_workflow_comments("Issue", [fixture["issue"]], ISSUE_WORKFLOW, "Open", USERS, mode)


def _set_workflow_comments(doctype, names, workflow, state, users, mode):
	from frappe.utils import add_to_date, now_datetime

	if mode not in ("empty", "single", "self", "multiple", "mixed", "later", "unsafe"):
		frappe.throw("Unknown comment fixture")
	viewer, required_actor, _, mixed = users
	marker = "cypress-workflow-comment-banner"
	previous_flag = frappe.flags.get("in_workflow_task_retention")
	frappe.flags.in_workflow_task_retention = True
	try:
		for task_name in frappe.get_all("Workflow Task", filters={
			"reference_doctype": doctype, "reference_name": ("in", names), "correlation_id": marker,
		}, pluck="name"):
			frappe.delete_doc("Workflow Task", task_name, force=True, ignore_permissions=True)
	finally:
		frappe.flags.in_workflow_task_retention = previous_flag
	if mode == "empty":
		return {"comments": 0}
	for name in names:
		round_id = frappe.generate_hash(length=40)
		decisions = [(viewer if mode == "self" else required_actor, "Correct the dates", True)]
		if mode in ("multiple", "mixed", "later"):
			decisions.append((mixed, "Attach the details", True))
		if mode == "unsafe":
			decisions[0] = (required_actor, 'First line\n<img src=x onerror="window.commentExecuted=true">' + "long" * 100, True)
		if mode in ("mixed", "later"):
			decisions.append((viewer, "", False))
		for index, (actor, text, required) in enumerate(decisions):
			if mode == "later" and not required:
				round_id = frappe.generate_hash(length=40)
			uuid = "comment-required" if required else "without-comment"
			task_name = _manual_task(
				doctype=doctype, name=name, workflow=workflow, state=state,
				approver=actor, round_status="Open", status="Completed", round_id=round_id,
			)
			frappe.db.set_value("Workflow Task", task_name, {
				"correlation_id": marker, "vote_comment": text, "transition_uuid": uuid,
				"completed_at": add_to_date(now_datetime(), seconds=index - 5),
				"round_manifest": json.dumps({"transitions": [{
					"transition_uuid": uuid, "comment_is_required": required,
				}]}),
			}, update_modified=False)
	return {"sources": names}
