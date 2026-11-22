"""Owned fixtures for the My Approvals Desk acceptance tests."""

import json

import frappe
from frappe.utils import add_days, now_datetime

from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_role, _ensure_user
from dinext_common.workflow_approval.scenarios import service

PREFIX = "DINEXT-APPROVAL-WORKSPACE-QA-"
APPROVER = "dinext-approval-workspace.en@example.invalid"
MONITOR = "dinext-approval-workspace.ru@example.invalid"
MONITOR_ROLE = PREFIX + "Monitor"
READER_ROLE = PREFIX + "Reader"
WORKFLOW = PREFIX + "Issue"


def _guard():
	ci_test = (
		frappe.local.site == "ci.test"
		and frappe.conf.allow_tests
		and frappe.conf.workflow_scenarios_test_site
	)
	if (frappe.local.site not in {"localhost", "test_site"} and not ci_test) or frappe.session.user != "Administrator":
		raise frappe.PermissionError("This fixture is restricted to the isolated test administrator")


def cleanup():
	_guard()
	frappe.db.delete("Workflow Task", {"name": ["like", PREFIX + "%"]})
	for doctype in (service.CONTEXT, service.PROCESS):
		frappe.db.delete(doctype, {"reference_doctype": "Issue", "reference_name": ["like", PREFIX + "%"]})
	frappe.db.delete("Has Role", {"parent": WORKFLOW, "parenttype": "Workflow"})
	frappe.db.delete("Workflow", {"name": WORKFLOW})
	frappe.db.delete("Issue", {"name": ["like", PREFIX + "%"]})
	for user in (APPROVER, MONITOR):
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
		frappe.clear_cache(user=user)
	for permission in ("DocPerm", "Custom DocPerm", "DocType Permission Condition"):
		frappe.db.delete(permission, {"role": READER_ROLE})
	frappe.cache.delete_value("doctype_permission_map")
	frappe.db.delete("Role", {"name": ["in", [READER_ROLE, MONITOR_ROLE]]})
	frappe.db.commit()
	return {"cleaned": True}


def _create_active_process(source):
	key = service.source_key(source)
	source_fields = {"reference_doctype": source.doctype, "reference_name": source.name,
		"source_created_at": source.creation}
	process = f"{source.name}-process"
	frappe.get_doc({"doctype": service.PROCESS, "name": process, **source_fields,
		"source_key": key, "active_source_key": key, "workflow": WORKFLOW,
		"status": "Running", "initial_state": "Open", "current_state": "Open"}).db_insert()
	frappe.get_doc({"doctype": service.CONTEXT, "name": key, **source_fields,
		"active_process": process}).db_insert()
	return process


def _grant_fixture_read(doctype):
	# Use the existing permission layer. Adding the first Custom DocPerm would replace standard permissions.
	is_custom = frappe.db.exists("Custom DocPerm", {"parent": doctype})
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm" if is_custom else "DocPerm",
			"parent": doctype,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": READER_ROLE,
			"permlevel": 0,
			"read": 1,
		}
	).db_insert()
	for rule in frappe.get_all("DocType Permission", filters={"ref_doctype": doctype}, pluck="name"):
		condition = {
			"Issue": f"`tabIssue`.`name` like '{PREFIX}%'",
			"Report": (
				"`tabReport`.`name` in ('My Approvals', 'My Approval History', 'Approval Monitoring', "
				"'Approval Load', 'Approval Duration', 'Approval Deadline Discipline')"
			),
			"Kanban Board": "1=0",
		}[doctype]
		frappe.get_doc(
			{
				"doctype": "DocType Permission Condition",
				"parent": rule,
				"parenttype": "DocType Permission",
				"parentfield": "conditions",
				"role": READER_ROLE,
				"perm_level": "Full Access",
				"script": f"conditions = {condition!r}",
			}
		).db_insert()
	frappe.clear_cache(doctype=doctype)
	frappe.cache.delete_value("doctype_permission_map")


def seed():
	_guard()
	cleanup()
	_ensure_role(MONITOR_ROLE)
	_ensure_role(READER_ROLE)
	for doctype in ("Issue", "Report", "Kanban Board"):
		_grant_fixture_read(doctype)
	_ensure_user(APPROVER, "Approval QA English", [READER_ROLE, "Desk User"])
	_ensure_user(MONITOR, "Approval QA Russian", [READER_ROLE, "Desk User", MONITOR_ROLE], dark=True)
	for user, language in ((APPROVER, "en"), (MONITOR, "ru")):
		frappe.db.set_value("User", user, {"language": language, "time_zone": frappe.utils.get_system_timezone()})
		frappe.clear_cache(user=user)
	frappe.get_doc(
		{
			"doctype": "Block Module",
			"parent": APPROVER,
			"parenttype": "User",
			"parentfield": "block_modules",
			"module": "Dinext Common",
		}
	).db_insert()
	frappe.get_doc(
		{"doctype": "Workflow", "name": WORKFLOW, "workflow_name": WORKFLOW, "document_type": "Issue"}
	).db_insert()
	frappe.get_doc(
		{
			"doctype": "Has Role",
			"parent": WORKFLOW,
			"parenttype": "Workflow",
			"parentfield": "custom_approval_monitor_roles",
			"role": MONITOR_ROLE,
		}
	).db_insert()

	now = now_datetime()
	for suffix, status, stamp, completion in (
		("Today", "Working", now, None),
		("Earlier", "Working", add_days(now, -2), None),
		("Manual", "Completed", now, "Manual"),
		("Automatic", "Completed", now, "Automatic Unchanged"),
		("Archived", "Completed", now, "Manual"),
		("Cancelled", "Cancelled", now, None),
		("Outside", "Completed", add_days(now, -31), "Manual"),
	):
		name = PREFIX + suffix
		source_created_at = None
		process = None
		if suffix != "Archived":
			source = frappe.get_doc({"doctype": "Issue", "name": name, "subject": name, "status": "Open"})
			source.db_insert()
			source_created_at = source.creation
			if status == "Working":
				process = _create_active_process(source)
		frappe.get_doc(
			{
				"doctype": "Workflow Task",
				"name": PREFIX + "Task-" + suffix,
				"creation": stamp,
				"modified": stamp,
				"owner": APPROVER,
				"approver": APPROVER,
				"user": APPROVER,
				"workflow": WORKFLOW,
				"workflow_process": process,
				"workflow_state": "Open",
				"reference_doctype": "Issue",
				"reference_name": name,
				"source_created_at": source_created_at,
				"source_title": name,
				"source_deleted_at": now if suffix == "Archived" else None,
				"round_status": "Open" if status == "Working" else "Transitioned",
				"approval_round_id": name,
				"round_manifest": json.dumps({"transitions": []}),
				"status": status,
				"completed_at": stamp if status == "Completed" else None,
				"cancelled_at": stamp if status == "Cancelled" else None,
				"completion_source": completion,
				"deadline_assignment_id": name if suffix == "Today" else None,
				"deadline_started_at": add_days(now, -2) if suffix == "Today" else None,
				"deadline_due_at": add_days(now, -1) if suffix == "Today" else None,
				"deadline_timezone": frappe.utils.get_system_timezone() if suffix == "Today" else None,
			}
		).db_insert()
	frappe.clear_cache(user=APPROVER)
	frappe.db.commit()
	return {"approver": APPROVER, "monitor": MONITOR, "password": PASSWORD, "prefix": PREFIX}
