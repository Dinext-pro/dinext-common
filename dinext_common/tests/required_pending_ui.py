"""Isolated display-only fixtures for mandatory-target pending banners."""

from __future__ import annotations

import json

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

from dinext_common.tests.ui_test_helpers import (
	_assert_flag,
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
POSITION_WORKFLOW = PREFIX + " Position"
PREVIOUS_KEY = "cypress_required_pending_previous_issue_workflows"
FIXTURE_KEY = "cypress_required_pending_fixture"
LEGACY_SCRIPTS_KEY = "cypress_required_pending_legacy_scripts"
GROUP = PREFIX + " Group"


def _workflow(name, doctype, state_field, state, mandatory, optional):
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
		row = _transition(label, target, policy="Any", uuid=name + label, allowed=ROLE)
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


def _tasks(source, workflow, state, mandatory, optional, *, second=False):
	round_id = frappe.generate_hash(length=40)
	for actor, targets in [
		(REQUIRED, [optional] if second else [mandatory]),
		(OPTIONAL, [optional]),
		(MIXED, [mandatory, optional]),
		(VIEWER, [mandatory, optional]),
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
					"allowed_role": ROLE,
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
	timesheets = frappe.get_all("User Timesheet", filters={"timesheet_from": VIEWER}, pluck="name")
	positions = (
		frappe.get_all(
			"User Timesheet Position", filters={"user_timesheet": ("in", timesheets)}, pluck="name"
		)
		if timesheets
		else []
	)
	issues = frappe.get_all("Issue", filters={"subject": "Cypress Required Pending"}, pluck="name")
	previous_flag = frappe.flags.get("in_workflow_task_retention")
	frappe.flags.in_workflow_task_retention = True
	try:
		for doctype, names in (("User Timesheet Position", positions), ("Issue", issues)):
			if not names:
				continue
			for name in frappe.get_all(
				"Workflow Task",
				filters={"reference_doctype": doctype, "reference_name": ("in", names)},
				pluck="name",
			):
				frappe.delete_doc("Workflow Task", name, force=True, ignore_permissions=True)
			for name in names:
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	finally:
		frappe.flags.in_workflow_task_retention = previous_flag
	for name in timesheets:
		frappe.delete_doc("User Timesheet", name, force=True, ignore_permissions=True)
	for name in frappe.get_all("Worker", filters={"wuser": VIEWER}, pluck="name"):
		frappe.delete_doc("Worker", name, force=True, ignore_permissions=True)
	if frappe.db.exists("User Group", GROUP):
		frappe.delete_doc("User Group", GROUP, force=True, ignore_permissions=True)
	for name in (ISSUE_WORKFLOW, POSITION_WORKFLOW):
		if frappe.db.exists("Workflow", name):
			frappe.delete_doc("Workflow", name, force=True, ignore_permissions=True)
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
	from dinext_timesheets.tests.ui_test_helpers import _worker

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
		"User Timesheet",
		"User Timesheet Position",
		"Kanban Board",
		"Report",
		"Support Settings",
	):
		_ensure_read_perm(doctype, ROLE)
	for parent in ("Issue_Permissions", "UT_Permissions-1", "UTP_Permissions-1"):
		_ensure_permission_condition(parent, ROLE)
	for user, title in [
		(VIEWER, "Cypress Pending Viewer"),
		(REQUIRED, "Cypress Required Actor"),
		(OPTIONAL, "Cypress Optional Actor"),
		(MIXED, "Cypress Mixed Actor"),
	]:
		_ensure_user(user, title, [ROLE, "Desk User", "System Manager", "Dinext_Worker"])
	issue_workflow = _workflow(ISSUE_WORKFLOW, "Issue", "status", "Open", "Closed", "Replied")
	position_workflow = _workflow(
		POSITION_WORKFLOW,
		"User Timesheet Position",
		"workflow_state",
		"Pending Approval",
		"Approved",
		"Editing",
	)
	for name in previous:
		frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
	frappe.db.set_value("Workflow", issue_workflow.name, "is_active", 1, update_modified=False)
	frappe.cache.hdel("workflow", "Issue")
	calendar = _worker()
	start, end = calendar.period
	frappe.get_doc({"doctype": "User Group", "name": GROUP, "user_group_members": [{"user": VIEWER}]}).insert(
		ignore_permissions=True
	)
	frappe.get_doc(
		{
			"doctype": "Worker",
			"wuser": VIEWER,
			"wfullname": "Cypress Pending Viewer",
			"wuser_group": GROUP,
			"wvalid_from": start,
			"wtimesheet_template": calendar.wtimesheet_template,
			"wholiday_list": calendar.wholiday_list,
		}
	).insert(ignore_permissions=True)
	with _engine_paused():
		issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Cypress Required Pending", "status": "Open"}
		).insert(ignore_permissions=True)
		timesheet = frappe.get_doc(
			{
				"doctype": "User Timesheet",
				"timesheet_from": VIEWER,
				"timesheet_from_name": "Cypress Required Pending",
				"ts_valid_from": start,
				"ts_valid_for": end,
				"ut_status": "Pending Approval",
			}
		).insert(ignore_permissions=True)
		positions = []
		for _ in range(2):
			position = frappe.get_doc(
				{
					"doctype": "User Timesheet Position",
					"user_timesheet": timesheet.name,
					"user": VIEWER,
					"status": "Pending Approval",
					"workflow_state": "Editing",
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value(
				"User Timesheet Position",
				position.name,
				{"status": "Pending Approval", "workflow_state": "Pending Approval"},
				update_modified=False,
			)
			positions.append(position)
	frappe.db.set_value(
		"User Timesheet", timesheet.name, "ut_status", "Pending Approval", update_modified=False
	)
	_tasks(issue, issue_workflow, "Open", "Closed", "Replied")
	for index, position in enumerate(positions):
		_tasks(position, position_workflow, "Pending Approval", "Approved", "Editing", second=bool(index))
	from dinext_common.tests.ui_test_helpers import PASSWORD

	fixture = {
		"viewer": VIEWER,
		"password": PASSWORD,
		"issue": issue.name,
		"timesheet": timesheet.name,
		"positions": [row.name for row in positions],
		"required": "Cypress Required Actor",
		"optional": "Cypress Optional Actor",
		"mixed": "Cypress Mixed Actor",
		"viewer_name": "Cypress Pending Viewer",
	}
	frappe.db.set_default(FIXTURE_KEY, json.dumps(fixture))
	frappe.clear_cache()
	return fixture


@whitelist_for_tests
def set_required_pending_optional(doctype: str, optional: int):
	fixture = frappe.db.get_default(FIXTURE_KEY)
	if not fixture or frappe.session.user not in (VIEWER, "Administrator"):
		frappe.throw("Only the fixture viewer may change its display metadata", frappe.PermissionError)
	if doctype not in ("Issue", "User Timesheet Position") or int(optional) not in (0, 1):
		frappe.throw("Unknown fixture metadata")
	workflow = ISSUE_WORKFLOW if doctype == "Issue" else POSITION_WORKFLOW
	state = "Closed" if doctype == "Issue" else "Approved"
	frappe.db.set_value(
		"Workflow Document State", {"parent": workflow, "state": state}, "is_optional_state", int(optional)
	)
	return {"optional": int(optional)}
