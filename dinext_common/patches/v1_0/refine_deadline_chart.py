"""Percentage discipline is not denominated in site currency."""

import frappe


def execute():
	if frappe.db.exists("Dashboard Chart", "Approval Deadline Discipline Trend"):
		chart = frappe.get_doc("Dashboard Chart", "Approval Deadline Discipline Trend")
		if chart.chart_type == "Report" and chart.report_name == "Approval Deadline Discipline":
			chart.db_set("currency", None, update_modified=False)
