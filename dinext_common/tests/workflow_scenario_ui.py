"""Disposable records for multiple active Workflow schemas on an isolated local site."""

from __future__ import annotations

import frappe

from dinext_common.tests.ui_test_helpers import (
	PASSWORD,
	_delete_tasks_for,
	_engine_paused,
	_ensure_master,
	_ensure_read_perm,
	_ensure_role,
	_ensure_user,
)

PREFIX = "_Cypress Scenario"
SOURCE = "Cypress Scenario Source"
USER = "cy.workflow.scenarios@example.com"
RUSSIAN_USER = "cy.workflow.scenarios.ru@example.com"
DESIGNER_USER = "cy.workflow.scenarios.designer@example.com"
PROGRESS_USER = "cy.workflow.scenarios.progress@example.com"
ROLE = PREFIX + " Approver"
EDITOR = PREFIX + " Editor A"
OTHER_EDITOR = PREFIX + " Editor B"
DESIGNER = PREFIX + " Designer"
CACHE = "workflow_scenario_ui_previous"
FIELDS = ("scenario_state_a", "scenario_state_b")
STATES = ("Scenario Waiting A", "Scenario Done A", "Scenario Waiting B", "Scenario Done B")


def _guard():
	frappe.only_for("System Manager")
	if not frappe.conf.get("workflow_scenarios_test_site"):
		raise frappe.PermissionError("Workflow scenario fixtures require an isolated test site")


def cleanup():
	_guard()
	names = frappe.get_all(SOURCE, pluck="name") if frappe.db.exists("DocType", SOURCE) else []
	with _engine_paused():
		_delete_tasks_for(SOURCE, names)
		for doctype in ("Workflow Document Context", "Workflow Process"):
			if names:
				frappe.db.delete(doctype, {"reference_doctype": SOURCE, "reference_name": ("in", names)})
		for name in names:
			frappe.delete_doc(SOURCE, name, force=True, ignore_permissions=True)
		for suffix in (" A", " B"):
			if frappe.db.exists("Workflow", PREFIX + suffix):
				frappe.delete_doc("Workflow", PREFIX + suffix, force=True, ignore_permissions=True)
	for name in frappe.cache.get_value(CACHE) or []:
		if frappe.db.exists("Workflow", name):
			frappe.db.set_value("Workflow", name, "is_active", 1, update_modified=False)
	frappe.cache.delete_value(CACHE)
	for user in (USER, RUSSIAN_USER, DESIGNER_USER):
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	for role in (ROLE, EDITOR, OTHER_EDITOR, DESIGNER):
		for doctype in ("Custom DocPerm", "DocType Permission Condition"):
			frappe.db.delete(doctype, {"role": role})
		if frappe.db.exists("Role", role):
			frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
	if frappe.db.exists("DocType", SOURCE):
		frappe.delete_doc("DocType", SOURCE, force=True, ignore_permissions=True)
	for state in STATES:
		if frappe.db.exists("Workflow State", state):
			frappe.delete_doc("Workflow State", state, force=True, ignore_permissions=True)
	frappe.clear_cache()
	return {"cleaned": True}


