# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DataCleanupRules(Document):
	def before_import(self):
		if not frappe.flags.in_fixtures or not frappe.db.get_singles_dict(self.doctype):
			return
		saved = frappe.get_single(self.doctype)
		for field in self.meta.get_table_fields():
			self.set(field.fieldname, [row.as_dict() for row in saved.get(field.fieldname)])
