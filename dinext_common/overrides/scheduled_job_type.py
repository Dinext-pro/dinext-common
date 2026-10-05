"""Route the existing Follow schedules through recipient-aware digests."""

from frappe.core.doctype.scheduled_job_type.scheduled_job_type import ScheduledJobType

FOLLOW_METHODS = {
	f"frappe.desk.form.document_follow.send_{frequency}_updates": (
		f"dinext_common.document_follow.send_{frequency}_updates"
	)
	for frequency in ("hourly", "daily", "weekly")
}


class DinextScheduledJobType(ScheduledJobType):
	def execute(self):
		original_method = self.method
		if not self.server_script:
			self.method = FOLLOW_METHODS.get(original_method, original_method)
		try:
			return super().execute()
		finally:
			self.method = original_method
