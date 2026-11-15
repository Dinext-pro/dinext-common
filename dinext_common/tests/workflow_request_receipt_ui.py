"""Synthetic Log Settings data for the native Workflow receipt scenario."""

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import add_days, now_datetime

from dinext_common.workflow_approval.request_receipts import DOCTYPE

PREFIX = "workflow-receipt-cypress-"


def _check_test_site():
	frappe.only_for("System Manager")
	if not (getattr(frappe.local, "dev_server", False) and frappe.conf.get("workflow_scenarios_test_site")):
		raise frappe.PermissionError("Workflow test data requires an isolated development test site")


@whitelist_for_tests(methods=["POST"])
def seed():
	_check_test_site()
	settings = frappe.get_single("Log Settings")
	period = next(row.days for row in settings.logs_to_clear if row.ref_doctype == DOCTYPE)
	suffix = frappe.generate_hash(length=8)
	names = {}
	for label, status, days in (
		("old", "Completed", 6),
		("recent", "Completed", 1),
		("running", "Working", None),
	):
		name = f"{PREFIX}{suffix}-{label}"
		frappe.get_doc({
			"doctype": DOCTYPE, "name": name, "operation": "Vote",
			"initiator": frappe.session.user, "request_digest": name, "status": status,
			"completed_at": add_days(now_datetime(), -days) if days else None,
		}).db_insert()
		names[label] = name
	return {"previous_days": period, "samples": names}


@whitelist_for_tests(methods=["POST"])
def cleanup_receipts(samples: dict):
	_check_test_site()
	from frappe.model.base_document import get_controller

	settings = frappe.get_single("Log Settings")
	entry = next(row for row in settings.logs_to_clear if row.ref_doctype == DOCTYPE)
	get_controller(DOCTYPE).clear_old_logs(entry.days)
	return {label: bool(frappe.db.exists(DOCTYPE, name))
		for label, name in samples.items() if name.startswith(PREFIX)}


@whitelist_for_tests(methods=["POST"])
def restore(previous_days: int, samples: dict):
	_check_test_site()
	settings = frappe.get_single("Log Settings")
	entry = next(row for row in settings.logs_to_clear if row.ref_doctype == DOCTYPE)
	if entry.days != previous_days:
		entry.days = previous_days
		settings.save()
	names = [name for name in samples.values() if name.startswith(PREFIX)]
	if names:
		frappe.db.delete(DOCTYPE, {"name": ("in", names)})
