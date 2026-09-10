"""Source-aware personal approval history report."""

from __future__ import annotations

from collections import Counter

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime

from dinext_common.workflow_approval.api import get_my_history


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.from_date or add_days(now_datetime(), -30))
	to_date = getdate(filters.to_date or now_datetime())
	rows = get_my_history()
	rows = [row for row in rows if _matches(row, filters, from_date, to_date)]
	for row in rows:
		row.event_at = row.completed_at or row.cancelled_at
		comment = (row.vote_comment or "")[:240]
		row.vote_comment = f"'{comment}" if comment.startswith(("=", "+", "-", "@")) else comment
	return get_columns(), rows, None, _chart(rows)


def _chart(rows):
	sources = sorted({row.completion_source or row.status for row in rows})
	dates = sorted({str(getdate(row.event_at)) for row in rows if row.event_at})
	counts = Counter(
		(str(getdate(row.event_at)), row.completion_source or row.status)
		for row in rows
		if row.event_at
	)
	return {
		"data": {
			"labels": dates,
			"datasets": [
				{
					"name": source,
					"values": [counts[(date, source)] for date in dates],
				}
				for source in sources
			],
		},
		"type": "line",
	}


def _matches(row, filters, from_date, to_date):
	event_at = row.completed_at or row.cancelled_at
	completed_date = getdate(event_at) if event_at else None
	return all(
		(
			not filters.workflow or row.workflow == filters.workflow,
			not filters.reference_doctype
			or row.reference_doctype == filters.reference_doctype,
			not filters.action or row.action == filters.action,
			not filters.completion_source
			or row.completion_source == filters.completion_source,
			not completed_date or from_date <= completed_date <= to_date,
		)
	)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Task"), "fieldtype": "Link", "options": "Workflow Task"},
		{"fieldname": "reference_doctype", "label": _("Document Type"), "fieldtype": "Link", "options": "DocType"},
		{"fieldname": "reference_name", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "reference_doctype"},
		{"fieldname": "source_title", "label": _("Title"), "fieldtype": "Data"},
		{"fieldname": "workflow", "label": _("Workflow"), "fieldtype": "Link", "options": "Workflow"},
		{"fieldname": "action", "label": _("Action"), "fieldtype": "Data"},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
		{"fieldname": "completion_source", "label": _("Completion Source"), "fieldtype": "Data"},
		{"fieldname": "event_at", "label": _("Completed At"), "fieldtype": "Datetime"},
		{"fieldname": "vote_comment", "label": _("Comment"), "fieldtype": "Small Text"},
		{"fieldname": "reused_from_workflow_task", "label": _("Reused From"), "fieldtype": "Link", "options": "Workflow Task"},
	]
