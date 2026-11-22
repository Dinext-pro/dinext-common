"""Development-only fixture for the delegated Workflow decision in Desk."""

import re

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import today

from dinext_common.tests.ui_test_helpers import (
	PASSWORD,
	_delete_tasks_for,
	_ensure_master,
	_ensure_role,
	_ensure_user,
)


def _fixture_names(marker: str) -> tuple[str, str, str]:
	if frappe.session.user != "Administrator" or not frappe.local.dev_server:
		raise frappe.PermissionError("A development Administrator must manage this fixture")
	if not re.fullmatch(r"wf-audit-[a-z0-9]{12}", marker):
		raise frappe.ValidationError("Invalid Workflow audit fixture name")
	return f"{marker}-deputy@example.invalid", f"{marker}-approver@example.invalid", f"Approve {marker}"


def _grant_read_permissions(role: str, project: str) -> None:
	# Respect an existing custom permission table. Creating its first row
	# would override the native permissions for every other user.
	for doctype in ("Issue", "Report", "Kanban Board"):
		layer = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"
		frappe.get_doc({
			"doctype": layer, "parent": doctype, "parenttype": "DocType", "parentfield": "permissions",
			"role": role, "read": 1, "permlevel": 0, "if_owner": int(doctype in ("Issue", "Kanban Board")),
		}).db_insert()
		frappe.clear_cache(doctype=doctype)
	if (
		frappe.db.exists("DocType", "DocType Permission")
		and frappe.db.exists("DocType Permission", "Issue_Permissions")
	):
		project_condition = (frappe.qb.DocType("Issue").project == project).get_sql()
		frappe.get_doc({
			"doctype": "DocType Permission Condition", "parent": "Issue_Permissions",
			"parenttype": "DocType Permission", "parentfield": "conditions",
			"role": role, "perm_level": "Full Access", "script": f"conditions = {project_condition!r}",
		}).db_insert()
		frappe.cache.delete_value("doctype_permission_map")


@whitelist_for_tests(methods=["POST"])
def cleanup(marker: str) -> None:
	deputy, approver, action = _fixture_names(marker)
	issues = frappe.get_all("Issue", filters={"project": marker}, pluck="name")
	_delete_tasks_for("Issue", issues)
	if issues:
		for doctype in ("Workflow Process", "Workflow Document Context"):
			frappe.db.delete(doctype, {"reference_doctype": "Issue", "reference_name": ("in", issues)})
	for issue in issues:
		frappe.delete_doc("Issue", issue, force=True, ignore_permissions=True)
	frappe.delete_doc_if_exists("Workflow", marker, force=True)
	frappe.delete_doc_if_exists("Workflow Action Master", action, force=True)
	frappe.delete_doc_if_exists("Project", marker, force=True)
	frappe.db.delete("User Delegate", {"delegate": deputy, "delegator": approver})
	frappe.db.delete("Workflow Request Receipt", {"initiator": approver})
	for user in (deputy, approver):
		frappe.delete_doc_if_exists("User", user, force=True)
	for doctype in ("DocPerm", "Custom DocPerm"):
		frappe.db.delete(doctype, {"role": ("in", [marker, marker + " Desk"])})
	frappe.delete_doc_if_exists("Role", marker + " Desk", force=True)
	if frappe.db.exists("DocType", "DocType Permission Condition"):
		frappe.db.delete("DocType Permission Condition", {"role": marker})
	frappe.delete_doc_if_exists("Role", marker, force=True)
	frappe.cache.hdel("workflow", "Issue")
	frappe.cache.delete_value("doctype_permission_map")
	for doctype in ("Issue", "Report", "Kanban Board"):
		frappe.clear_cache(doctype=doctype)


@whitelist_for_tests(methods=["POST"])
def seed(marker: str) -> dict:
	deputy, approver, action = _fixture_names(marker)
	if "dinext_deputies" not in frappe.get_installed_apps():
		raise frappe.ValidationError("The Workflow delegation browser test requires dinext_deputies")
	if not frappe.conf.get("enable_parallel_workflow_approval"):
		raise frappe.ValidationError("Enable parallel Workflow approvals for the browser test")

	previous_mute = frappe.flags.get("mute_emails")
	frappe.flags.mute_emails = True
	try:
		deputy_label = f"Audit Deputy {marker}"
		approver_label = f"Audit Approver {marker}"
		_ensure_role(marker)
		_grant_read_permissions(marker, marker)
		deputy_role = marker + " Desk"
		_ensure_role(deputy_role)
		layer = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": "Kanban Board"}) else "DocPerm"
		frappe.get_doc({
			"doctype": layer, "parent": "Kanban Board", "parenttype": "DocType", "parentfield": "permissions",
			"role": deputy_role, "read": 1, "permlevel": 0, "if_owner": 1,
		}).db_insert()
		frappe.clear_cache(doctype="Kanban Board")
		_ensure_user(deputy, deputy_label, ["Projects User", deputy_role])
		_ensure_user(approver, approver_label, ["System Manager", marker])
		frappe.get_doc({
			"doctype": "User Delegate",
			"delegate": deputy,
			"delegator": approver,
			"from_date": today(),
			"to_date": today(),
		}).insert(ignore_permissions=True)

		company = frappe.db.get_value("Company", {}, "name")
		frappe.get_doc({
			"doctype": "Project", "name": marker, "project_name": marker,
			"company": company, "status": "Open",
		}).db_insert()
		_ensure_master("Workflow Action Master", action, {"workflow_action_name": action})
		for state in ("Open", "Closed"):
			_ensure_master("Workflow State", state, {"workflow_state_name": state})
		workflow = frappe.get_doc({
			"doctype": "Workflow", "workflow_name": marker, "document_type": "Issue",
			"workflow_state_field": "status", "is_active": 1, "send_email_alert": 0,
			"custom_activation_condition": f"doc.project == {marker!r}",
			"states": [
				{"state": state, "doc_status": 0, "allow_edit": "System Manager"}
				for state in ("Open", "Closed")
			],
			"transitions": [{
				"state": "Open", "next_state": "Closed", "action": action,
				"allowed": marker, "allow_self_approval": 1,
				"custom_parallel_approval_policy": "Any",
			}],
		}).insert(ignore_permissions=True)
		# Frappe assigns new document ownership from the current user.
		# Use the fixture approver as author without changing the bootstrap SID.
		previous_user = frappe.session.user
		previous_user_perms = frappe.local.user_perms
		previous_role_permissions = frappe.local.role_permissions
		try:
			frappe.session.user = approver
			frappe.local.user_perms = None
			frappe.local.role_permissions = {}
			issue = frappe.get_doc({
				"doctype": "Issue", "subject": f"Delegated decision {marker}", "status": "Open",
				"project": marker, "company": company,
			}).insert(ignore_permissions=True)
		finally:
			frappe.session.user = previous_user
			frappe.local.user_perms = previous_user_perms
			frappe.local.role_permissions = previous_role_permissions
		task = frappe.get_doc("Workflow Task", {
			"reference_doctype": "Issue", "reference_name": issue.name,
			"workflow": workflow.name, "approver": approver, "status": "Working",
		})
		return {
			"action": action, "deputy": deputy, "deputy_label": deputy_label,
			"approver": approver, "approver_label": approver_label, "password": PASSWORD,
			"workflow": workflow.name, "issue": issue.name, "task": task.name,
		}
	finally:
		frappe.flags.mute_emails = previous_mute
