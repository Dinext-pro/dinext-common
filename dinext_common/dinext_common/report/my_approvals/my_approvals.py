"""Source-aware personal approval queue with quorum progress."""

from __future__ import annotations

import json
from collections import Counter

import frappe
from frappe import _
from frappe.utils import date_diff, now_datetime

from dinext_common.workflow_approval.api import get_my_queue
from dinext_common.workflow_approval.notifications import (
	_aware_utc,
	_recipient_timezone,
	get_timezone,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_my_queue()
	completed = _completed_votes({row.approval_round_id for row in rows})
	zone = get_timezone(_recipient_timezone(frappe.session.user))
	today = _aware_utc(now_datetime()).astimezone(zone).date()
	for row in rows:
		manifest = json.loads(row.round_manifest)
		row.available_actions = ", ".join(
			transition["action"] for transition in manifest["transitions"]
		)
		row.progress = _progress(manifest, completed[row.approval_round_id])
		row.age_days = max(0, date_diff(now_datetime(), row.creation))
		row.created_today = (
			_aware_utc(row.creation).astimezone(zone).date() == today
		)
	rows = [row for row in rows if _matches(row, filters)]
	counts = Counter(row.reference_doctype for row in rows)
	chart = {
		"data": {
			"labels": list(counts),
			"datasets": [{"name": _("Pending"), "values": list(counts.values())}],
		},
		"type": "bar",
	}
	return get_columns(), rows, None, chart


def _completed_votes(round_ids: set[str]) -> Counter:
	if not round_ids:
		return Counter()
	return Counter(
		frappe.get_all(
			"Workflow Task",
			filters={
				"approval_round_id": ("in", tuple(round_ids)),
				"status": "Completed",
			},
			pluck="approval_round_id",
		)
	)


def _progress(manifest: dict, completed: int) -> str:
	target = min(
		(int(row["threshold"]) for row in manifest["transitions"]),
		default=0,
	)
	return f"{completed}/{target}"


def _matches(row, filters) -> bool:
	return all(
		(
			not filters.workflow or row.workflow == filters.workflow,
			not filters.reference_doctype
			or row.reference_doctype == filters.reference_doctype,
			not filters.workflow_state or row.workflow_state == filters.workflow_state,
			not filters.action or filters.action in row.available_actions.split(", "),
			not filters.minimum_age or row.age_days >= int(filters.minimum_age),
			not filters.created_today or row.created_today,
		)
	)


def get_columns():
	return [
		{"fieldname": "reference_doctype", "label": _("Document Type"), "fieldtype": "Link", "options": "DocType"},
		{"fieldname": "reference_name", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "reference_doctype"},
		{"fieldname": "source_title", "label": _("Title"), "fieldtype": "Data"},
		{"fieldname": "workflow", "label": _("Workflow"), "fieldtype": "Link", "options": "Workflow"},
		{"fieldname": "workflow_state", "label": _("State"), "fieldtype": "Data"},
		{"fieldname": "available_actions", "label": _("Available Actions"), "fieldtype": "Data"},
		{"fieldname": "progress", "label": _("Progress"), "fieldtype": "Data"},
		{"fieldname": "creation", "label": _("Created"), "fieldtype": "Datetime"},
		{"fieldname": "age_days", "label": _("Age (days)"), "fieldtype": "Int"},
	]
