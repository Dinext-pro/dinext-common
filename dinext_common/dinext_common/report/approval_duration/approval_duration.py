"""Completed approval duration and open-round charts for monitored workflows."""

from frappe import _
from frappe.utils import add_days, getdate, now_datetime

from dinext_common.workflow_approval.api import (
	approver_display_names,
	canonical_choice,
	get_monitored_tasks,
	get_monitoring_rows,
)
from dinext_common.workflow_approval.control import (
	aggregate_duration,
	aggregate_open_groups,
	duration_chart,
)

CHART_CHOICES = ("Completed duration", "Open rounds")
GROUP_CHOICES = ("Document Type", "Approver", "Workflow")


def execute(filters=None):
	filters = filters or {}
	start, end = _period(filters)
	group_by = canonical_choice(filters.get("group_by"), GROUP_CHOICES)
	view = canonical_choice(filters.get("chart"), CHART_CHOICES)
	scope = {
		"workflow": filters.get("workflow"),
		"reference_doctype": filters.get("reference_doctype"),
	}
	tasks = [
		task
		for task in get_monitored_tasks(
			{
				"status": "Completed",
				"completed_since": start,
				**scope,
			}
		)
		if _on_or_before(task.get("completed_at"), end)
	]
	open_rounds = (
		get_monitoring_rows({"round_status": "Open", **scope})
		if view == "Open rounds"
		else []
	)
	names = approver_display_names(_approvers(tasks, open_rounds))
	rows = aggregate_duration(tasks, group_by, names)
	chart_rows = (
		aggregate_open_groups(open_rounds, group_by, names)
		if view == "Open rounds"
		else rows
	)
	return get_columns(), rows, None, _translated_chart(duration_chart(chart_rows, view))


def get_columns():
	return [
		{"fieldname": "group_label", "label": _("Group"), "fieldtype": "Data"},
		{"fieldname": "manual_count", "label": _("Manual Decisions"), "fieldtype": "Int"},
		{"fieldname": "automatic_count", "label": _("Automatic Decisions"), "fieldtype": "Int"},
		{"fieldname": "avg_hours", "label": _("Average duration (hours)"), "fieldtype": "Float"},
		{"fieldname": "max_hours", "label": _("Maximum duration (hours)"), "fieldtype": "Float"},
	]


def _period(filters):
	today = getdate(now_datetime())
	start = getdate(filters.get("from_date") or add_days(today, -30))
	end = getdate(filters.get("to_date") or today)
	return start, end


def _on_or_before(value, end) -> bool:
	if not value:
		return False
	return getdate(value) <= end


def _approvers(tasks, open_rounds) -> list[str]:
	idents = [task.get("approver") or task.get("user") for task in tasks]
	for row in open_rounds:
		for approver in (row.get("pending_approvers") or "").split(","):
			idents.append(approver.strip())
	return idents


def _translated_chart(chart):
	for dataset in chart["data"]["datasets"]:
		dataset["name"] = _(dataset["name"])
	return chart
