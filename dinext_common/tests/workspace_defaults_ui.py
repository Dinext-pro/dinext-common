"""Temporary browser-test user for the real settings form and Hub."""
import secrets

import frappe
from frappe.utils.password import update_password

USER = "workspace-defaults-ui@example.invalid"
_SETUP_STATE = "workspace_defaults_ui_setup_state"


def seed():
	if frappe.request:
		raise frappe.PermissionError("Browser fixtures are CLI-only")
	if not frappe.conf.allow_tests:
		raise frappe.PermissionError("Browser acceptance requires an explicit test site")
	from dinext_common.tests.workspace_install_acceptance import verify

	counts = verify()
	if not frappe.cache().get_value(_SETUP_STATE):
		frappe.cache().set_value(_SETUP_STATE, {
			"applications": frappe.get_all("Installed Application", fields=["name", "is_setup_complete"]),
			"system": frappe.db.get_single_value("System Settings", "setup_complete"),
		})
	for application in frappe.get_all("Installed Application", pluck="name"):
		frappe.db.set_value("Installed Application", application, "is_setup_complete", 1)
	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	if frappe.db.exists("User", USER):
		frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
	user = frappe.get_doc({
		"doctype": "User", "email": USER, "first_name": "Workspace acceptance",
		"enabled": 1, "user_type": "System User", "language": "en", "send_welcome_email": 0,
	}).insert(ignore_permissions=True)
	roles = {"System Manager", "Workspace Manager", "Projects User", "Projects Manager", "Employee"}
	settings = frappe.get_doc("Dinext Workspace Settings", "Dinext")
	for item in settings.items:
		if item.element_type == "DocType":
			roles.update(p.role for p in frappe.get_meta(item.target).permissions if p.read)
		elif item.element_type == "Workspace" and frappe.db.exists("Workspace", item.target):
			roles.update(row.role for row in frappe.get_doc("Workspace", item.target).roles)
	roles -= {"All", "Guest", "Administrator"}
	user.add_roles(*(role for role in sorted(roles) if frappe.db.exists("Role", role)))
	password = secrets.token_urlsafe(24)
	update_password(USER, password)
	frappe.db.commit()
	return {"user": USER, "password": password, **counts}


def cleanup():
	if frappe.request:
		raise frappe.PermissionError("Browser fixtures are CLI-only")
	if not frappe.conf.allow_tests:
		raise frappe.PermissionError("Browser acceptance requires an explicit test site")
	if frappe.db.exists("User", USER):
		frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
	state = frappe.cache().get_value(_SETUP_STATE)
	if state:
		for application in state["applications"]:
			frappe.db.set_value("Installed Application", application["name"], "is_setup_complete", application["is_setup_complete"])
		frappe.db.set_single_value("System Settings", "setup_complete", state["system"])
		frappe.cache().delete_value(_SETUP_STATE)
	frappe.db.commit()