def seed():
	_guard()
	cleanup()
	for role in (ROLE, EDITOR, OTHER_EDITOR, DESIGNER):
		_ensure_role(role)
	_ensure_user(USER, "Scenario Reviewer", [ROLE, EDITOR, "Desk User"])
	_ensure_user(RUSSIAN_USER, "Scenario Reviewer RU", [ROLE, EDITOR, "Desk User"])
	frappe.db.set_value("User", RUSSIAN_USER, "language", "ru", update_modified=False)
	_ensure_user(DESIGNER_USER, "Scenario Designer", [DESIGNER, "System Manager", "Desk User"])
	frappe.get_doc({"doctype": "Custom DocPerm", "parent": "Workflow", "parenttype": "DocType",
		"parentfield": "permissions", "role": DESIGNER, "permlevel": 0, "read": 1, "write": 1, "create": 1}).insert(ignore_permissions=True)
	for doctype in ("Report", "Kanban Board"):
		_ensure_read_perm(doctype, ROLE)
	frappe.get_doc({"doctype": "DocType", "name": SOURCE, "module": "Dinext Common", "custom": 1,
		"autoname": "hash", "title_field": "title", "track_changes": 0,
		"fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
			{"fieldname": "status", "label": "Status", "fieldtype": "Data", "default": "Open"},
			*({"fieldname": field, "label": field, "fieldtype": "Link", "options": "Workflow State", "read_only": 1}
				for field in FIELDS)],
		"permissions": [{"role": ROLE, "read": 1}, {"role": EDITOR, "read": 1, "write": 1}],
	}).insert(ignore_permissions=True)
	active = frappe.get_all("Workflow", filters={"document_type": SOURCE, "is_active": 1}, pluck="name")
	frappe.cache.set_value(CACHE, active)
	for name in active:
		frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
	for state in STATES:
		_ensure_master("Workflow State", state, {"workflow_state_name": state,
			"style": "Warning" if "Waiting" in state else "Success"})
	_ensure_master("Workflow Action Master", "Approve", {"workflow_action_name": "Approve"})
	for index, suffix in enumerate(("A", "B")):
		field, start, end = FIELDS[index], STATES[index * 2], STATES[index * 2 + 1]
		orders = frappe.get_all("Workflow", filters={"document_type": SOURCE}, pluck="custom_selection_order")
		order = max((int(value or 0) for value in orders), default=0) + 1
		condition = f'doc.title.startswith("{PREFIX} {suffix}") and (doc.get("{field}") != "{end}" or doc.title.endswith("Repeat"))'
		frappe.get_doc({"doctype": "Workflow", "workflow_name": PREFIX + " " + suffix,
			"document_type": SOURCE, "workflow_state_field": field, "is_active": 1,
			"override_status": 0, "send_email_alert": 0, "custom_activation_condition": condition,
			"custom_selection_order": order,
			"states": [{"state": start, "doc_status": "0", "allow_edit": EDITOR if index == 0 else OTHER_EDITOR},
				{"state": end, "doc_status": "0", "allow_edit": EDITOR if index == 0 else OTHER_EDITOR}],
			"transitions": [{"state": start, "action": "Approve", "next_state": end,
				"allowed": ROLE, "allow_self_approval": 1, "custom_parallel_approval_policy": "Any",
				"custom_transition_uuid": "cypress-scenario-" + suffix.lower(), "custom_comment_is_required": index}],
		}).insert(ignore_permissions=True)
	frappe.clear_cache()
	docs = {}
	for suffix, purpose in (("A", "Form"), ("B", "Form"), ("A", "List"), ("B", "List"), ("A", "Repeat")):
		doc = frappe.get_doc({"doctype": SOURCE, "title": f"{PREFIX} {suffix} {purpose}", "status": "Open"})
		doc.insert(ignore_permissions=True)
		docs[suffix.lower() + "_" + purpose.lower()] = doc.name
	return {"user": USER, "russian_user": RUSSIAN_USER, "designer": DESIGNER_USER,
		"password": PASSWORD, "doctype": SOURCE, "documents": docs, "state_fields": FIELDS,
		"workflows": [PREFIX + " A", PREFIX + " B"], "uuids": ["cypress-scenario-a", "cypress-scenario-b"]}


def seed_progress_user():
	_guard()
	_ensure_user(PROGRESS_USER, "Scenario Progress Reviewer", ["System Manager", "Desk User"])
	return {"user": PROGRESS_USER, "password": PASSWORD}


def cleanup_progress_user():
	_guard()
	if frappe.db.exists("User", PROGRESS_USER):
		frappe.delete_doc("User", PROGRESS_USER, force=True, ignore_permissions=True)
	return {"cleaned": True}
