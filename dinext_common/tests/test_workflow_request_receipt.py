"""Receipt cleanup uses the row and retention period from standard Frappe Log Settings."""

from unittest.mock import patch

import frappe
from frappe.core.doctype.log_settings.log_settings import _supports_log_clearing
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime


class TestWorkflowRequestReceipt(FrappeTestCase):
	def test_cleanup_uses_completion_time_and_preserves_running_receipts(self):
		doctype = "Workflow Request Receipt"
		self.assertTrue(_supports_log_clearing(doctype))
		now = now_datetime()

		def receipt(status, completed_at):
			name = frappe.generate_hash(length=32)
			doc = frappe.get_doc({
				"doctype": doctype, "name": name, "operation": "Vote",
				"initiator": "Administrator", "request_digest": name, "status": status,
				"completed_at": completed_at,
			})
			doc.creation = add_days(now, -45)
			doc.modified = doc.creation
			doc.owner = doc.modified_by = "Administrator"
			doc.db_insert()
			return name

		old = receipt("Completed", add_days(now, -8))
		failed = receipt("Failed", add_days(now, -8))
		within_week = receipt("Completed", add_days(now, -6))
		fresh = receipt("Completed", add_days(now, -1))
		running = receipt("Working", None)
		settings = frappe.get_single("Log Settings")
		settings.set("logs_to_clear", [row for row in settings.logs_to_clear if row.ref_doctype != doctype])
		settings.add_default_logtypes()
		entry = next(row for row in settings.logs_to_clear if row.ref_doctype == doctype)
		self.assertEqual(entry.days, 7)
		settings.set("logs_to_clear", [entry])
		# The framework's runner commits after every log DocType.
		with patch.object(frappe.db, "commit"):
			settings.clear_logs()
			self.assertFalse(frappe.db.exists(doctype, old))
			self.assertFalse(frappe.db.exists(doctype, failed))
			self.assertTrue(frappe.db.exists(doctype, within_week))
			self.assertTrue(frappe.db.exists(doctype, fresh))
			self.assertTrue(frappe.db.exists(doctype, running))
			entry.days = 0
			settings.add_default_logtypes()
			self.assertEqual(entry.days, 0)
			settings.set("logs_to_clear", [entry])
			settings.clear_logs()
		self.assertFalse(frappe.db.exists(doctype, fresh))
		self.assertTrue(frappe.db.exists(doctype, running))
