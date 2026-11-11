"""Guarded, disposable Timesheets records for mixed-scenario browser acceptance."""

from __future__ import annotations

import frappe
from frappe.utils.password import update_password

CACHE = "workflow_scenario_timesheet_ui_fixture"
POSITION = "User Timesheet Position"
READ_DOCTYPES = ("User Timesheet", POSITION, "Worker", "Timesheet Template", "Working Hours On Date",
	"Holiday List", "Timesheet Settings", "User Group", "Report", "Application For Leave", "Comment", "User")


def _guard():
	frappe.only_for("System Manager")
	if not frappe.conf.get("workflow_scenarios_test_site"):
		raise frappe.PermissionError("Timesheet scenario fixtures require an isolated test site")


def _restore_rules(rows, visible_rows=None):
	settings = frappe.get_single("Timesheet Settings")
	settings.set("position_rules", rows)
	settings.update_child_table("position_rules")
	if visible_rows is not None:
		settings.set("visible_list_statuses", visible_rows)
		settings.update_child_table("visible_list_statuses")


def cleanup():
	_guard()
	data = frappe.cache.get_value(CACHE)
	if not data:
		return {"cleaned": True}
	from dinext_common.tests.ui_test_helpers import _delete_tasks_for

	previous_mute = frappe.flags.get("mute_emails")
	previous_retention = frappe.flags.get("in_workflow_task_retention")
	frappe.flags.mute_emails = True
	try:
		names = data["positions"]
		_delete_tasks_for(POSITION, names)
		_delete_tasks_for("User Timesheet", [data["parent"]])
		for name in names:
			if frappe.db.exists(POSITION, name):
				frappe.delete_doc(POSITION, name, force=True, ignore_permissions=True)
		for doctype in ("Workflow Document Context", "Workflow Process"):
			frappe.db.delete(doctype, {"reference_doctype": POSITION, "reference_name": ("in", names)})
		if frappe.db.table_exists("Timesheet Submission Event"):
			frappe.db.delete("Timesheet Submission Event", {"timesheet": data["parent"]})
		if frappe.db.exists("User Timesheet", data["parent"]):
			frappe.delete_doc("User Timesheet", data["parent"], force=True, ignore_permissions=True)
		for name in data["workflows"]:
			if frappe.db.exists("Workflow", name):
				frappe.delete_doc("Workflow", name, force=True, ignore_permissions=True)
		for name, condition in data["previous_conditions"].items():
			if frappe.db.exists("Workflow", name):
				frappe.db.set_value("Workflow", name, "custom_activation_condition", condition, update_modified=False)
		_restore_rules(data["previous_rules"], data.get("previous_visible_rules"))
		for doctype, name in data["dependencies"]:
			if name and frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		for user in data["users"]:
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)
		for role in data["roles"]:
			frappe.db.delete("Custom DocPerm", {"role": role})
			if frappe.db.exists("Role", role):
				frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
		for action in data["actions"]:
			if frappe.db.exists("Workflow Action Master", action):
				frappe.delete_doc("Workflow Action Master", action, force=True, ignore_permissions=True)
		frappe.cache.delete_value(CACHE)
		frappe.db.commit()
		for doctype in READ_DOCTYPES:
			frappe.clear_cache(doctype=doctype)
		return {"cleaned": True}
	finally:
		frappe.flags.mute_emails = previous_mute
		frappe.flags.in_workflow_task_retention = previous_retention


def seed():
	_guard()
	cleanup()
	from dinext_common.tests.test_workflow_scenario_timesheet_integration import (
		FIELDS,
		TestWorkflowScenarioTimesheetIntegration,
	)
	from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_read_perm

	previous_conditions = {
		row.name: row.custom_activation_condition
		for row in frappe.get_all("Workflow", filters={"document_type": POSITION, "is_active": 1},
			fields=["name", "custom_activation_condition"])
	}
	settings = frappe.get_single("Timesheet Settings")
	previous_rules = [row.as_dict() for row in settings.position_rules or []]
	previous_visible_rules = [row.as_dict() for row in settings.visible_list_statuses or []]
	TestWorkflowScenarioTimesheetIntegration.setUpClass()
	fixture = TestWorkflowScenarioTimesheetIntegration()
	try:
		fixture.setUp()
		settings = frappe.get_single("Timesheet Settings")
		settings.set("visible_list_statuses", [
			{"position_status": "Pending Approval", "open_wf_task": 0},
			{"position_status": "Rejected", "open_wf_task": 0},
		])
		settings.update_child_table("visible_list_statuses")
		for doctype in READ_DOCTYPES:
			_ensure_read_perm(doctype, fixture.roles[0])
		for user in (fixture.reviewer, fixture.other):
			update_password(user, PASSWORD)
			frappe.db.set_value("User", user, "language", "en")
			frappe.clear_cache(user=user)
		worker = frappe.get_doc("Worker", {"wuser": fixture.reviewer})
		data = {
			"parent": fixture.parent.name, "positions": [row.name for row in fixture.positions],
			"workflows": [row.name for row in fixture.workflows], "users": [fixture.reviewer, fixture.other],
			"roles": fixture.roles, "actions": [fixture.action, fixture.reopen],
			"previous_conditions": previous_conditions, "previous_rules": previous_rules,
			"previous_visible_rules": previous_visible_rules,
			"dependencies": [("Worker", worker.name), ("Timesheet Template", fixture.template.name),
				("Working Hours On Date", fixture.template.tt_working_hours_on_date),
				("Holiday List", worker.wholiday_list), ("User Group", worker.wuser_group)],
		}
		# A browser fixture commits its source records; unrelated limit-notification jobs
		# are deliberately excluded while the real approval/task projections remain.
		frappe.db.after_commit.reset()
		for callback in fixture.previous_after_commit:
			frappe.db.after_commit.add(callback)
		frappe.cache.set_value(CACHE, data)
		frappe.db.commit()
		fixture._cleanups.clear()
		return {
			"parent": fixture.parent.name, "positions": data["positions"], "workflows": data["workflows"],
			"state_fields": list(FIELDS), "uuids": [fixture.marker + "-A", fixture.marker + "-B"],
			"actor": fixture.reviewer, "user": fixture.reviewer, "password": PASSWORD,
			"actor_name": fixture.reviewer_name, "other": fixture.other, "other_name": fixture.other_name,
			"action": fixture.action, "reopen_action": fixture.reopen,
			"initial_state": "Pending Approval", "target_state": "Rejected", "comment_is_required": True,
		}
	except Exception:
		frappe.db.rollback()
		frappe.cache.delete_value(CACHE)
		raise
	finally:
		if hasattr(fixture, "previous_engine"):
			frappe.conf.enable_parallel_workflow_approval = fixture.previous_engine
			frappe.flags.mute_emails = fixture.previous_mute
