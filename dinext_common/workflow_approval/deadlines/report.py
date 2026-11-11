"""Permission-filtered detail, due-date cohorts and weekly discipline trend."""

from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _

from dinext_common.workflow_approval.deadlines.discipline import metrics
from dinext_common.workflow_approval.deadlines.errors import display_deadline_error
from dinext_common.workflow_approval.email_presentation import full_name


def execute(filters=None):
	filters = frappe._dict(filters or {})
	result = metrics(filters)
	rows = result["rows"] + [
		row for row in result["all_rows"] if row["discipline_status"] in ("Error", "Unknown")
	]
	groups = {}
	if frappe.db.exists("DocType", "Worker") and frappe.has_permission("Worker", "read"):
		users = list({row["approver"] for row in rows})
		groups = (
			{
				row.wuser: row.wuser_group
				for row in frappe.get_list(
					"Worker",
					filters={"wuser": ["in", users]},
					fields=["wuser", "wuser_group"],
					limit_page_length=0,
				)
			}
			if users
			else {}
		)
	for row in rows:
		row.update(
			approver_name=full_name(row["approver"]),
			user_group=groups.get(row["approver"]),
			state_label=_(row["workflow_state"]),
			result_label=_(row["discipline_status"]),
			deadline_error=display_deadline_error(row.get("deadline_error")),
		)
	if filters.get("result"):
		rows = [row for row in rows if row["discipline_status"] == filters.result]
	group = filters.get("group_by")
	if group in ("approver", "user_group", "workflow", "workflow_state"):
		buckets = defaultdict(list)
		for row in rows:
			buckets[row.get(group) or _("Not specified")].append(row)
		data = []
		for key, items in buckets.items():
			eligible = [
				row for row in items if row["discipline_status"] in ("On Time", "Completed Late", "Overdue")
			]
			data.append(
				dict(
					group=full_name(key) if group == "approver" else _(key),
					count=len(eligible),
					on_time_percent=100
					* sum(row["discipline_status"] == "On Time" for row in eligible)
					/ len(eligible)
					if eligible
					else None,
					late=sum(row["discipline_status"] == "Completed Late" for row in items),
					overdue=sum(row["discipline_status"] == "Overdue" for row in items),
				)
			)
		columns = [
			dict(fieldname=field, label=_(label), fieldtype=kind, width=width)
			for field, label, kind, width in [
				("group", "Group", "Data", 220),
				("count", "Assignments", "Int", 110),
				("on_time_percent", "On-time approvals, %", "Percent", 170),
				("late", "Completed Late", "Int", 150),
				("overdue", "Overdue", "Int", 110),
			]
		]
	else:
		data = rows
		columns = [
			dict(fieldname=field, label=_(label), fieldtype=kind, width=width, **extra)
			for field, label, kind, width, extra in [
				("reference_doctype", "Document Type", "Link", 150, {"options": "DocType"}),
				("reference_name", "Document", "Dynamic Link", 180, {"options": "reference_doctype"}),
				("source_title", "Title", "Data", 200, {}),
				("workflow", "Workflow", "Link", 160, {"options": "Workflow"}),
				("state_label", "State", "Data", 150, {}),
				("approver_name", "Approver", "Data", 180, {}),
				("user_group", "User Group", "Link", 150, {"options": "User Group"}),
				("deadline_started_at", "Assigned At", "Datetime", 165, {}),
				("deadline_due_at", "Deadline", "Datetime", 165, {}),
				("completed_at", "Decision At", "Datetime", 165, {}),
				("result_label", "Result", "Data", 160, {}),
				("delay_hours", "Delay, hours", "Float", 120, {}),
				("deadline_error", "Deadline Calculation Error", "Data", 280, {}),
			]
		]
	weeks = defaultdict(lambda: [0, 0])
	for row in result["rows"]:
		if row["discipline_status"] not in ("On Time", "Completed Late", "Overdue"):
			continue
		week = row["due_date"] - timedelta(days=row["due_date"].weekday())
		weeks[str(week)][0] += row["discipline_status"] == "On Time"
		weeks[str(week)][1] += 1
	labels = sorted(weeks)
	chart = (
		dict(
			data=dict(
				labels=labels,
				datasets=[
					dict(
						name=_("On-time approvals, %"),
						values=[round(100 * weeks[key][0] / weeks[key][1], 1) for key in labels],
					)
				],
			),
			type="line",
			height=230,
		)
	)
	summary = [
		dict(
			label=_(label),
			value=result[key] if result[key] is not None else _("No observations"),
			datatype=("Data" if result[key] is None else "Percent") if key == "on_time_percent" else "Int",
			indicator=indicator,
		)
		for label, key, indicator in [
			("On-time approvals, %", "on_time_percent", "Green"),
			("Overdue", "open_overdue", "Red"),
			("Completed Late", "completed_late", "Orange"),
			("Deadline Calculation Error", "errors", "Orange"),
		]
	]
	return columns, data, None, chart, summary
