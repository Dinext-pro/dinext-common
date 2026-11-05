"""Owned fixtures for the My Approvals Desk acceptance tests."""

import json

import frappe
from frappe.utils import add_days, now_datetime

from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_role, _ensure_user

PREFIX = "DINEXT-APPROVAL-WORKSPACE-QA-"
APPROVER = "dinext-approval-workspace.en@example.invalid"
MONITOR = "dinext-approval-workspace.ru@example.invalid"
MONITOR_ROLE = PREFIX + "Monitor"
READER_ROLE = PREFIX + "Reader"
WORKFLOW = PREFIX + "Issue"


def _guard():
	if frappe.local.site not in {"localhost", "test_site"} or frappe.session.user != "Administrator":
		raise frappe.PermissionError("This fixture is restricted to the local test administrator")


def cleanup():
	_guard()
	frappe.db.delete("Workflow Task", {"name": ["like", PREFIX + "%"]})
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
			"Report": "`tabReport`.`name` in ('My Approvals', 'My Approval History', 'Approval Monitoring', 'Approval Load', 'Approval Duration')",
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
		if suffix != "Archived":
			frappe.get_doc({"doctype": "Issue", "name": name, "subject": name, "status": "Open"}).db_insert()
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
				"workflow_state": "Open",
				"reference_doctype": "Issue",
				"reference_name": name,
				"source_title": name,
				"source_deleted_at": now if suffix == "Archived" else None,
				"round_status": "Open" if status == "Working" else "Transitioned",
				"approval_round_id": name,
				"round_manifest": json.dumps({"transitions": []}),
				"status": status,
				"completed_at": stamp if status == "Completed" else None,
				"cancelled_at": stamp if status == "Cancelled" else None,
				"completion_source": completion,
			}
		).db_insert()
	frappe.clear_cache(user=APPROVER)
	frappe.db.commit()
	return {"approver": APPROVER, "monitor": MONITOR, "password": PASSWORD, "prefix": PREFIX}
