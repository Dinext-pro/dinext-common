"""Development-only fixture for the delegated Workflow decision in Desk."""

import re

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import today

from dinext_common.tests.ui_test_helpers import (
	PASSWORD,
	_delete_tasks_for,
	_ensure_master,
	_ensure_user,
)


def _fixture_names(marker: str) -> tuple[str, str, str]:
	if frappe.session.user != "Administrator" or not frappe.local.dev_server:
		raise frappe.PermissionError("A development Administrator must manage this fixture")
	if not re.fullmatch(r"wf-audit-[a-z0-9]{12}", marker):
		raise frappe.ValidationError("Invalid Workflow audit fixture name")
	return f"{marker}-deputy@example.invalid", f"{marker}-approver@example.invalid", f"Approve {marker}"


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
	frappe.cache.hdel("workflow", "Issue")


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
		_ensure_user(deputy, deputy_label, ["Projects User"])
		_ensure_user(approver, approver_label, ["System Manager", "Support Team"])
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
				"allowed": "System Manager", "allow_self_approval": 1,
				"condition": f"frappe.session.user == {approver!r}",
				"custom_parallel_approval_policy": "Any",
			}],
		}).insert(ignore_permissions=True)
		issue = frappe.get_doc({
			"doctype": "Issue", "subject": f"Delegated decision {marker}", "status": "Open",
			"project": marker, "company": company,
		}).insert(ignore_permissions=True)
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
