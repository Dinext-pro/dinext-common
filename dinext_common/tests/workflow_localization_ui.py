"""Disposable language-specific Desk users for workflow acceptance tests."""

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_user


_USERS = {lang: f"cy.workflow.locales.{lang}@example.com" for lang in ("en", "ru")}


@whitelist_for_tests
def seed():
	if frappe.session.user != "Administrator":
		frappe.throw("Administrator is required to seed workflow test users.", frappe.PermissionError)
	for lang, email in _USERS.items():
		_ensure_user(email, f"Cypress Workflow {lang}", ["System Manager"])
		frappe.db.set_value("User", email, "language", lang, update_modified=False)
		frappe.clear_cache(user=email)
	return {"users": _USERS, "password": PASSWORD}


@whitelist_for_tests
def cleanup():
	if frappe.session.user != "Administrator":
		frappe.throw("Administrator is required to clean up workflow test users.", frappe.PermissionError)
	for email in _USERS.values():
		frappe.delete_doc("User", email, ignore_permissions=True, ignore_missing=True, force=True)
