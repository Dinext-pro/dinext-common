"""Align the deadline shortcut with the other approval control reports."""

import frappe

WORKSPACE = "My Approvals"
DEADLINE = "Approval Deadline Discipline"
DURATION = "Approval Duration"


def align_blocks(blocks):
	def shortcut_index(label):
		return next(
			(i for i, block in enumerate(blocks)
			 if block["type"] == "shortcut" and block["data"].get("shortcut_name") == label),
			None,
		)

	deadline = shortcut_index(DEADLINE)
	duration = shortcut_index(DURATION)
	if deadline is None or duration is None or deadline == duration + 1:
		return blocks

	updated = blocks.copy()
	shortcut = updated.pop(deadline)
	updated.insert(duration + (deadline > duration), shortcut)
	return updated


def execute():
	content = frappe.db.get_value("Workspace", WORKSPACE, "content")
	if not content:
		return

	before = frappe.parse_json(content)
	after = align_blocks(before)
	if after != before:
		frappe.db.set_value("Workspace", WORKSPACE, "content", frappe.as_json(after), update_modified=False)
		frappe.cache.delete_key("bootinfo")
