"""Stage approval decisions until native submission and successor admission succeed."""
from __future__ import annotations

from copy import deepcopy

import frappe
from frappe import _
from frappe.core.doctype.submission_queue.submission_queue import SubmissionQueue
from frappe.utils import get_datetime

from dinext_common.workflow_approval import engine


def pending(task):
	data = frappe.parse_json(task.failure_metadata or "{}")
	return data.get("pending_vote") if isinstance(data, dict) else None


def stage(task, source, transition, workflow, *, comment, completion_source, request_id, receipt_recorded):
	"""Return a queue acknowledgment only for a winning draft-to-submit vote."""
	if source.docstatus != 0 or not source.meta.queue_in_background:
		return None
	counts = engine._round_vote_counts(task.approval_round_id, engine._parse_manifest(task))
	for row in counts:
		row["votes"] += int(row["transition_uuid"] == transition.transition_uuid)
	reached = [row for row in counts if row["votes"] >= row["threshold"]]
	winner = min(reached, key=lambda row: (int(row["idx"]), row["transition_uuid"]), default=None)
	if not _can_queue(source, workflow, winner):
		return None
	vote = dict(task_name=task.name, transition_uuid=transition.transition_uuid, comment=comment,
		completion_source=completion_source, request_id=request_id, receipt_recorded=receipt_recorded)
	return _stage_votes(task, source, winner, [vote], actor=task.approver)


def _can_queue(source, workflow, winner):
	from frappe.utils.scheduler import is_scheduler_inactive
	if not winner or source.docstatus != 0 or not source.meta.queue_in_background:
		return False
	target = next(row for row in workflow.states if row.state == winner["next_state"])
	return int(target.doc_status or 0) == 1 and not is_scheduler_inactive()


def stage_automatic(source, candidates, winner, *, cycle_guard=None):
	"""Stage all copied decisions before any automatic vote effects are written."""
	if not candidates or source.docstatus != 0 or not source.meta.queue_in_background:
		return None
	task = candidates[0][0]
	workflow = frappe.get_doc("Workflow", task.workflow)
	if not _can_queue(source, workflow, winner):
		return None
	actors = [task.approver for task, transition, reused in candidates
		if transition.transition_uuid == winner["transition_uuid"]]
	actor = actors[-1] if actors else engine._finalization_actor(task.approval_round_id, winner)
	votes = [dict(task_name=task.name, transition_uuid=transition.transition_uuid, comment="",
		completion_source="Automatic Unchanged", request_id=None, receipt_recorded=False,
		reused_from=reused.name) for task, transition, reused in candidates]
	guard = deepcopy(cycle_guard) if cycle_guard else engine.AutomationCycleGuard()
	guard.visit(task.workflow, task.workflow_state, task.entry_fingerprint, task.get("workflow_process") or "")
	return _stage_votes(task, source, winner, votes, actor=actor, automatic=True, cycle_guard=guard)


def _stage_votes(task, source, winner, votes, *, actor, automatic=False, cycle_guard=None):
	data = dict(task_name=task.name, initiator=frappe.session.user, winner=winner,
		votes=votes, automatic=automatic)
	if cycle_guard:
		data["cycle_guard"] = dict(max_transitions=cycle_guard.max_transitions,
			visited=list(cycle_guard.visited), transition_count=cycle_guard.transition_count)
	engine._set_round_values(task.approval_round_id, {
		"round_status": "Finalizing", "finalization_status": "Queued",
		"failure_metadata": engine.serialize_manifest({"pending_vote": data}),
	})
	previous_user = frappe.session.user
	previous_flag = frappe.flags.in_dinext_workflow_finalization
	try:
		frappe.flags.in_dinext_workflow_finalization = True
		frappe.session.user = actor
		engine._ensure_finalization_placeholder(source, task.approval_round_id, winner, actor)
		engine._apply_winning_transition(source, winner["action"])
	finally:
		frappe.session.user = previous_user
		frappe.flags.in_dinext_workflow_finalization = previous_flag
	queue = frappe.db.get_value("Submission Queue", {
		"ref_doctype": source.doctype, "ref_docname": source.name, "status": "Queued"}, "name")
	if not queue:
		raise engine.WorkflowApprovalConflictError(_("Workflow core did not create the expected Submission Queue"))
	engine._set_round_values(task.approval_round_id, {"submission_queue": queue})
	task.reload()
	result = engine._vote_result(task, frappe.get_doc(source.doctype, source.name), transitioned=False)
	return result


