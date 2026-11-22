# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from dinext_common.workflow_approval.scenarios.records import has_record_permission, require_service_write


class WorkflowDocumentContext(Document):
	def validate(self) -> None:
		require_service_write(self)

	def on_trash(self) -> None:
		require_service_write(self)

	def before_rename(self, old, new, merge=False) -> None:
		require_service_write(self)

	def has_permission(self, permtype="read", *, debug=False, user=None) -> bool:
		if self.flags.ignore_permissions:
			return True
		return has_record_permission(self, ptype=permtype, user=user) and super().has_permission(
			permtype, debug=debug, user=user
		)


def on_doctype_update() -> None:
	frappe.db.add_index(
		"Workflow Document Context", ["reference_doctype", "reference_name", "source_created_at"]
	)
