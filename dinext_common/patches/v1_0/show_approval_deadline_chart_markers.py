import frappe


def execute():
	doctype = "Dashboard Chart"
	name = "Approval Deadline Discipline Trend"
	chart = frappe.db.get_value(
		doctype,
		{
			"name": name,
			"is_standard": 1,
			"chart_type": "Report",
			"report_name": "Approval Deadline Discipline",
			"type": "Line",
			"use_report_chart": 1,
		},
		"custom_options",
		as_dict=True,
	)
	if not chart:
		return

	options = frappe.parse_json(chart.custom_options) or {}
	line_options = options.get("lineOptions") or {}
	if line_options.get("showDots"):
		return

	options["lineOptions"] = {**line_options, "showDots": True}
	frappe.db.set_value(doctype, name, "custom_options", frappe.as_json(options), update_modified=False)