def stage_existing_finalization(task, winner, queue, *, initiator, cycle_guard=None):
	"""Correlate a new native queue without changing already accepted votes."""
	data = dict(task_name=task.name, initiator=initiator, winner=winner,
		votes=[], preserve_completed=True)
	if cycle_guard:
		data["cycle_guard"] = dict(max_transitions=cycle_guard.max_transitions,
			visited=list(cycle_guard.visited), transition_count=cycle_guard.transition_count)
	engine._set_round_values(task.approval_round_id, {"submission_queue": queue,
		"failure_metadata": engine.serialize_manifest({"pending_vote": data})})


def complete_source(doc):
	queue = frappe.flags.dinext_pending_submission
	if not queue or (doc.doctype, doc.name) != (queue.ref_doctype, queue.ref_docname):
		return False
	if queue.vote_completed:
		return True
	try:
		task, data = queue.pending_task, queue.pending_data
		workflow = frappe.get_doc("Workflow", task.workflow)
		persisted = frappe.db.get_value(doc.doctype, doc.name, [workflow.workflow_state_field, "docstatus"])
		if persisted != (data["winner"]["next_state"], 1):
			raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
		from dinext_common.workflow_approval.scenarios import service
		service.start_cascade(doc, manual=not (data.get("automatic") or data.get("preserve_completed")))
		service.pin_process(doc, task.get("workflow_process"))
		for vote in data.get("votes", [data]):
			voting_task = frappe.get_doc("Workflow Task", vote["task_name"], for_update=True)
			if voting_task.status != "Working" or voting_task.approval_round_id != task.approval_round_id:
				raise engine.WorkflowApprovalConflictError(_("Workflow Task is no longer active"))
			transition = engine._task_transition(voting_task, vote["transition_uuid"], None)
			engine.complete_task(voting_task, transition, comment=vote["comment"],
				completion_source=vote["completion_source"], content_fingerprint=queue.vote_fingerprint,
				request_id=vote["request_id"], receipt_recorded=vote["receipt_recorded"],
				reused_from=vote.get("reused_from"))
			voting_task.reload()
			engine._dispatch_vote_completed(voting_task, doc, transition)
			if vote.get("reused_from"):
				message = _("{0} automatically reused action {1}").format(
					frappe.bold(frappe.utils.escape_html(voting_task.approver)),
					frappe.bold(frappe.utils.escape_html(_(transition.action))))
			else:
				message = _("{0} voted {1}{2}").format(
					frappe.bold(frappe.utils.escape_html(voting_task.approver)),
					frappe.bold(frappe.utils.escape_html(_(transition.action))),
					f": {frappe.utils.escape_html(vote['comment'])}" if vote["comment"] else "")
			doc.add_comment("Workflow", message)
		from dinext_common.workflow_approval.email_context import entry_context_for_round
		entry = entry_context_for_round(task.approval_round_id, data["winner"])
		engine._finish_round(task.approval_round_id, data["winner"])
		service.finish_transition(doc, task.workflow, task.get("workflow_process"))
		engine._set_round_values(task.approval_round_id, {"failure_metadata": None})
		queue.vote_completed = True
		guard_data = data.get("cycle_guard")
		guard = engine.AutomationCycleGuard(
			max_transitions=guard_data["max_transitions"],
			visited={tuple(state) for state in guard_data["visited"]},
			transition_count=guard_data["transition_count"],
		) if guard_data else None
		engine.reconcile_source(doc, cycle_guard=guard, entry_context=entry)
	except engine.NoEligibleApproversError as error:
		queue.round_error = error.details
		raise
	return True


