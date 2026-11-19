"""Lock project totals before Workflow locks an invoice and its approval task."""

import frappe

INVOICE_TYPES = frozenset({"Purchase Invoice", "Sales Invoice"})


def lock_dependencies(doctype: str, name: str) -> list[tuple[str, str]]:
	if doctype not in INVOICE_TYPES:
		return []

	projects = set(frappe.get_all(
		f"{doctype} Item", filters={"parent": name, "parenttype": doctype}, pluck="project",
	))
	if doctype == "Sales Invoice":
		projects.add(frappe.db.get_value(doctype, name, "project"))
	return [("Project", project) for project in sorted(filter(None, projects))]
