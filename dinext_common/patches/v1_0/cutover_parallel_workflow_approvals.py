"""Version-gated coordinator for the parallel workflow approval cutover."""

from __future__ import annotations

import frappe


def execute() -> None:
	if frappe.conf.get("parallel_workflow_cutover_receipt"):
		return
	if not frappe.conf.get("run_parallel_workflow_cutover"):
		return

	from dinext_common.workflow_approval.migration import execute_cutover

	execute_cutover(frappe.conf.get("parallel_workflow_cutover_backup") or "")
