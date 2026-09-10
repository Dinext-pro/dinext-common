# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WorkflowTask(Document):
	def validate(self) -> None:
		if self.is_new():
			if not self.flags.ignore_permissions:
				frappe.throw(
					"Workflow Task can only be created by the approval engine",
					frappe.PermissionError,
				)
			return
		frappe.throw(
			"Workflow Task is an immutable approval audit record",
			frappe.PermissionError,
		)

	def on_trash(self) -> None:
		if not getattr(frappe.flags, "in_workflow_task_retention", False):
			frappe.throw(
				"Workflow Task can only be deleted by configured retention",
				frappe.PermissionError,
			)


def on_doctype_update() -> None:
	"""Create composite indexes used by approval queues and reconciliation."""
	for fields in (
		["reference_doctype", "reference_name", "round_status"],
		["approver", "status", "creation"],
		["workflow", "round_status"],
		["transition_uuid", "approver", "status", "completed_at"],
		["finalization_status", "modified"],
	):
		frappe.db.add_index("Workflow Task", fields)
