"""Stage approval decisions until native submission and successor admission succeed."""
from __future__ import annotations

from copy import deepcopy

import frappe
from frappe import _
from frappe.core.doctype.submission_queue.submission_queue import SubmissionQueue
from frappe.utils import get_datetime, now_datetime

from dinext_common.workflow_approval import engine


def pending(task):
	data = frappe.parse_json(task.failure_metadata or "{}")
	return data.get("pending_vote") if isinstance(data, dict) else None


def queue_job_id(queue_name):
	return f"workflow-submission:{queue_name}"


def _matches_job(job, queue_name, source):
	from rq.job import JobStatus

	payload = job.kwargs
	args = payload.get("kwargs") or {}
	doc = args.get("to_be_queued_doc")
	return (
		payload.get("site") == frappe.local.site
		and payload.get("method") == "frappe.model.document.execute_action"
		and args.get("__doctype") == "Submission Queue"
		and args.get("__name") == queue_name
		and args.get("__action") == "background_submission"
		and args.get("action_for_queuing") == "Submit"
		and doc
		and (doc.doctype, doc.name) == (source.doctype, source.name)
		and doc.creation and get_datetime(doc.creation) == get_datetime(source.creation)
		and job.get_status() in (JobStatus.QUEUED, JobStatus.STARTED, JobStatus.DEFERRED, JobStatus.SCHEDULED)
	)


def has_active_job(queue_name, source, *, job_id=None, named=False):
	"""Inspect this site's native queue job. An unavailable Redis cannot prove loss."""
	from frappe.utils.background_jobs import create_job_id, get_queue
	from redis.exceptions import RedisError
	from rq.exceptions import DeserializationError, NoSuchJobError

	try:
		queue = get_queue("default")
		expected_id = create_job_id(queue_job_id(queue_name))
		for candidate in dict.fromkeys(filter(None, (job_id, expected_id))):
			try:
				job = queue.job_class.fetch(candidate, connection=queue.connection, serializer=queue.serializer)
			except NoSuchJobError:
				continue
			if job.origin == queue.name and _matches_job(job, queue_name, source):
				return True
		if named:
			return False

		# Older native jobs were assigned random IDs. Read queue indexes together
		# because a worker can move a job from waiting to started during repair.
		with queue.connection.pipeline() as indexes:
			indexes.lrange(queue.key, 0, -1)
			indexes.lrange(queue.intermediate_queue_key, 0, -1)
			indexes.zrange(queue.started_job_registry.key, 0, -1)
			indexes.zrange(queue.scheduled_job_registry.key, 0, -1)
			indexes.zrange(queue.deferred_job_registry.key, 0, -1)
			job_ids = {value.decode() for rows in indexes.execute() for value in rows}
		jobs = queue.job_class.fetch_many(job_ids, connection=queue.connection, serializer=queue.serializer)
		return any(job and job.origin == queue.name and _matches_job(job, queue_name, source) for job in jobs)
	except (RedisError, DeserializationError):
		return None


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
	return _stage_votes(task, source, workflow, winner, [vote], actor=task.approver)


def _can_queue(source, workflow, winner):
	from frappe.utils.scheduler import is_scheduler_inactive

	return bool(
		winner and source.docstatus == 0 and source.meta.queue_in_background
		and engine._state_docstatus(workflow, winner["next_state"]) == 1
		and not is_scheduler_inactive()
	)


