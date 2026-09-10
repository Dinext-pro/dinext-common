"""Durable repair loop for queued Workflow finalization."""

from __future__ import annotations

import frappe
from frappe import _

from dinext_common.workflow_approval import engine


def _winner(task: object) -> dict | None:
	manifest = engine._parse_manifest(task)
	counts = engine._round_vote_counts(task.approval_round_id, manifest)
	reached = [row for row in counts if row["votes"] >= row["threshold"]]
	return min(
		reached,
		key=lambda row: (int(row["idx"]), row["transition_uuid"]),
		default=None,
	)


def repair_round(round_id: str) -> None:
	names = engine._round_task_names(round_id)
	if not names:
		return
	task = frappe.get_doc("Workflow Task", names[0])
	if task.round_status != "Finalizing":
		return
	winner = _winner(task)
	if not winner:
		engine._mark_conflicted(round_id, _("Finalizing round no longer has a reached transition"))
		return
	source_exists = frappe.db.exists(task.reference_doctype, task.reference_name)
	if not source_exists:
		engine._cancel_round(round_id, _("Source document was deleted during finalization"))
		return
	engine._lock_domain_dependencies(task.reference_doctype, task.reference_name)
	task = frappe.get_doc("Workflow Task", names[0])
	source = frappe.get_doc(task.reference_doctype, task.reference_name, for_update=True)
	context = engine._workflow_context(source)
	if context and context[3] == winner["next_state"]:
		engine._finish_round(round_id, winner)
		engine.reconcile_source(source)
		return
	if task.submission_queue:
		queue = frappe.get_doc("Submission Queue", task.submission_queue)
		if queue.status == "Queued":
			return
		if queue.status == "Failed":
			engine._set_round_values(
				round_id,
				{
					"round_status": "Stalled",
					"finalization_status": "Failed",
					"failure_metadata": engine.serialize_manifest(
						{
							"submission_queue": queue.name,
							"status": "Failed",
						}
					),
				},
			)
			from dinext_common.workflow_approval.projections import (
				close_round_projections,
			)

			close_round_projections(round_id)
			engine._notify_stalled_monitors(source, task)
			frappe.log_error(
				message=queue.exception,
				title=f"Workflow approval finalization failed: {round_id}",
				reference_doctype="Workflow Task",
				reference_name=task.name,
			)
			return
	engine._finalize_round(source, round_id, winner)


def repair_pending_finalizations() -> None:
	"""Repair each distinct durable finalization without aborting the scheduler run."""
	round_ids = frappe.get_all(
		"Workflow Task",
		filters={
			"round_status": "Finalizing",
			"finalization_status": ("in", ("Queued", "Failed")),
		},
		pluck="approval_round_id",
		distinct=True,
	)
	for round_id in filter(None, round_ids):
		try:
			repair_round(round_id)
		except Exception:
			frappe.log_error(
				title=f"Workflow approval finalization repair failed: {round_id}"
			)
