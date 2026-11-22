"""Standard Log Settings cleanup for completed workflow requests."""

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, cint, now_datetime


class WorkflowRequestReceipt(Document):
	@staticmethod
	def clear_old_logs(days: int) -> None:
		cutoff = add_days(now_datetime(), -max(0, cint(days)))
		filters = {"status": ("in", ("Completed", "Failed")), "completed_at": ("<", cutoff)}
		while names := frappe.db.get_values(
			"Workflow Request Receipt",
			filters=filters,
			fieldname="name",
			pluck=True,
			for_update=True,
			order_by="completed_at asc, name asc",
			limit=500,
		):
			frappe.db.delete("Workflow Request Receipt", {**filters, "name": ("in", names)})
			if len(names) < 500:
				break
