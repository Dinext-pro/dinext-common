"""Open approval load by approver for workflows the user monitors."""

from frappe import _
from frappe.utils import now_datetime

from dinext_common.workflow_approval.api import (
	approver_display_names,
	canonical_choice,
	get_monitored_tasks,
)
from dinext_common.workflow_approval.control import aggregate_load, load_chart

CHART_CHOICES = ("Open count", "Open age")


def execute(filters=None):
	filters = filters or {}
	tasks = get_monitored_tasks(
		{
			"status": "Working",
			"round_status": "Open",
			"workflow": filters.get("workflow"),
			"reference_doctype": filters.get("reference_doctype"),
		}
	)
	names = approver_display_names(
		[task.get("approver") or task.get("user") for task in tasks]
	)
	rows = aggregate_load(tasks, names, now_datetime())
	view = canonical_choice(filters.get("chart"), CHART_CHOICES)
	return get_columns(), rows, None, _translated_chart(load_chart(rows, view))


def get_columns():
	return [
		{"fieldname": "approver_name", "label": _("Approver"), "fieldtype": "Data"},
		{"fieldname": "open_tasks", "label": _("Open tasks"), "fieldtype": "Int"},
		{"fieldname": "open_rounds", "label": _("Open rounds"), "fieldtype": "Int"},
		{"fieldname": "avg_age_hours", "label": _("Average age (hours)"), "fieldtype": "Float"},
		{"fieldname": "max_age_hours", "label": _("Maximum age (hours)"), "fieldtype": "Float"},
		{"fieldname": "oldest_document", "label": _("Oldest Document"), "fieldtype": "Data"},
	]


def _translated_chart(chart):
	for dataset in chart["data"]["datasets"]:
		dataset["name"] = _(dataset["name"])
	return chart