class DinextSubmissionQueue(SubmissionQueue):
	def background_submission(self, to_be_queued_doc, action_for_queuing):
		if frappe.db.get_value("Submission Queue", self.name, "status") != "Queued":
			return
		names = frappe.get_all("Workflow Task", filters={"submission_queue": self.name,
			}, pluck="name")
		task = None
		for name in names:
			candidate = frappe.get_doc("Workflow Task", name)
			data = pending(candidate)
			if data and data.get("task_name") == candidate.name:
				task = candidate
				break
		if not task:
			return super().background_submission(to_be_queued_doc, action_for_queuing)
		# Native update_job_id commits; acquire all attempt locks after that boundary.
		return self._run_pending(task, to_be_queued_doc, action_for_queuing)

	def update_job_id(self, job_id):
		super().update_job_id(job_id)
		if not getattr(self, "pending_task", None):
			return
		engine._lock_domain_dependencies(self.ref_doctype, self.ref_docname)
		source = frappe.get_doc(self.ref_doctype, self.ref_docname, for_update=True)
		task = frappe.get_doc("Workflow Task", self.pending_task.name, for_update=True)
		if task.submission_queue != self.name or task.round_status != "Finalizing" or not pending(task):
			raise engine.WorkflowApprovalConflictError(_("Workflow Task is no longer active"))
		if get_datetime(task.source_created_at) != get_datetime(source.creation):
			raise engine.WorkflowApprovalConflictError(_("The Workflow Task belongs to another document instance"))
		from dinext_common.workflow_approval.scenarios import service
		if service.is_ready():
			context = service.get_context(source)
			if context["process_id"] != task.get("workflow_process") or context["workflow"] != task.workflow:
				raise engine.WorkflowApprovalConflictError(_("The Workflow process has changed. Refresh the document before acting."))
		workflow = frappe.get_doc("Workflow", task.workflow)
		if source.docstatus != 0 or source.get(workflow.workflow_state_field) != task.workflow_state:
			raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
		self.pending_task = task
		self.pending_data = pending(task)
		self.vote_fingerprint = engine.get_content_fingerprint(source, frappe.get_doc("Workflow", task.workflow))

	def _run_pending(self, task, doc, action):
		self.pending_task, self.pending_data = task, pending(task)
		self.round_error, self.vote_completed = None, False
		previous_cascade = deepcopy(getattr(frappe.local, "workflow_scenario_cascade", None))
		previous = frappe.flags.dinext_pending_submission
		previous_flag = frappe.flags.in_dinext_workflow_finalization
		frappe.flags.dinext_pending_submission = self
		frappe.flags.in_dinext_workflow_finalization = True
		try:
			from dinext_common.workflow_approval.scenarios.compat import authorized_finalization
			with authorized_finalization(doc):
				return super().background_submission(doc, action)
		except Exception:
			# Native worker setup (including update_job_id) precedes its try/rollback.
			traceback = frappe.get_traceback()
			frappe.db.rollback()
			queue = frappe.get_doc("Submission Queue", self.name, for_update=True)
			if queue.status == "Queued":
				frappe.db.set_value("Submission Queue", self.name, {
					"status": "Failed", "exception": traceback, "ended_at": frappe.utils.now()}, update_modified=False)
				self.notify("Failed", action)
		finally:
			frappe.local.workflow_scenario_cascade = previous_cascade
			frappe.flags.dinext_pending_submission = previous
			frappe.flags.in_dinext_workflow_finalization = previous_flag

	def notify(self, submission_status, action):
		if submission_status == "Finished" and getattr(self, "pending_task", None):
			return
		if submission_status != "Failed" or not getattr(self, "round_error", None):
			return super().notify(submission_status, action)
		engine._lock_domain_dependencies(self.ref_doctype, self.ref_docname)
		source = frappe.get_doc(self.ref_doctype, self.ref_docname, for_update=True)
		task = frappe.get_doc("Workflow Task", self.pending_task.name, for_update=True)
		if task.submission_queue != self.name or task.round_status != "Finalizing" or not pending(task):
			return
		if get_datetime(task.source_created_at) != get_datetime(source.creation):
			return
		from dinext_common.workflow_approval.scenarios import service
		if service.is_ready():
			context = service.get_context(source)
			if context["process_id"] != task.get("workflow_process") or context["workflow"] != task.workflow:
				return
		data = self.pending_data
		engine._set_round_values(task.approval_round_id, {
			"round_status": "Stalled" if data.get("preserve_completed") else "Open",
			"finalization_status": "Failed" if data.get("preserve_completed") else None,
			"submission_queue": None,
			"failure_metadata": engine.serialize_manifest({"reason": "no_eligible_approvers",
				"workflow_error": self.round_error, "initiator": data["initiator"],
				"submission_queue": self.name, "task_name": task.name}),
		})
		frappe.db.delete("Workflow Action", {"custom_approval_round_id": task.approval_round_id,
			"custom_workflow_task": ("is", "not set")})
		if data.get("preserve_completed"):
			from dinext_common.workflow_approval.projections import close_round_projections
			close_round_projections(task.approval_round_id)
		if data.get("automatic"):
			from dinext_common.workflow_approval.projections import create_round_projections
			create_round_projections(source, [frappe.get_doc("Workflow Task", name)
				for name in engine._round_task_names(task.approval_round_id)
				if frappe.db.get_value("Workflow Task", name, "status") == "Working"])
		message = frappe.utils.escape_html(engine.round_error_message(self.round_error))
		frappe.publish_realtime("msgprint", {"message": message, "alert": True, "indicator": "red"},
			user=data["initiator"], after_commit=True)
		frappe.get_doc({"doctype": "Notification Log", "type": "Alert", "for_user": data["initiator"],
			"subject": message, "document_type": source.doctype, "document_name": source.name,
		}).insert(ignore_permissions=True)
