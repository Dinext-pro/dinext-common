"""Acceptance checks against the approved, non-sensitive localhost snapshot."""
import json
from pathlib import Path

import frappe

_REFERENCE = json.loads(
	(Path(__file__).parent / "fixtures" / "workspace_install_defaults.json").read_text()
)


def verify():
	"""Fail if a fresh full site's saved configuration differs from the reference."""
	doc = frappe.get_doc("Dinext Workspace Settings", "Dinext")
	for field in ("settings_name", "show_frequent_pages", "show_recent_pages"):
		assert doc.get(field) == _REFERENCE[field], (field, doc.get(field))
	assert not doc.roles, "Unexpected role restriction"
	for table in ("items", "sections", "doctype_items"):
		rows = doc.get(table)
		expected_rows = _REFERENCE[table]
		assert len(rows) == len(expected_rows), (table, len(rows), len(expected_rows))
		for actual, expected in zip(rows, expected_rows):
			for field, value in expected.items():
				found = actual.get(field)
				if field in ("attention_filter", "list_filter"):
					found = json.loads(found or "[]")
					value = json.loads(value or "[]")
				assert found == value, (table, actual.idx, field, found, value)
	return {"cards": len(doc.items), "doctype_lists": len(doc.doctype_items), "sections": len(doc.sections)}
