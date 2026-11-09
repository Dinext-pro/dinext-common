"""Keep live transition deadline settings across forced fixture imports."""

import frappe

from dinext_common.workflow_approval.deadlines.metadata import transition_fields


def preserve_deadline_settings(doc, method=None):
	if not frappe.flags.in_fixtures or not frappe.db.exists("Workflow", doc.name):
		return
	existing = frappe.get_doc("Workflow", doc.name)
	by_uuid = {row.get("custom_transition_uuid"): row for row in existing.transitions}
	fields = [row["fieldname"] for row in transition_fields() if row["fieldtype"] != "Section Break"]
	for row in doc.transitions:
		original = by_uuid.get(row.get("custom_transition_uuid"))
		if not original:
			continue
		for field in fields:
			if original.meta.has_field(field):
				row.set(field, original.get(field))
