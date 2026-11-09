# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

# import frappe


def execute(filters=None):
	from dinext_common.workflow_approval.deadlines.report import execute as run

	return run(filters)


def execute_snapshot_report(filters: dict | None = None):
	"""Return columns and data for the report.

	This is the main entry point for snapshot report. When 'Synced
	Report' is enabled in report, framework will call this method
	every time the report is refreshed or a filter is updated. It
	accepts the same filters as normal execute. But a utility method -
	get_latest_sync, is also imported.

	"""
	return execute(filters)