def stage_automatic(source, candidates, winner, *, cycle_guard=None):
	"""Stage all copied decisions before any automatic vote effects are written."""
	if not candidates or source.docstatus != 0 or not source.meta.queue_in_background:
		return None
	task = candidates[0][0]
	workflow = frappe.get_doc("Workflow", task.workflow)
	if not _can_queue(source, workflow, winner):
		return None
	actors = [
		task.approver for task, transition, _ in candidates
		if transition.transition_uuid == winner["transition_uuid"]
	]
	actor = actors[-1] if actors else engine._finalization_actor(task.approval_round_id, winner)
	votes = [dict(task_name=task.name, transition_uuid=transition.transition_uuid, comment="",
		completion_source="Automatic Unchanged", request_id=None, receipt_recorded=False,
		reused_from=reused.name) for task, transition, reused in candidates]
	guard = deepcopy(cycle_guard) if cycle_guard else engine.AutomationCycleGuard()
	guard.visit(task.workflow, task.workflow_state, task.entry_fingerprint, task.get("workflow_process") or "")
	return _stage_votes(task, source, workflow, winner, votes, actor=actor, automatic=True, cycle_guard=guard)


def _save_pending(task, queue, data):
	data = {**data, "submission_queue": queue, "staged_at": str(now_datetime()), "named_rq_job": True}
	engine._set_round_values(task.approval_round_id, {
		"round_status": "Finalizing", "finalization_status": "Queued", "submission_queue": queue,
		"failure_metadata": engine.serialize_manifest({"pending_vote": data}),
	})


def _pending_data(task, winner, votes, *, actor, initiator, cycle_guard, **flags):
	data = dict(task_name=task.name, initiator=initiator, actor=actor, winner=winner, votes=votes, **flags)
	if cycle_guard:
		data["cycle_guard"] = dict(max_transitions=cycle_guard.max_transitions,
			visited=list(cycle_guard.visited), transition_count=cycle_guard.transition_count)
	return data


def _stage_votes(task, source, workflow, winner, votes, *, actor, automatic=False, cycle_guard=None):
	data = _pending_data(
		task, winner, votes, actor=actor, initiator=frappe.session.user,
		cycle_guard=cycle_guard, automatic=automatic,
	)
	with engine._atomic_workflow_attempt(rollback_on=(Exception,)):
		_enqueue_pending(task, source, workflow, data)
	task.reload()
	return engine._vote_result(task, frappe.get_doc(source.doctype, source.name), transitioned=False)


def _enqueue_pending(task, source, workflow, data):
	winner = data["winner"]
	actor = data["actor"]
	previous_user = frappe.session.user
	previous_flag = frappe.flags.in_dinext_workflow_finalization
	try:
		frappe.flags.in_dinext_workflow_finalization = True
		frappe.session.user = actor
		engine._ensure_finalization_placeholder(source, task.approval_round_id, winner, actor)
		result, queue = engine._apply_winning_transition(source, workflow, winner)
	finally:
		frappe.session.user = previous_user
		frappe.flags.in_dinext_workflow_finalization = previous_flag
	if result is not None or not queue:
		raise engine.WorkflowApprovalConflictError(_("Workflow core did not create the expected Submission Queue"))
	_save_pending(task, queue, data)


def stage_existing_finalization(task, winner, queue, *, initiator, actor, cycle_guard=None):
	"""Correlate a new native queue without changing already accepted votes."""
	data = _pending_data(
		task, winner, [], actor=actor, initiator=initiator,
		cycle_guard=cycle_guard, preserve_completed=True,
	)
	_save_pending(task, queue, data)


def retry_pending(task, source, data):
	workflow = frappe.get_doc("Workflow", task.workflow)
	if not _can_queue(source, workflow, data["winner"]) or (
		source.get(workflow.workflow_state_field) != task.workflow_state
	):
		raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
	if not data.get("actor"):
		# Existing persisted attempts predate the explicit actor. Their native
		# queue owner or the decisive approver identifies that same actor.
		actor = frappe.db.get_value("Submission Queue", task.submission_queue, "owner") if task.submission_queue else None
		if not actor:
			winning_uuid = data["winner"]["transition_uuid"]
			winning_vote = next((vote for vote in reversed(data.get("votes", [data]))
				if vote["transition_uuid"] == winning_uuid), None)
			actor = (
				frappe.db.get_value("Workflow Task", winning_vote["task_name"], "approver")
				if winning_vote else engine._finalization_actor(task.approval_round_id, data["winner"])
			)
		data = {**data, "actor": actor}
	_enqueue_pending(task, source, workflow, data)


