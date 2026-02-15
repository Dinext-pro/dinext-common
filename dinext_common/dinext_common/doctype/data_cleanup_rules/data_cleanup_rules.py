# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from pathlib import Path

import frappe
from frappe.model.document import Document


class DataCleanupRules(Document):
	pass


def update_data_cleanup_server_script():
	"""Update Server Script 'Data Cleanup Daily' from data_cleanup_scheduled_script.py (skips validation)."""
	name = "Data Cleanup Daily"
	if not frappe.db.exists("Server Script", name):
		print(f"Server Script '{name}' not found.")
		return
	path = Path(__file__).resolve().parent / "data_cleanup_scheduled_script.py"
	content = path.read_text(encoding="utf-8")
	doc = frappe.get_doc("Server Script", name)
	doc.script = content
	doc.flags.ignore_validate = True
	doc.save()
	frappe.db.commit()
	print(f"Updated '{name}' with {len(content)} chars from {path.name}")


def run_data_cleanup_daily():
	"""Execute the Data Cleanup Daily Server Script (for testing)."""
	frappe.get_doc("Server Script", "Data Cleanup Daily").execute_scheduled_method()
