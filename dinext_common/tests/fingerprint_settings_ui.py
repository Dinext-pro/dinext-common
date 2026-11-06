"""Synthetic Workflow editor fixtures restricted to the dedicated test site."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_role, _ensure_user
from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.exclusions import EXCLUSIONS_FIELD

PREFIX = "_Cypress Fingerprint "
WORKFLOW = PREFIX + "Workflow"
WORKSPACE = PREFIX + "Workspace"
ROLE = PREFIX + "Reader"
EDITOR = "cy.fp.editor@example.com"
READER = "cy.fp.reader@example.com"
MANAGER_PERM = PREFIX + "Manager Permission"
READER_PERM = PREFIX + "Reader Permission"
KANBAN_PERM = PREFIX + "Kanban Permission"
TASK = PREFIX + "Historical Task"


def _guard():
	if not frappe.conf.get("workflow_fingerprint_test_site"):
		raise frappe.PermissionError("Workflow fingerprint fixtures require the isolated test site")
	frappe.only_for("System Manager")


@whitelist_for_tests
def cleanup():
	_guard()
	frappe.db.delete("Workflow Task", {"name": TASK})
	if frappe.db.exists("Workflow", WORKFLOW):
		frappe.delete_doc("Workflow", WORKFLOW, force=True, ignore_permissions=True)
	for email in (EDITOR, READER):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	for name in (MANAGER_PERM, READER_PERM, KANBAN_PERM):
		frappe.db.delete("Custom DocPerm", {"name": name})
	frappe.db.delete("Workspace", {"name": WORKSPACE})
	frappe.db.delete("Role", {"name": ROLE})
	frappe.clear_cache()
	return {"cleaned": True}


@whitelist_for_tests
def seed():
	_guard()
	cleanup()
	_ensure_role(ROLE)
	_ensure_user(EDITOR, "Fingerprint Editor", ["System Manager", "Desk User", "Dinext_UT_Full_Access"])
	_ensure_user(READER, "Fingerprint Reader", [ROLE, "Desk User", "Dinext_UT_Full_Access"])
	frappe.db.set_value("User", EDITOR, "language", "ru")
	frappe.get_doc(
		{
			"doctype": "Workspace",
			"name": WORKSPACE,
			"label": WORKSPACE,
			"title": WORKSPACE,
			"module": "Custom",
			"public": 1,
			"content": "[]",
		}
	).db_insert()
	for email in (EDITOR, READER):
		frappe.db.set_value("User", email, "default_workspace", WORKSPACE)
	for name, role, write in [(MANAGER_PERM, "System Manager", 1), (READER_PERM, ROLE, 0)]:
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"name": name,
				"parent": "Workflow",
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": 0,
				"read": 1,
				"write": write,
				"create": write,
				"delete": write,
			}
		).db_insert()
	# Desk's sidebar also reads Kanban Board; isolate its permission from site customizations.
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"name": KANBAN_PERM,
			"parent": "Kanban Board",
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": "Desk User",
			"permlevel": 0,
			"read": 1,
		}
	).db_insert()
	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW,
			"document_type": "User Timesheet Position",
			"workflow_state_field": "workflow_state",
			"is_active": 0,
			"states": [
				{
					"state": "Editing",
					"doc_status": "0",
					"allow_edit": "System Manager",
					"update_field": "status",
					"update_value": "Editing",
				}
			],
			EXCLUSIONS_FIELD: [{"field_path": "table.utilized_hours"}],
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Workflow Task",
			"name": TASK,
			"workflow": workflow.name,
			"reference_doctype": "User Timesheet Position",
			"reference_name": PREFIX + "Source",
			"workflow_state": "Editing",
			"approver": EDITOR,
			"status": "Completed",
			"round_status": "Transitioned",
			"approval_round_id": PREFIX + "Round",
			"content_fingerprint": "historical-immutable-digest",
			"content_fingerprint_version": "1",
		}
	).db_insert()
	frappe.clear_cache()
	return {"workflow": WORKFLOW, "editor": EDITOR, "reader": READER, "password": PASSWORD}


def _fingerprint(workflow):
	doc = frappe.get_doc(
		{
			"doctype": "User Timesheet Position",
			"user": "Administrator",
			"custom_username": "Owner",
			"workflow_state": "Editing",
			"status": "Editing",
			"table": [{"date": "2039-01-03", "hours": 8, "description": "Work", "utilized_hours": 8}],
		}
	)
	with patch.object(frappe, "get_hooks", return_value=[{"User Timesheet Position": ["custom_username"]}]):
		before = engine.get_content_fingerprint(doc, workflow).digest
		doc.custom_username = "Renamed"
		doc.table[0].utilized_hours = 0
		after_excluded = engine.get_content_fingerprint(doc, workflow).digest
		doc.table[0].hours = 7
		after_hours = engine.get_content_fingerprint(doc, workflow).digest
	return {"base": before, "excluded": after_excluded, "hours": after_hours}


@whitelist_for_tests
def verify_union():
	_guard()
	workflow = frappe.get_doc("Workflow", WORKFLOW)
	result = _fingerprint(workflow)
	assert result["base"] == result["excluded"]
	assert result["base"] != result["hours"]
	return result


@whitelist_for_tests
def history():
	_guard()
	task = frappe.get_doc("Workflow Task", TASK)
	workflow = frappe.get_doc("Workflow", WORKFLOW)
	return {"task": frappe.as_json(task.as_dict()), "fingerprint": _fingerprint(workflow)["base"]}