def complete_source(doc):
	queue = frappe.flags.dinext_pending_submission
	if not queue or not engine._round_matches_source(queue.pending_task, doc):
		return False
	if queue.vote_completed:
		return True
	try:
		task, data = queue.pending_task, queue.pending_data
		workflow = frappe.get_doc("Workflow", task.workflow)
		persisted = frappe.get_doc(doc.doctype, doc.name)
		if not engine._round_matches_source(task, persisted) or not engine._source_at_workflow_state(
			persisted, workflow, data["winner"]["next_state"],
		) or persisted.docstatus != 1:
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


class _SubmissionNoLongerPending(Exception):
	pass


class DinextSubmissionQueue(SubmissionQueue):
	def after_insert(self):
		from dinext_common.workflow_approval.scenarios.compat import transition_execution

		execution = transition_execution(self.queued_doc)
		if not execution:
			return super().after_insert()
		self.queue_action(
			"background_submission", to_be_queued_doc=self.queued_doc,
			action_for_queuing=self.action_for_queuing, timeout=600,
			enqueue_after_commit=True, job_id=queue_job_id(self.name),
		)
		execution.submission_queue = self.name

	def unlock(self):
		# A delayed worker for a definitively failed queue may arrive after retry.
		if self.status == "Queued":
			return super().unlock()

	def background_submission(self, to_be_queued_doc, action_for_queuing):
		if frappe.db.get_value("Submission Queue", self.name, "status") != "Queued":
			return
		names = frappe.get_all("Workflow Task", filters={"submission_queue": self.name}, pluck="name")
		for name in names:
			task = frappe.get_doc("Workflow Task", name)
			data = pending(task)
			if data and data.get("task_name") == task.name:
				return self._run_pending(task, to_be_queued_doc, action_for_queuing)
		from frappe.utils.background_jobs import create_job_id
		from rq import get_current_job

		job = get_current_job()
		if job and job.id == create_job_id(queue_job_id(self.name)):
			return
		if frappe.db.get_value("Submission Queue", self.name, "status", for_update=True) == "Queued":
			return super().background_submission(to_be_queued_doc, action_for_queuing)

	def _lock_attempt(self):
		engine._lock_domain_dependencies(self.ref_doctype, self.ref_docname)
		source = frappe.get_doc(self.ref_doctype, self.ref_docname, for_update=True)
		task = frappe.get_doc("Workflow Task", self.pending_task.name, for_update=True)
		queue = frappe.db.get_value(
			"Submission Queue", self.name, ["status", "job_id", "ref_doctype", "ref_docname"],
			as_dict=True, for_update=True,
		)
		data = pending(task)
		if (
			not queue or queue.status != "Queued" or task.submission_queue != self.name
			or task.round_status != "Finalizing" or not data
			or data.get("submission_queue", self.name) != self.name
		):
			raise _SubmissionNoLongerPending
		if (queue.ref_doctype, queue.ref_docname) != (source.doctype, source.name) or not engine._round_matches_source(task, source):
			raise engine.WorkflowApprovalConflictError(_("The Workflow Task belongs to another document instance"))
		return source, task, data, queue

	def update_job_id(self, job_id):
		if not getattr(self, "pending_task", None):
			return super().update_job_id(job_id)
		# Keep native job-ID persistence. Recheck ownership and state after its commit.
		self._lock_attempt()
		super().update_job_id(job_id)
		source, task, data, queue = self._lock_attempt()
		if queue.job_id != job_id:
			raise _SubmissionNoLongerPending
		from frappe.model.workflow import get_transitions, has_approval_access

		workflow = frappe.get_doc("Workflow", task.workflow)
		winner = data["winner"]
		doc = self.submission_document
		if (
			self.submission_action != "Submit" or not engine._round_matches_source(task, doc)
			or source.get(workflow.workflow_state_field) != task.workflow_state or source.docstatus != 0
			or doc.get(workflow.workflow_state_field) != winner["next_state"]
			or engine._state_docstatus(workflow, winner["next_state"]) != 1
		):
			raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
		frappe.has_permission(source.doctype, doc=source.name, throw=True)
		choices = get_transitions(source, workflow)
		if not choices or not has_approval_access(frappe.session.user, source, choices[0]):
			raise engine.WorkflowApprovalConflictError(_("Workflow core validation rejected the winning transition"))
		self.pending_task, self.pending_data = task, data
		self.vote_fingerprint = engine.get_content_fingerprint(source, workflow)

	def _run_pending(self, task, doc, action):
		self.pending_task, self.pending_data = task, pending(task)
		self.submission_document, self.submission_action = doc, action
		self.round_error, self.vote_completed = None, False
		previous_cascade = deepcopy(getattr(frappe.local, "workflow_scenario_cascade", None))
		previous_user = frappe.session.user
		previous = frappe.flags.dinext_pending_submission
		previous_flag = frappe.flags.in_dinext_workflow_finalization
		frappe.flags.dinext_pending_submission = self
		frappe.flags.in_dinext_workflow_finalization = True
		frappe.session.user = self.pending_data.get("actor") or self.owner
		try:
			from frappe.core.doctype.submission_queue.submission_queue import get_current_job
			from frappe.monitor import add_data_to_monitor
			from frappe.utils import now, time_diff_in_seconds

			from dinext_common.workflow_approval.scenarios.compat import (
				authorized_finalization,
				exact_transition,
			)

			with exact_transition(doc, task.workflow, self.pending_data["winner"]), authorized_finalization(doc):
				self.update_job_id(get_current_job().id)
				# Native submit runs normal controllers and events. Retain the
				# source locks when rolling back a failed save for its diagnostics.
				with engine._atomic_workflow_attempt(rollback_on=(Exception,)):
					doc.submit()
					if not self.vote_completed:
						raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
					add_data_to_monitor(
						doctype=doc.doctype, docname=doc.name, action="submit",
						execution_time=time_diff_in_seconds(now(), self.created_at),
						enqueued_by=self.enqueued_by,
					)
					frappe.db.set_value("Submission Queue", self.name, {
						"status": "Finished", "ended_at": now_datetime(),
					}, update_modified=False)
		except _SubmissionNoLongerPending:
			return
		except (frappe.db.InternalError, frappe.QueryDeadlockError, frappe.QueryTimeoutError):
			raise
		except Exception:
			if frappe.db.get_value("Submission Queue", self.name, "status", for_update=True) == "Queued":
				frappe.db.set_value("Submission Queue", self.name, {
					"status": "Failed", "exception": frappe.get_traceback(), "ended_at": now_datetime(),
				}, update_modified=False)
				self.notify("Failed", action)
		finally:
			frappe.local.workflow_scenario_cascade = previous_cascade
			frappe.session.user = previous_user
			frappe.flags.dinext_pending_submission = previous
			frappe.flags.in_dinext_workflow_finalization = previous_flag

	def notify(self, submission_status, action):
		if submission_status == "Finished" and getattr(self, "pending_task", None):
			if not self.vote_completed:
				raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
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
		else:
			from dinext_common.workflow_approval.projections import repair_round_projections

			repair_round_projections(source, task.approval_round_id)
		message = frappe.utils.escape_html(engine.round_error_message(self.round_error))
		frappe.publish_realtime("msgprint", {"message": message, "alert": True, "indicator": "red"},
			user=data["initiator"], after_commit=True)
		frappe.get_doc({"doctype": "Notification Log", "type": "Alert", "for_user": data["initiator"],
			"subject": message, "document_type": source.doctype, "document_name": source.name,
		}).insert(ignore_permissions=True)
