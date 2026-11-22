# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WorkflowTask(Document):
	def has_permission(self, permtype="read", *, debug=False, user=None) -> bool:
		# Document.check_permission must not restore a denied audit read from a
		# pre-existing DocShare. Explicit engine writes already use this flag.
		if self.flags.ignore_permissions:
			return True
		from dinext_common.workflow_approval.permissions import has_workflow_task_permission

		return has_workflow_task_permission(self, ptype=permtype, user=user) and super().has_permission(
			permtype, debug=debug, user=user
		)

	def validate(self) -> None:
		if self.is_new():
			if not self.flags.ignore_permissions:
				frappe.throw(
					_("Workflow Task can only be created by the approval engine"),
					frappe.PermissionError,
				)
			return
		frappe.throw(
			_("Workflow Task is an immutable approval audit record"),
			frappe.PermissionError,
		)

	def on_trash(self) -> None:
		if not getattr(frappe.flags, "in_workflow_task_retention", False):
			frappe.throw(
				_("Workflow Task can only be deleted by configured retention"),
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
