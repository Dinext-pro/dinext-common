"""Dev-server fixtures for the parallel-workflow Cypress suite.

Methods are whitelisted only while `bench serve` sets `dev_server`. They create
and delete their own users and documents. They do not change `administrator@dinext.invalid`
and they do not turn `enable_parallel_workflow_approval` off.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import now_datetime
from frappe.utils.password import update_password

PASSWORD = "Cypress-Wf-2026!"
PROTECTED_USER = "administrator@dinext.invalid"
CACHE_PREVIOUS = "cypress_parallel_previous_issue_workflows"
CACHE_FIXTURE = "cypress_parallel_fixture"

APPROVER = "cy.wf.approver@example.com"
APPROVER_B = "cy.wf.approver.b@example.com"
MONITOR = "cy.wf.monitor@example.com"
EXCLUDED = "cy.wf.excluded@example.com"
MANAGER = "cy.wf.manager@example.com"
USERS = (APPROVER, APPROVER_B, MONITOR, EXCLUDED, MANAGER)

ROLE = "_Cypress WF Approver"
ROLE_B = "_Cypress WF Approver B"
ROLE_COHORT = "_Cypress WF Cohort"
ROLE_MONITOR = "_Cypress WF Monitor"
ROLE_MANAGER = "_Cypress WF Manager"
ROLES = (ROLE, ROLE_B, ROLE_COHORT, ROLE_MONITOR, ROLE_MANAGER)

TIMESHEET_ROLE = "Dinext_UTP_Appoval"
AUTHOR = "administrator@dinext.invalid"
LEAVE_FROM = "2026-12-14"
LEAVE_TO = "2026-12-18"
TIMESHEET_FROM = "2026-12-14"
TIMESHEET_TO = "2026-12-20"

WORKFLOWS = (
	"_Cypress WF All",
	"_Cypress WF Reject",
	"_Cypress WF Cohort",
	"_Cypress WF Edit",
	"_Cypress WF Empty",
	"_Cypress WF Split",
)
PERMISSION_DOCS = (
	"Issue_Permissions",
	"UT_Permissions-1",
	"UTP_Permissions-1",
	"AFL_Permissions-1",
)
ISSUE_READ_ROLES = (ROLE, ROLE_B, ROLE_MONITOR, ROLE_MANAGER)
TIMESHEET_READ_ROLES = (ROLE,)


def _permission_as(user: str, doctype: str, ptype: str, doc: str | None = None) -> bool:
	"""Check a permission as that user.

	The DocType Permission hook lists the document as the session user, so the
	``user`` argument alone does not see the approver's read condition.
	Only ``session.user`` is swapped. ``frappe.set_user`` also replaces the
	session id and would invalidate the caller's login.
	"""
	session_user = frappe.session.user
	frappe.session.user = user
	frappe.local.user_perms = None
	frappe.local.role_permissions = {}
	try:
		return bool(frappe.has_permission(doctype, ptype=ptype, doc=doc))
	finally:
		frappe.session.user = session_user
		frappe.local.user_perms = None
		frappe.local.role_permissions = {}


def _assert_flag() -> None:
	if not frappe.conf.get("enable_parallel_workflow_approval"):
		frappe.throw("enable_parallel_workflow_approval must be 1")


def _cache_get(key: str):
	return frappe.cache().get_value(key)


def _cache_set(key: str, value) -> None:
	frappe.cache().set_value(key, value)


def _clear_workflow_cache() -> None:
	frappe.cache.hdel("workflow", "Issue")
	frappe.clear_cache(doctype="Issue")


def _ensure_master(doctype: str, name: str, values: dict) -> None:
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(ignore_permissions=True)


def _ensure_role(role: str) -> None:
	if not frappe.db.exists("Role", role):
		frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)


def _ensure_user(email: str, first_name: str, roles: list[str], *, dark: bool = False) -> None:
	if frappe.db.exists("User", email):
		update_password(email, PASSWORD)
		frappe.db.set_value("User", email, "enabled", 1, update_modified=False)
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
				"new_password": PASSWORD,
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		with patch(
			"raven.raven.doctype.raven_user.raven_user.add_user_to_raven",
			return_value=None,
		):
			user.insert(ignore_permissions=True)
		update_password(email, PASSWORD)
	existing = set(frappe.get_roles(email))
	for role in roles:
		if role not in existing:
			frappe.get_doc(
				{
					"doctype": "Has Role",
					"parent": email,
					"parenttype": "User",
					"parentfield": "roles",
					"role": role,
				}
			).db_insert()
	if dark:
		frappe.db.set_value("User", email, "desk_theme", "Dark", update_modified=False)
	frappe.clear_cache(user=email)


def _ensure_read_perm(doctype: str, role: str) -> None:
	if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
		return
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": doctype,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": role,
			"permlevel": 0,
			"read": 1,
			"write": 0,
			"create": 0,
			"delete": 0,
		}
	).insert(ignore_permissions=True)


def _ensure_issue_perm(role: str) -> None:
	_ensure_read_perm("Issue", role)


def _ensure_permission_condition(parent: str, role: str) -> None:
	if not frappe.db.exists("DocType Permission", parent):
		return
	if frappe.db.exists("DocType Permission Condition", {"parent": parent, "role": role}):
		return
	idx = frappe.db.count("DocType Permission Condition", {"parent": parent}) + 1
	frappe.get_doc(
		{
			"doctype": "DocType Permission Condition",
			"parent": parent,
			"parenttype": "DocType Permission",
			"parentfield": "conditions",
			"idx": idx,
			"role": role,
			"perm_level": "Full Access",
			"script": 'conditions = "true"',
		}
	).db_insert()
	frappe.cache.delete_value("doctype_permission_map")


def _remove_permission_conditions() -> None:
	frappe.db.delete(
		"DocType Permission Condition",
		{"parent": ["in", list(PERMISSION_DOCS)], "role": ["in", list(ROLES)]},
	)
	frappe.cache.delete_value("doctype_permission_map")


def _transition(
	action: str,
	next_state: str,
	*,
	policy: str,
	uuid: str,
	allowed: str,
	comment_required: int = 0,
	condition: str | None = None,
	allow_self_approval: int = 1,
	reset_on_change: int = 0,
) -> dict:
	_ensure_master("Workflow Action Master", action, {"workflow_action_name": action})
	_ensure_master("Workflow State", next_state, {"workflow_state_name": next_state})
	return {
		"state": "Open",
		"action": action,
		"next_state": next_state,
		"allowed": allowed,
		"allow_self_approval": allow_self_approval,
		"condition": condition,
		"custom_transition_uuid": uuid,
		"custom_parallel_approval_policy": policy,
		"custom_comment_is_required": comment_required,
		"custom_reset_on_change": reset_on_change,
	}


def _insert_workflow(name: str, transitions: list[dict], states: list[str] | None = None) -> object:
	if frappe.db.exists("Workflow", name):
		frappe.delete_doc("Workflow", name, force=True, ignore_permissions=True)
	state_names = states or ["Open", "Closed"]
	for state in state_names:
		_ensure_master("Workflow State", state, {"workflow_state_name": state})
	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": name,
			"document_type": "Issue",
			"workflow_state_field": "status",
			"is_active": 0,
			"send_email_alert": 0,
			"states": [
				{"state": state, "doc_status": "0", "allow_edit": "All"} for state in state_names
			],
			"transitions": transitions,
			"custom_approval_monitor_roles": [{"role": ROLE_MONITOR}],
		}
	)
	workflow.insert(ignore_permissions=True)
	return workflow


def _activate(name: str) -> None:
	for existing in frappe.get_all(
		"Workflow",
		filters={"document_type": "Issue", "is_active": 1},
		pluck="name",
	):
		if existing != name:
			frappe.db.set_value("Workflow", existing, "is_active", 0, update_modified=False)
	frappe.db.set_value("Workflow", name, "is_active", 1, update_modified=False)
	_clear_workflow_cache()


def _issue(subject: str):
	return frappe.get_doc(
		{"doctype": "Issue", "subject": subject, "status": "Open"}
	).insert(ignore_permissions=True)


def _working_tasks(name: str) -> list[dict]:
	return frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": "Issue",
			"reference_name": name,
			"status": "Working",
		},
		fields=["name", "approver", "round_status", "approval_round_id", "round_manifest"],
		order_by="approver asc",
	)


def _threshold(tasks: list[dict]) -> int | None:
	if not tasks or not tasks[0].get("round_manifest"):
		return None
	manifest = json.loads(tasks[0].round_manifest)
	transitions = manifest.get("transitions") or []
	if not transitions:
		return None
	return transitions[0].get("threshold")


def _manual_task(
	*,
	doctype: str,
	name: str,
	workflow: str,
	state: str,
	approver: str | None,
	round_status: str,
	status: str,
	round_id: str,
	action: str | None = None,
	next_state: str | None = None,
	transition_uuid: str | None = None,
	allowed_role: str | None = None,
) -> str:
	from dinext_common.workflow_approval.policy import make_task_name

	task_name = make_task_name(round_id, approver or "")
	if frappe.db.exists("Workflow Task", task_name):
		return task_name
	task = frappe.get_doc(
		{
			"doctype": "Workflow Task",
			"name": task_name,
			"doc": doctype,
			"wt_docname": name,
			"reference_doctype": doctype,
			"reference_name": name,
			"status": status,
			"round_status": round_status,
			"finalization_status": "Not Required",
			"workflow": workflow,
			"workflow_state": state,
			"state": state,
			"approval_round_id": round_id,
			"approver": approver,
			"user": approver,
			"source_title": name,
			"source_owner": frappe.session.user,
			"source_created_at": now_datetime(),
			"round_manifest": json.dumps({"transitions": []}),
			"completed_at": now_datetime() if status == "Completed" else None,
			"action": action,
			"completion_source": "Manual" if status == "Completed" else None,
		}
	)
	if action:
		_ensure_master("Workflow Action Master", action, {"workflow_action_name": action})
	for state_name in (state, next_state):
		if state_name:
			_ensure_master("Workflow State", state_name, {"workflow_state_name": state_name})
	if action and transition_uuid:
		task.append(
			"available_workflow_transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state or state,
				"transition_uuid": transition_uuid,
				"allowed_role": allowed_role or ROLE,
				"policy": "Any",
				"threshold": 1,
				"comment_is_required": 0,
			},
		)
	task.insert(ignore_permissions=True)
	return task.name


@contextmanager
def _engine_paused():
	from dinext_common.workflow_approval import lifecycle

	original = lifecycle._should_handle
	lifecycle._should_handle = lambda _doc: False
	try:
		yield
	finally:
		lifecycle._should_handle = original


def _delete_tasks_for(doctype: str, names: list[str]) -> None:
	if not names:
		return
	task_names = frappe.get_all(
		"Workflow Task",
		filters={"reference_doctype": doctype, "reference_name": ["in", names]},
		pluck="name",
	)
	frappe.flags.in_workflow_task_retention = True
	for task_name in task_names:
		frappe.delete_doc("Workflow Task", task_name, force=True, ignore_permissions=True)
	frappe.db.delete("ToDo", {"reference_type": doctype, "reference_name": ["in", names]})
	frappe.db.delete(
		"Workflow Action",
		{"reference_doctype": doctype, "reference_name": ["in", names]},
	)


def _our_issues() -> list[str]:
	return frappe.get_all(
		"Issue",
		filters={"subject": ["like", "Cypress %"]},
		pluck="name",
	)


def _our_timesheets() -> list[str]:
	return frappe.get_all(
		"User Timesheet",
		filters={"ts_valid_from": TIMESHEET_FROM, "ts_valid_for": TIMESHEET_TO, "timesheet_from": AUTHOR},
		pluck="name",
	)


def _our_leaves() -> list[str]:
	return frappe.get_all(
		"Application For Leave",
		filters={"alfrom_date": LEAVE_FROM, "alto_date": LEAVE_TO, "alreasons": "Cypress parallel workflow"},
		pluck="name",
	)


def _our_positions(timesheets: list[str]) -> list[str]:
	if not timesheets:
		return []
	return frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": ["in", timesheets]},
		pluck="name",
	)


@whitelist_for_tests
def cleanup_parallel_workflow_cypress() -> dict:
	"""Delete documents and users this suite created, then restore Issue workflows."""
	_assert_flag()
	previous = _cache_get(CACHE_PREVIOUS) or []
	with _engine_paused():
		issues = _our_issues()
		timesheets = _our_timesheets()
		positions = _our_positions(timesheets)
		leaves = _our_leaves()
		_delete_tasks_for("Issue", issues)
		_delete_tasks_for("User Timesheet Position", positions)
		_delete_tasks_for("Application For Leave", leaves)
		_delete_tasks_for("User Timesheet", timesheets)
		previous_import = frappe.flags.in_import
		frappe.flags.in_import = True
		try:
			for doctype, names in (
				("User Timesheet Position", positions),
				("User Timesheet", timesheets),
				("Application For Leave", leaves),
				("Issue", issues),
			):
				for name in names:
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		finally:
			frappe.flags.in_import = previous_import
	for name in WORKFLOWS:
		if frappe.db.exists("Workflow", name):
			frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
			frappe.delete_doc("Workflow", name, force=True, ignore_permissions=True)
	_remove_permission_conditions()
	for role in ROLES:
		for perm in frappe.get_all(
			"Custom DocPerm",
			filters={"role": role},
			pluck="name",
		):
			frappe.delete_doc("Custom DocPerm", perm, force=True, ignore_permissions=True)
	for email in USERS:
		if email == PROTECTED_USER or not frappe.db.exists("User", email):
			continue
		frappe.db.delete("Has Role", {"parent": email, "parenttype": "User"})
		try:
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		except Exception:
			frappe.db.set_value("User", email, "enabled", 0, update_modified=False)
	for name in previous:
		if frappe.db.exists("Workflow", name):
			frappe.db.set_value("Workflow", name, "is_active", 1, update_modified=False)
	_cache_set(CACHE_PREVIOUS, [])
	_cache_set(CACHE_FIXTURE, {})
	_clear_workflow_cache()
	frappe.clear_cache()
	return {"cleaned": True}


def _duplicate_uuid_result() -> dict:
	name = "_Cypress WF Duplicate"
	try:
		_insert_workflow(
			name,
			[
				_transition("Cypress Split", "Replied", policy="Any", uuid="cypress-dup-uuid", allowed=ROLE),
				_transition("Cypress Split", "Closed", policy="Any", uuid="cypress-dup-uuid", allowed=ROLE_B),
			],
			states=["Open", "Replied", "Closed"],
		)
	except frappe.ValidationError as exc:
		return {"rejected": True, "message": str(exc)}
	if frappe.db.exists("Workflow", name):
		frappe.delete_doc("Workflow", name, force=True, ignore_permissions=True)
	return {"rejected": False, "message": "Workflow saved with a repeated UUID"}


def _seed_timesheet(workflow_name: str) -> dict:
	worker = frappe.db.get_value("Worker", {"wuser": AUTHOR}, "name")
	leave_type = frappe.db.get_value("Type Of Leave", {}, "name")
	if not worker or not leave_type:
		frappe.throw("Cypress timesheet seed needs a Worker for the author and a Type Of Leave")
	with _engine_paused():
		timesheet = frappe.get_doc(
			{
				"doctype": "User Timesheet",
				"timesheet_from": AUTHOR,
				"timesheet_from_name": "Cypress Timesheet",
				"ts_valid_from": TIMESHEET_FROM,
				"ts_valid_for": TIMESHEET_TO,
				"ut_status": "На согласовании",
			}
		).insert(ignore_permissions=True)
		position = frappe.get_doc(
			{
				"doctype": "User Timesheet Position",
				"user_timesheet": timesheet.name,
				"user": AUTHOR,
				"status": "На согласовании",
				"period": "Cypress parallel workflow",
			}
		).insert(ignore_permissions=True)
		leave = frappe.get_doc(
			{
				"doctype": "Application For Leave",
				"alworker": worker,
				"lauser": AUTHOR,
				"altype_of_leave": leave_type,
				"alfrom_date": LEAVE_FROM,
				"alto_date": LEAVE_TO,
				"status": "На согласовании",
				"alreasons": "Cypress parallel workflow",
			}
		).insert(ignore_permissions=True)
	round_id = frappe.generate_hash(length=40)
	_manual_task(
		doctype="User Timesheet Position",
		name=position.name,
		workflow=workflow_name,
		state="На согласовании",
		approver=APPROVER,
		round_status="Open",
		status="Working",
		round_id=round_id,
		action="Cypress Position",
		next_state="Согласовано",
		transition_uuid="cypress-position",
		allowed_role=ROLE,
	)
	_manual_task(
		doctype="User Timesheet Position",
		name=position.name,
		workflow=workflow_name,
		state="На согласовании",
		approver=APPROVER_B,
		round_status="Open",
		status="Working",
		round_id=round_id,
		action="Cypress Position",
		next_state="Согласовано",
		transition_uuid="cypress-position",
		allowed_role=ROLE,
	)
	leave_round = frappe.generate_hash(length=40)
	_manual_task(
		doctype="Application For Leave",
		name=leave.name,
		workflow=workflow_name,
		state="На согласовании",
		approver=APPROVER,
		round_status="Open",
		status="Working",
		round_id=leave_round,
		action="Cypress Leave",
		next_state="Согласовано",
		transition_uuid="cypress-leave",
		allowed_role=ROLE,
	)
	_manual_task(
		doctype="Application For Leave",
		name=leave.name,
		workflow=workflow_name,
		state="На согласовании",
		approver=APPROVER_B,
		round_status="Open",
		status="Working",
		round_id=leave_round,
		action="Cypress Leave",
		next_state="Согласовано",
		transition_uuid="cypress-leave",
		allowed_role=ROLE,
	)
	return {
		"timesheet": timesheet.name,
		"position": position.name,
		"leave": leave.name,
		"pending_names": ["Cypress Approver", "Cypress Approver B"],
	}


def _seed_conflicted(issue_name: str, workflow_name: str) -> str:
	return _manual_task(
		doctype="Issue",
		name=issue_name,
		workflow=workflow_name,
		state="Open",
		approver=APPROVER,
		round_status="Conflicted",
		status="Working",
		round_id=frappe.generate_hash(length=40),
	)


@whitelist_for_tests
def seed_parallel_workflow_cypress() -> dict:
	"""Create isolated Issue rounds and a timesheet chain. Returns the fixture."""
	_assert_flag()
	cleanup_parallel_workflow_cypress()
	_assert_flag()
	ikhmel_modified = frappe.db.get_value("User", PROTECTED_USER, "modified")
	previous = frappe.get_all(
		"Workflow",
		filters={"document_type": "Issue", "is_active": 1},
		pluck="name",
	)
	_cache_set(CACHE_PREVIOUS, previous)
	for role in ROLES:
		_ensure_role(role)
	_ensure_user(APPROVER, "Cypress Approver", [ROLE, ROLE_COHORT, "Desk User", TIMESHEET_ROLE], dark=True)
	_ensure_user(APPROVER_B, "Cypress Approver B", [ROLE, ROLE_B, "Desk User"])
	_ensure_user(MONITOR, "Cypress Monitor", [ROLE_MONITOR, "Desk User"])
	_ensure_user(EXCLUDED, "Cypress Excluded", [ROLE_COHORT, "Desk User"])
	_ensure_user(MANAGER, "Cypress Manager", [ROLE_MANAGER, "System Manager", "Desk User"])
	for role in ISSUE_READ_ROLES:
		_ensure_issue_perm(role)
		_ensure_permission_condition("Issue_Permissions", role)
	for role in ROLES:
		_ensure_read_perm("Report", role)
		_ensure_read_perm("Support Settings", role)
	for role in TIMESHEET_READ_ROLES:
		for parent in ("UT_Permissions-1", "UTP_Permissions-1", "AFL_Permissions-1"):
			_ensure_permission_condition(parent, role)
	frappe.clear_cache()

	all_workflow = _insert_workflow(
		"_Cypress WF All",
		[_transition("Cypress Approve", "Closed", policy="All", uuid="cypress-all", allowed=ROLE)],
	)
	_activate(all_workflow.name)
	all_issue = _issue("Cypress all cohort")
	all_tasks = _working_tasks(all_issue.name)

	reject_workflow = _insert_workflow(
		"_Cypress WF Reject",
		[
			_transition(
				"Cypress Reject",
				"Closed",
				policy="Any",
				uuid="cypress-reject",
				allowed=ROLE,
				comment_required=1,
				condition="doc.owner != frappe.session.user",
				allow_self_approval=0,
			)
		],
	)
	_activate(reject_workflow.name)
	reject_issue = _issue("Cypress read only reject")
	reject_tasks = _working_tasks(reject_issue.name)
	can_write = _permission_as(APPROVER, "Issue", "write", reject_issue.name)

	cohort_workflow = _insert_workflow(
		"_Cypress WF Cohort",
		[_transition("Cypress Cohort", "Closed", policy="All", uuid="cypress-cohort", allowed=ROLE_COHORT)],
	)
	_activate(cohort_workflow.name)
	from dinext_common.workflow_approval import engine

	def allow_read(_doc, user):
		return user == APPROVER

	with patch.object(engine, "_has_source_read_permission", side_effect=allow_read):
		cohort_issue = _issue("Cypress cohort filter")
	cohort_tasks = _working_tasks(cohort_issue.name)

	edit_workflow = _insert_workflow(
		"_Cypress WF Edit",
		[
			_transition(
				"Cypress Edit",
				"Closed",
				policy="Any",
				uuid="cypress-edit",
				allowed=ROLE,
				reset_on_change=0,
			)
		],
	)
	_activate(edit_workflow.name)
	edit_issue = _issue("Cypress mid round edit")
	edit_issue.subject = "Cypress mid round edit changed"
	edit_issue.save(ignore_permissions=True)
	edit_tasks = _working_tasks(edit_issue.name)

	empty_workflow = _insert_workflow(
		"_Cypress WF Empty",
		[_transition("Cypress Empty", "Closed", policy="Any", uuid="", allowed=ROLE)],
	)
	empty_workflow.reload()
	empty_uuid = empty_workflow.transitions[0].custom_transition_uuid
	empty_workflow.save(ignore_permissions=True)
	empty_workflow.reload()
	empty_uuid_again = empty_workflow.transitions[0].custom_transition_uuid
	_activate(empty_workflow.name)
	empty_issue = _issue("Cypress empty uuid")
	empty_issue.subject = "Cypress empty uuid saved"
	empty_issue.save(ignore_permissions=True)
	empty_tasks = _working_tasks(empty_issue.name)

	duplicate = _duplicate_uuid_result()
	split_workflow = _insert_workflow(
		"_Cypress WF Split",
		[
			_transition("Cypress Split", "Replied", policy="Any", uuid="cypress-split-a", allowed=ROLE),
			_transition("Cypress Split", "Closed", policy="Any", uuid="cypress-split-b", allowed=ROLE_B),
		],
		states=["Open", "Replied", "Closed"],
	)
	split_labels = [row.action for row in split_workflow.transitions]
	_activate(split_workflow.name)
	split_one = _issue("Cypress split one role")
	split_both = _issue("Cypress split both roles")
	split_buttons = _issue("Cypress split buttons")

	_activate(all_workflow.name)
	queue_issue = _issue("Cypress queue")
	conflicted_issue = _issue("Cypress conflicted")
	with _engine_paused():
		history_issue = _issue("Cypress history")
		quiet_issue = _issue("Cypress no personal task")
	_seed_conflicted(conflicted_issue.name, all_workflow.name)
	history_task = _manual_task(
		doctype="Issue",
		name=history_issue.name,
		workflow=all_workflow.name,
		state="Open",
		approver=APPROVER,
		round_status="Transitioned",
		status="Completed",
		round_id=frappe.generate_hash(length=40),
		action="Cypress Approve",
	)
	monitor_round = frappe.generate_hash(length=40)
	_manual_task(
		doctype="Issue",
		name=queue_issue.name,
		workflow=all_workflow.name,
		state="Open",
		approver=None,
		round_status="Open",
		status="Working",
		round_id=monitor_round,
	)
	_manual_task(
		doctype="Issue",
		name=queue_issue.name,
		workflow=all_workflow.name,
		state="Open",
		approver=MONITOR,
		round_status="Open",
		status="Working",
		round_id=monitor_round,
		action="Cypress Approve",
		next_state="Closed",
		transition_uuid="cypress-all",
		allowed_role=ROLE,
	)

	utp_workflow = (
		frappe.db.get_value(
			"Workflow",
			{"document_type": "User Timesheet Position", "is_active": 1},
			"name",
		)
		or all_workflow.name
	)
	timesheet = _seed_timesheet(utp_workflow)
	holiday_read = _permission_as(APPROVER, "Holiday List", "read")
	project_write = _permission_as(APPROVER, "Project", "write")
	ikhmel_after = frappe.db.get_value("User", PROTECTED_USER, "modified")

	fixture = {
		"password": PASSWORD,
		"approver": APPROVER,
		"approver_b": APPROVER_B,
		"monitor": MONITOR,
		"excluded": EXCLUDED,
		"manager": MANAGER,
		"approver_name": "Cypress Approver",
		"approver_b_name": "Cypress Approver B",
		"ikhmel_modified_unchanged": ikhmel_modified == ikhmel_after,
		"holiday_list_read": holiday_read,
		"project_write": project_write,
		"can_write_issue": can_write,
		"all_workflow": all_workflow.name,
		"all_issue": all_issue.name,
		"all_action": "Cypress Approve",
		"all_uuid": "cypress-all",
		"all_threshold": _threshold(all_tasks),
		"all_approvers": [row.approver for row in all_tasks],
		"reject_workflow": reject_workflow.name,
		"reject_issue": reject_issue.name,
		"reject_action": "Cypress Reject",
		"reject_uuid": "cypress-reject",
		"reject_task": reject_tasks[0].name if reject_tasks else None,
		"cohort_issue": cohort_issue.name,
		"cohort_threshold": _threshold(cohort_tasks),
		"cohort_approvers": [row.approver for row in cohort_tasks],
		"edit_workflow": edit_workflow.name,
		"edit_issue": edit_issue.name,
		"edit_action": "Cypress Edit",
		"edit_uuid": "cypress-edit",
		"edit_round_status": edit_tasks[0].round_status if edit_tasks else None,
		"empty_issue": empty_issue.name,
		"empty_uuid": empty_uuid,
		"empty_uuid_again": empty_uuid_again,
		"empty_round_status": empty_tasks[0].round_status if empty_tasks else None,
		"duplicate_rejected": duplicate["rejected"],
		"duplicate_message": duplicate["message"],
		"split_workflow": split_workflow.name,
		"split_action": "Cypress Split",
		"split_labels": split_labels,
		"split_uuid_a": "cypress-split-a",
		"split_uuid_b": "cypress-split-b",
		"split_one": split_one.name,
		"split_both": split_both.name,
		"split_buttons": split_buttons.name,
		"queue_issue": queue_issue.name,
		"history_issue": history_issue.name,
		"history_task": history_task,
		"conflicted_issue": conflicted_issue.name,
		"quiet_issue": quiet_issue.name,
		**timesheet,
	}
	_cache_set(CACHE_FIXTURE, fixture)
	return fixture


@whitelist_for_tests
def activate_issue_workflow(name: str) -> dict:
	"""Make one Cypress Issue workflow the active one for the next vote."""
	_assert_flag()
	if name not in WORKFLOWS:
		frappe.throw("Only a Cypress Issue workflow can be activated")
	_activate(name)
	return {"workflow": name}


@whitelist_for_tests
def task_snapshot(task_name: str) -> dict:
	"""Return vote fields for a task the current user is allowed to read."""
	_assert_flag()
	task = frappe.db.get_value(
		"Workflow Task",
		task_name,
		["name", "approver", "round_status", "status", "vote_comment", "action"],
		as_dict=True,
	)
	if not task:
		frappe.throw("Workflow Task not found")
	if frappe.session.user not in {task.approver, "Administrator"} and "System Manager" not in set(
		frappe.get_roles()
	):
		frappe.throw("Not allowed to read this task", frappe.PermissionError)
	return {
		"name": task.name,
		"round_status": task.round_status,
		"status": task.status,
		"vote_comment": task.vote_comment,
		"action": task.action,
	}
