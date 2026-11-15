"""Compatibility for earlier Timesheet workflow RPC addresses."""

from __future__ import annotations

import frappe


@frappe.whitelist()
def get_timesheet_position_actions(timesheet_name: str):
	from dinext_timesheets.workflow_approval import get_timesheet_position_actions as get_actions

	return get_actions(timesheet_name)


@frappe.whitelist(methods=["POST"])
def apply_timesheet_position_action(
	timesheet_name: str, action: str, comment: object = None, request_id: str | None = None,
	track_progress: bool = False, targets: object = None,
):
	from dinext_timesheets.workflow_approval import apply_timesheet_position_action as apply_action

	return apply_action(timesheet_name, action, comment, request_id, track_progress, targets)
