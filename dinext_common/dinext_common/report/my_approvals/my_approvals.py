"""Source-aware personal approval queue with quorum progress."""

from __future__ import annotations

import json
from collections import Counter

import frappe
from frappe import _
from frappe.utils import date_diff, now_datetime

from dinext_common.workflow_approval.api import get_personal_queue

def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_personal_queue(filters, include_transitions=True)
	completed = _completed_votes({row.approval_round_id for row in rows})
	for row in rows:
		manifest = json.loads(row.round_manifest)
		row.available_actions = ", ".join(
			dict.fromkeys(transition["action"] for transition in row.available_transitions)
		)
		row.progress_transitions = [
			{**transition, "votes": completed[(row.approval_round_id, transition.get("transition_uuid"))]}
			for transition in manifest["transitions"]
		]
		row.progress = _progress(row.progress_transitions)
		row.age_days = max(0, date_diff(now_datetime(), row.creation))
	rows = [row for row in rows if _matches(row, filters)]
	counts = Counter(row.reference_doctype for row in rows)
	chart = {
		"data": {
			"labels": [_(label) for label in counts],
			"datasets": [{"name": _("Pending"), "values": list(counts.values())}],
		},
		"type": "bar",
	}
	return get_columns(), rows, None, chart


def _completed_votes(round_ids: set[str]) -> Counter:
	if not round_ids:
		return Counter()
	return Counter(
		(row.approval_round_id, row.transition_uuid)
		for row in frappe.get_all(
			"Workflow Task",
			filters={
				"approval_round_id": ("in", tuple(round_ids)),
				"status": "Completed",
			},
			fields=["approval_round_id", "transition_uuid"],
		)
	)


def _progress(transitions: list[dict]) -> str:
	return "; ".join(
		f"{row['action']} {row['votes']}/{int(row['threshold'])}"
		for row in transitions
	)


def _matches(row, filters) -> bool:
	return all(
		(
			not filters.workflow or row.workflow == filters.workflow,
			not filters.reference_doctype
			or row.reference_doctype == filters.reference_doctype,
			not filters.workflow_state or row.workflow_state == filters.workflow_state,
			not filters.action
			or any(transition["action"] == filters.action for transition in row.available_transitions),
			not filters.minimum_age or row.age_days >= int(filters.minimum_age),
		)
	)


def get_columns():
	return [
		{"fieldname": "reference_doctype", "label": _("Document Type"), "fieldtype": "Data"},
		{"fieldname": "reference_name", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "reference_doctype"},
		{"fieldname": "source_title", "label": _("Title"), "fieldtype": "Data"},
		{"fieldname": "workflow", "label": _("Workflow"), "fieldtype": "Data"},
		{"fieldname": "workflow_state", "label": _("State"), "fieldtype": "Data"},
		{"fieldname": "available_actions", "label": _("Available Actions"), "fieldtype": "Data"},
		{"fieldname": "progress", "label": _("Progress"), "fieldtype": "Data"},
		{"fieldname": "creation", "label": _("Created"), "fieldtype": "Datetime"},
		{"fieldname": "age_days", "label": _("Age (days)"), "fieldtype": "Int"},
	]
