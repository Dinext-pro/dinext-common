"""Workflow-monitor-role queue report with source permission intersection."""

from frappe import _

from dinext_common.workflow_approval.api import get_monitoring_rows


def execute(filters=None):
	rows = get_monitoring_rows(filters)
	return get_columns(), rows


def get_columns():
	return [
		{"fieldname": "reference_doctype", "label": _("Document Type"), "fieldtype": "Link", "options": "DocType"},
		{"fieldname": "reference_name", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "reference_doctype"},
		{"fieldname": "source_title", "label": _("Title"), "fieldtype": "Data"},
		{"fieldname": "workflow", "label": _("Workflow"), "fieldtype": "Link", "options": "Workflow"},
		{"fieldname": "workflow_state", "label": _("State"), "fieldtype": "Data"},
		{"fieldname": "available_actions", "label": _("Available Actions"), "fieldtype": "Data"},
		{"fieldname": "pending_approvers", "label": _("Pending Approvers"), "fieldtype": "Data"},
		{"fieldname": "active_task_count", "label": _("Active Tasks"), "fieldtype": "Int"},
		{"fieldname": "age_hours", "label": _("Age (hours)"), "fieldtype": "Float"},
		{"fieldname": "round_status", "label": _("Round Status"), "fieldtype": "Data"},
	]
