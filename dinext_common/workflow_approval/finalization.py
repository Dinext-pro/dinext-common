"""Durable repair loop for queued Workflow finalization."""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from dinext_common.workflow_approval import engine, queued_submission

SUBMISSION_GRACE = timedelta(minutes=2)


def _winner(task: object) -> dict | None:
	return engine._reached_winner(task.approval_round_id, engine._parse_manifest(task))


def _lock_round(round_id):
	names = engine._round_task_names(round_id)
	if not names:
		return None, None
	task = frappe.get_doc("Workflow Task", names[0])
	engine._lock_domain_dependencies(task.reference_doctype, task.reference_name)
	try:
		source = frappe.get_doc(task.reference_doctype, task.reference_name, for_update=True)
	except frappe.DoesNotExistError:
		source = None
	return frappe.get_doc("Workflow Task", task.name, for_update=True), source


def _queue_for_round(task, source):
	if not task.submission_queue:
		return None
	queue = frappe.db.get_value(
		"Submission Queue", task.submission_queue,
		["name", "ref_doctype", "ref_docname", "status", "job_id", "creation"],
		as_dict=True, for_update=True,
	)
	if (
		queue and (queue.ref_doctype, queue.ref_docname) == (source.doctype, source.name)
		and get_datetime(queue.creation) >= get_datetime(source.creation)
	):
		return queue
	return None


def _stall_submission(task, source, queue, data, *, orphan=False):
	from dinext_common.workflow_approval.projections import close_round_projections

	queue_name = task.submission_queue
	if orphan:
		if queue:
			frappe.db.set_value("Submission Queue", queue.name, {
				"status": "Failed",
				"ended_at": now_datetime(),
				"exception": _("The background submission no longer has an active job."),
			}, update_modified=False)
		if not frappe.db.exists("Submission Queue", {
			"ref_doctype": source.doctype, "ref_docname": source.name, "status": "Queued",
		}):
			source.unlock()
	failure = {
		"submission_queue": queue_name,
		"status": "Failed",
		"reason": "submission_orphaned" if orphan else "submission_failed",
	}
	if data:
		failure["pending_vote"] = data
	engine._set_round_values(task.approval_round_id, {
		"round_status": "Stalled", "finalization_status": "Failed",
		"failure_metadata": engine.serialize_manifest(failure),
	})
	close_round_projections(task.approval_round_id)
	engine._notify_stalled_monitors(source, task)


def _repair_queue(task, source, workflow, winner, data):
	round_id = task.approval_round_id
	queue_name = task.submission_queue
	if data and data.get("submission_queue", queue_name) != queue_name:
		engine._mark_conflicted(round_id, _("The source workflow state has changed"))
		return
	queue = _queue_for_round(task, source)
	if queue and queue.status == "Finished":
		# Managed staged votes finish atomically with the source. Older queues
		# may have committed with the round still awaiting reconciliation.
		if not data and queue.job_id and engine._source_at_workflow_state(source, workflow, winner["next_state"]):
			from dinext_common.workflow_approval.email_context import entry_context_for_round
			from dinext_common.workflow_approval.scenarios import service

			entry = entry_context_for_round(round_id, winner)
			engine._finish_round(round_id, winner)
			service.finish_transition(source, task.workflow, task.get("workflow_process"))
			engine.reconcile_source(source, entry_context=entry)
		else:
			engine._mark_conflicted(round_id, _("The source workflow state has changed"))
		return
	if source.get(workflow.workflow_state_field) != task.workflow_state or source.docstatus != 0:
		engine._mark_conflicted(round_id, _("The source workflow state has changed"))
		return
	if queue and queue.status == "Failed":
		_stall_submission(task, source, queue, data)
		return
	staged_at = (data or {}).get("staged_at") or (queue.creation if queue else task.modified)
	if now_datetime() - get_datetime(staged_at) < SUBMISSION_GRACE:
		return
	if queue_name and queued_submission.has_active_job(
		queue_name, source, job_id=queue.job_id if queue else None, named=bool((data or {}).get("named_rq_job")),
	) is not False:
		return
	_stall_submission(task, source, queue, data, orphan=True)


def repair_round(round_id: str) -> None:
	initial_status = frappe.db.get_value("Workflow Task", {"approval_round_id": round_id}, "round_status")
	if initial_status != "Finalizing":
		return
	task, source = _lock_round(round_id)
	if not task or task.round_status != "Finalizing":
		return
	if source is None:
		engine._cancel_round(round_id, _("Source document was deleted during finalization"))
		return
	if not engine._round_matches_source(task, source):
		engine._mark_conflicted(round_id, _("The Workflow process has changed. Refresh the document before acting."))
		return
	data = queued_submission.pending(task)
	winner = data["winner"] if data else _winner(task)
	if not winner:
		engine._mark_conflicted(round_id, _("Finalizing round no longer has a reached transition"))
		return
	workflow = frappe.get_doc("Workflow", task.workflow)
	if task.submission_queue or data:
		_repair_queue(task, source, workflow, winner, data)
	elif source.get(workflow.workflow_state_field) == task.workflow_state:
		engine._finalize_round(source, round_id, winner)
	else:
		engine._mark_conflicted(round_id, _("The source workflow state has changed"))


def retry_round(round_id: str) -> None:
	task, source = _lock_round(round_id)
	if not task:
		raise frappe.DoesNotExistError(_("Approval round does not exist"))
	if task.round_status == "Finalizing" and task.submission_queue:
		return
	if task.finalization_status != "Failed":
		raise engine.WorkflowApprovalConflictError(_("Finalization is not failed"))
	if source is None or not engine._round_matches_source(task, source):
		raise engine.WorkflowApprovalConflictError(_("The Workflow process has changed. Refresh the document before acting."))
	with engine._atomic_workflow_attempt(rollback_on=(Exception,)):
		source.add_comment(
			"Workflow",
			_("Approval finalization retried by {0}").format(
				frappe.bold(frappe.utils.escape_html(frappe.session.user)),
			),
		)
		if data := queued_submission.pending(task):
			queued_submission.retry_pending(task, source, data)
		else:
			engine._set_round_values(round_id, {
				"round_status": "Finalizing", "finalization_status": "Queued",
				"failure_metadata": None, "submission_queue": None,
			})
			repair_round(round_id)


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
			with engine._atomic_workflow_attempt(rollback_on=(Exception,)):
				repair_round(round_id)
		except Exception:
			frappe.log_error(title=f"Workflow approval finalization repair failed: {round_id}")
