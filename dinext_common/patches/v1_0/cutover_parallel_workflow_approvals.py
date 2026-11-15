"""Version-gated coordinator for the parallel workflow approval cutover."""

from __future__ import annotations

import frappe


def execute() -> None:
	from dinext_common.workflow_approval.migration import cutover_complete, execute_cutover

	if not frappe.conf.get("run_parallel_workflow_cutover") or cutover_complete():
		return

	prior_receipt = frappe.conf.get("parallel_workflow_cutover_receipt") or {}
	execute_cutover(frappe.conf.get("parallel_workflow_cutover_backup") or prior_receipt.get("backup") or "")
