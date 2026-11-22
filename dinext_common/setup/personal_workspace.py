"""Migrate only shipped captions and links on personal Workspaces."""

import json

import frappe
from frappe import _
from frappe.utils import strip_html


def localize_workspace(
	legacy_name,
	name,
	*,
	headings,
	widgets,
	public_without_module=False,
	hub_description=None,
):
	if not frappe.db.exists("Workspace", legacy_name):
		return
	if frappe.db.exists("Workspace", name):
		frappe.throw(
			_("Cannot rename Workspace {0}: Workspace {1} already exists.").format(legacy_name, name)
		)

	frappe.rename_doc("Workspace", legacy_name, name, force=True)
	workspace = frappe.get_doc("Workspace", name)
	workspace.title = workspace.label = name
	if public_without_module:
		workspace.module = ""
	update_workspace_captions(workspace, headings, widgets)
	workspace.save(ignore_permissions=True)

	for child in frappe.get_all("Workspace", filters={"parent_page": legacy_name}, pluck="name"):
		frappe.db.set_value("Workspace", child, "parent_page", name)

	if not frappe.db.table_exists("Dinext Workspace Settings Item"):
		return
	for item in frappe.get_all(
		"Dinext Workspace Settings Item",
		filters={"element_type": "Workspace", "target": legacy_name},
		fields=["name", "label", "description"],
	):
		values = {"target": name}
		if item.label == legacy_name:
			values["label"] = name
		if hub_description and item.description == hub_description[0]:
			values["description"] = hub_description[1]
		frappe.db.set_value("Dinext Workspace Settings Item", item.name, values)


def update_workspace_captions(workspace, headings, widgets):
	blocks = json.loads(workspace.content or "[]")
	block_fields = {
		"number_card": ("number_cards", "number_card_name"),
		"chart": ("charts", "chart_name"),
		"shortcut": ("shortcuts", "shortcut_name"),
	}
	for block in blocks:
		data = block["data"]
		if block["type"] == "header":
			caption = strip_html(data["text"]).strip()
			if caption in headings:
				data["text"] = data["text"].replace(caption, headings[caption], 1)
		elif block["type"] in block_fields:
			_, field = block_fields[block["type"]]
			caption = data.get(field)
			if caption in widgets:
				data[field] = widgets[caption]
	for table, _ in block_fields.values():
		for row in workspace.get(table, []):
			if row.label in widgets:
				row.label = widgets[row.label]
	workspace.content = json.dumps(blocks, ensure_ascii=False, separators=(",", ":"))
