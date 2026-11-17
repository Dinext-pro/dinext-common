"""Exercise admission through the native Submission Queue worker transaction."""
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.tests import test_workflow_approval_integration as fixtures


class TestWorkflowQueuedRoundFailure(FrappeTestCase):
	workflow_name = "_Test Queued Admission Workflow"
	action_name = "_Test Approve"
	reopen_action_name = "_Test Reopen"
	user = "parallel-approver@example.com"
	empty_role = "_Test Empty Queued Approval"

	def setUp(self):
		super().setUp()
		self.fixture = fixtures.TestWorkflowApprovalIntegration("runTest")
		self.fixture.workflow_name = self.workflow_name
		self.fixture.setUp()
		self.fixture._ensure_master("Role", self.empty_role, {"role_name": self.empty_role})
		frappe.db.set_value("Custom DocPerm", {"parent": "Issue", "role": "System Manager", "permlevel": 0}, "submit", 1)
		frappe.clear_cache(doctype="Issue")

	def tearDown(self):
		self.fixture.tearDown()
		super().tearDown()

	def test_repair_waits_for_the_exact_rq_job_and_retries_the_saved_vote(self):
		from frappe.utils import add_to_date, now_datetime
		from frappe.utils.background_jobs import enqueue
		from redis.exceptions import ConnectionError

		from dinext_common.workflow_approval import api, engine, finalization, request_receipts
		from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].condition = f"frappe.session.user == {self.user!r}"
		workflow.append("transitions", {
			"state": "Open", "action": self.action_name, "next_state": "Open",
			"allowed": "System Manager", "allow_self_approval": 1,
			"custom_transition_uuid": "_test-same-action",
		})
		workflow.save(ignore_permissions=True)
		frappe.db.set_value("Workflow Document State", workflow.states[1].name, "doc_status", "1")
		meta = frappe.get_meta("Issue")
		with (
			patch.object(meta, "is_submittable", 1), patch.object(meta, "queue_in_background", 1),
			patch("frappe.utils.scheduler.is_scheduler_inactive", return_value=False),
			patch.object(DinextSubmissionQueue, "queue_action"), patch.object(frappe.db, "commit"),
		):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Orphaned queued approval", "status": "Open"}).insert()
			task = frappe.get_doc("Workflow Task", {
				"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user,
			})
			request_id = frappe.generate_hash(length=32)
			receipt_key = request_receipts.request_key("Vote", request_id)
			result = engine.cast_vote(task.name, transition_uuid="_test-transition", comment="Saved decision", request_id=request_id)
			queue_name = result["pending_submission"]
			self.assertEqual(api.get_vote_status(task.name)["pending_submission"], queue_name)
			receipt = request_receipts.get(receipt_key)
			round_id = task.approval_round_id

			finalization.repair_round(round_id)
			self.assertEqual(task.reload().round_status, "Finalizing")

			failure = frappe.parse_json(task.failure_metadata)
			failure["pending_vote"].pop("named_rq_job", None)
			engine._set_round_values(round_id, {"failure_metadata": engine.serialize_manifest(failure)})
			# Older native jobs used a random ID until the job actually began.
			job = enqueue(
				"frappe.model.document.execute_action",
				__doctype="Submission Queue", __name=queue_name, __action="background_submission",
				to_be_queued_doc=doc, action_for_queuing="Submit",
			)
			self.addCleanup(job.delete)
			later = add_to_date(now_datetime(), minutes=3)
			with patch.object(finalization, "now_datetime", return_value=later):
				finalization.repair_round(round_id)
				self.assertEqual(task.reload().round_status, "Finalizing")
				self.assertFalse(frappe.db.get_value("Submission Queue", queue_name, "job_id"))
				job.delete()

				with patch("frappe.utils.background_jobs.get_redis_conn", side_effect=ConnectionError):
					finalization.repair_round(round_id)
				self.assertEqual(task.reload().round_status, "Finalizing")

				other_job = enqueue(
					"frappe.model.document.execute_action",
					__doctype="Submission Queue", __name=f"{queue_name}-other", __action="background_submission",
					to_be_queued_doc=doc, action_for_queuing="Submit",
				)
				self.addCleanup(other_job.delete)
				finalization.repair_round(round_id)
				finalization.repair_round(round_id)
			self.assertEqual((task.reload().round_status, task.finalization_status), ("Stalled", "Failed"))
			self.assertEqual(frappe.db.get_value("Submission Queue", queue_name, "status"), "Failed")
			self.assertEqual(request_receipts.get(receipt_key), receipt)

			api.retry_finalization(round_id)
			self.assertEqual(task.reload().round_status, "Finalizing")
			self.assertNotEqual(task.submission_queue, queue_name)
			retried_queue = task.submission_queue
			api.retry_finalization(round_id)
			self.assertEqual(task.reload().submission_queue, retried_queue)
			self.assertEqual(frappe.db.count("Submission Queue", {"ref_doctype": "Issue", "ref_docname": doc.name}), 2)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Open", 0))
			queue = frappe.get_doc("Submission Queue", retried_queue)
			queued_doc = frappe.get_doc("Issue", doc.name)
			queued_doc.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			with patch("frappe.core.doctype.submission_queue.submission_queue.get_current_job", return_value=SimpleNamespace(id="test-recovered-queue")):
				queue.background_submission(queued_doc, "Submit")
				queue.background_submission(queued_doc, "Submit")
			frappe.set_user("Administrator")
			self.assertEqual(queue.reload().status, "Finished", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Closed", 1))
			self.assertEqual((task.reload().status, task.vote_comment, task.correlation_id), ("Completed", "Saved decision", request_id))
			self.assertEqual(request_receipts.get(receipt_key), receipt)
			current = api.get_vote_status(task.name)
			self.assertNotIn("pending_submission", current)
			self.assertEqual(current["workflow_state"], "Closed")
			self.assertEqual(
				engine.cast_vote(task.name, transition_uuid="_test-transition", comment="Saved decision", request_id=request_id),
				result,
			)

	def test_staged_worker_rejects_live_semantic_drift(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		frappe.db.set_value("Workflow Document State", workflow.states[1].name, "doc_status", "1")
		meta = frappe.get_meta("Issue")
		with (
			patch.object(meta, "is_submittable", 1), patch.object(meta, "queue_in_background", 1),
			patch("frappe.utils.scheduler.is_scheduler_inactive", return_value=False),
			patch.object(DinextSubmissionQueue, "queue_action"), patch.object(frappe.db, "commit"),
			patch("frappe.core.doctype.submission_queue.submission_queue.get_current_job", return_value=SimpleNamespace(id="test-drifted-queue")),
		):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Staged semantic drift", "status": "Open"}).insert()
			task = frappe.get_doc("Workflow Task", {
				"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user,
			})
			queued = engine.cast_vote(task.name, transition_uuid="_test-transition")
			queue = frappe.get_doc("Submission Queue", queued["pending_submission"])
			# The actor still passes the live condition, but this is a different snapshot.
			frappe.db.set_value("Workflow Transition", workflow.transitions[0].name, "condition", "True")
			submitted = frappe.get_doc("Issue", doc.name)
			submitted.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			queue.background_submission(submitted, "Submit")
			frappe.set_user("Administrator")

			self.assertEqual(queue.reload().status, "Failed", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Open", 0))
			self.assertEqual(task.reload().status, "Working")

	def test_staged_worker_needs_the_winning_role_even_with_source_read_access(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		frappe.db.set_value("Workflow Document State", workflow.states[1].name, "doc_status", "1")
		meta = frappe.get_meta("Issue")
		with (
			patch.object(meta, "is_submittable", 1), patch.object(meta, "queue_in_background", 1),
			patch("frappe.utils.scheduler.is_scheduler_inactive", return_value=False),
			patch.object(DinextSubmissionQueue, "queue_action"), patch.object(frappe.db, "commit"),
			patch("frappe.core.doctype.submission_queue.submission_queue.get_current_job", return_value=SimpleNamespace(id="test-revoked-role")),
		):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Staged role revoked", "status": "Open"}).insert()
			frappe.share.add("Issue", doc.name, self.user, read=1)
			task = frappe.get_doc("Workflow Task", {
				"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user,
			})
			result = engine.cast_vote(task.name, transition_uuid="_test-transition")
			queue = frappe.get_doc("Submission Queue", result["pending_submission"])
			frappe.db.delete("Has Role", {"parenttype": "User", "parent": self.user, "role": "System Manager"})
			frappe.clear_cache(user=self.user)
			self.assertTrue(frappe.has_permission(doc.doctype, doc=doc.name, user=self.user))
			self.assertNotIn("System Manager", frappe.get_roles(self.user))
			submitted = frappe.get_doc(doc.doctype, doc.name)
			submitted.status = "Closed"
			queue.background_submission(submitted, "Submit")

			self.assertEqual(queue.reload().status, "Failed", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Open", 0))
			self.assertEqual(task.reload().status, "Working")

	def test_worker_restores_source_and_vote_if_queue_completion_cannot_be_saved(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		frappe.db.set_value("Workflow Document State", workflow.states[1].name, "doc_status", "1")
		meta = frappe.get_meta("Issue")
		with (
			patch.object(meta, "is_submittable", 1), patch.object(meta, "queue_in_background", 1),
			patch("frappe.utils.scheduler.is_scheduler_inactive", return_value=False),
			patch.object(DinextSubmissionQueue, "queue_action"), patch.object(frappe.db, "commit"),
			patch("frappe.core.doctype.submission_queue.submission_queue.get_current_job", return_value=SimpleNamespace(id="test-completion-write")),
		):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Queued completion write failure", "status": "Open"}).insert()
			task = frappe.get_doc("Workflow Task", {
				"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user,
			})
			result = engine.cast_vote(task.name, transition_uuid="_test-transition")
			queue = frappe.get_doc("Submission Queue", result["pending_submission"])
			submitted = frappe.get_doc(doc.doctype, doc.name)
			submitted.status = "Closed"
			set_value = frappe.db.set_value

			def fail_completion(doctype, name, fields, *args, **kwargs):
				if doctype == "Submission Queue" and name == queue.name and fields.get("status") == "Finished":
					raise RuntimeError("Could not write test queue completion")
				return set_value(doctype, name, fields, *args, **kwargs)

			with patch.object(frappe.db, "set_value", side_effect=fail_completion):
				queue.background_submission(submitted, "Submit")

			self.assertEqual(queue.reload().status, "Failed", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Open", 0))
			self.assertEqual((task.reload().status, task.round_status), ("Working", "Finalizing"))

	def test_native_worker_rolls_back_deciding_vote_and_allows_retry(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue
		second = "queued-deciding-approver@example.com"
		if not frappe.db.exists("User", second):
			frappe.get_doc({"doctype": "User", "email": second, "first_name": "Queue Approver",
				"send_welcome_email": 0, "roles": [{"role": "System Manager"}]}).insert(ignore_permissions=True)
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].custom_parallel_approval_policy = "All"
		workflow.transitions[0].condition = f"frappe.session.user in {[second, self.user]!r}"
		workflow.transitions[1].allowed = self.empty_role
		workflow.save(ignore_permissions=True)
		# Issue provides a small real source fixture. The test grants it submission
		# metadata without changing any production DocType or its controller.
		frappe.db.set_value("Workflow Document State", workflow.states[1].name, "doc_status", "1")
		frappe.clear_cache(doctype="Workflow")
		meta = frappe.get_meta("Issue")
		with patch.object(meta, "is_submittable", 1), patch.object(meta, "queue_in_background", 1), \
			patch("frappe.utils.scheduler.is_scheduler_inactive", return_value=False), \
			patch.object(DinextSubmissionQueue, "queue_action"), \
			patch.object(frappe.db, "commit"), \
			patch("frappe.core.doctype.submission_queue.submission_queue.get_current_job", return_value=SimpleNamespace(id="test-native-admission")):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Native queued admission", "status": "Open"}).insert(ignore_permissions=True)
			scope = {"reference_doctype": "Issue", "reference_name": doc.name}
			tasks = {r.approver: r.name for r in frappe.get_all("Workflow Task", filters=scope, fields=["approver", "name"])}
			engine.cast_vote(tasks[self.user], action=self.action_name)
			first = frappe.get_doc("Workflow Task", tasks[self.user]).completed_at
			result = engine.cast_vote(tasks[second], action=self.action_name, comment="Decision")
			self.assertEqual(result["status"], "Working")
			self.assertFalse(result["transitioned"])
			queue = frappe.get_doc("Submission Queue", result["pending_submission"])
			self.assertIsInstance(queue, DinextSubmissionQueue)
			comments = frappe.db.count("Comment", scope)
			queued_doc = frappe.get_doc("Issue", doc.name)
			queued_doc.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			queue.background_submission(queued_doc, "Submit")
			frappe.set_user("Administrator")
			self.assertEqual(queue.reload().status, "Failed", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Open", 0))
			task = frappe.get_doc("Workflow Task", tasks[second])
			self.assertEqual((task.status, task.round_status), ("Working", "Open"), queue.exception)
			details = frappe.parse_json(task.failure_metadata)
			self.assertEqual(details["reason"], "no_eligible_approvers")
			self.assertEqual(details["workflow_error"]["state"], "Closed")
			from dinext_common.workflow_approval.api import get_form_approval_banner
			self.assertEqual(get_form_approval_banner("Issue", doc.name)["workflow_errors"], [details["workflow_error"]])
			self.assertTrue(frappe.db.exists("Notification Log", {"document_type": "Issue", "document_name": doc.name, "for_user": "Administrator"}))
			self.assertEqual(frappe.db.count("Comment", scope), comments)
			self.assertEqual(frappe.db.get_value("Workflow Task", tasks[self.user], "completed_at"), first)
			self.assertTrue(frappe.db.exists("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"}))
			frappe.db.set_value("Workflow Transition", workflow.transitions[1].name, "allowed", "System Manager")
			frappe.clear_cache(doctype="Workflow")
			frappe.get_meta("Issue").is_submittable = 1
			frappe.get_meta("Issue").queue_in_background = 1
			result = engine.cast_vote(task.name, action=self.action_name, comment="Decision")
			queue = frappe.get_doc("Submission Queue", result["pending_submission"])
			queued_doc = frappe.get_doc("Issue", doc.name)
			queued_doc.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			queue.background_submission(queued_doc, "Submit")
			frappe.set_user("Administrator")
			self.assertEqual(queue.reload().status, "Finished", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Closed", 1))
			self.assertEqual(frappe.get_doc("Workflow Task", task.name).status, "Completed")
			self.assertTrue(frappe.db.exists("Workflow Task", {**scope, "workflow_state": "Closed", "status": "Working"}))

			comments_after = frappe.db.count("Comment", scope)
			queue.background_submission(queued_doc, "Submit")
			self.assertEqual(frappe.db.count("Comment", scope), comments_after)
			self.assertFalse(frappe.get_doc("Workflow Task", task.name).failure_metadata)
			self.assertNotIn("workflow_errors", get_form_approval_banner("Issue", doc.name))

	def test_native_worker_rolls_back_automatic_vote_bundle(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue
		second = "queued-auto-approver@example.com"
		if not frappe.db.exists("User", second):
			frappe.get_doc({"doctype": "User", "email": second, "first_name": "Automatic Queue Approver",
				"send_welcome_email": 0, "roles": [{"role": "System Manager"}]}).insert(ignore_permissions=True)
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].custom_parallel_approval_policy = "All"
		workflow.transitions[0].condition = f"frappe.session.user in {[second, self.user]!r}"
		workflow.transitions[1].allowed = self.empty_role
		workflow.save(ignore_permissions=True)
		frappe.db.set_value("Workflow Document State", workflow.states[1].name, "doc_status", "1")
		frappe.clear_cache(doctype="Workflow")
		meta = frappe.get_meta("Issue")
		with patch.object(meta, "is_submittable", 1), patch.object(meta, "queue_in_background", 1), \
			patch("frappe.utils.scheduler.is_scheduler_inactive", return_value=False), \
			patch.object(DinextSubmissionQueue, "queue_action"), patch.object(frappe.db, "commit"), \
			patch("frappe.core.doctype.submission_queue.submission_queue.get_current_job", return_value=SimpleNamespace(id="test-native-auto-admission")):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Automatic queued admission", "status": "Open"}).insert(ignore_permissions=True)
			scope = {"reference_doctype": "Issue", "reference_name": doc.name}
			history = [frappe.get_doc("Workflow Task", name) for name in frappe.get_all("Workflow Task", filters=scope, pluck="name")]
			fingerprint = engine.get_content_fingerprint(doc.reload(), workflow)
			# Seed two historical human decisions for this same source instance,
			# representing a prior round before the unchanged source reentered Open.
			for task in history:
				engine.complete_task(task, task.available_workflow_transitions[0], comment="Prior decision",
					completion_source="Manual", content_fingerprint=fingerprint)
			engine._finish_round(history[0].approval_round_id, {"next_state": "Closed"})
			prior = {task.name: frappe.get_doc("Workflow Task", task.name).as_dict() for task in history}
			comments = frappe.db.count("Comment", scope)
			names = engine.reconcile_source(doc)
			self.assertEqual(len(names), 2)
			tasks = [frappe.get_doc("Workflow Task", name) for name in names]
			self.assertTrue(all((task.status, task.round_status) == ("Working", "Finalizing") for task in tasks))
			data = frappe.parse_json(tasks[0].failure_metadata)["pending_vote"]
			self.assertEqual(len(data["votes"]), 2)
			self.assertTrue(data["automatic"])
			self.assertEqual(data["cycle_guard"]["transition_count"], 1)
			self.assertEqual(len(data["cycle_guard"]["visited"]), 1)
			self.assertEqual(frappe.db.count("Comment", scope), comments)
			queue = frappe.get_doc("Submission Queue", tasks[0].submission_queue)
			self.assertEqual(frappe.db.count("Submission Queue", {"ref_doctype": "Issue", "ref_docname": doc.name}), 1)
			submitted = frappe.get_doc("Issue", doc.name)
			submitted.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			queue.background_submission(submitted, "Submit")
			frappe.set_user("Administrator")
			self.assertEqual(queue.reload().status, "Failed", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Open", 0))
			for task in tasks:
				task.reload()
				self.assertEqual((task.status, task.round_status), ("Working", "Open"))
				self.assertFalse(task.reused_from_workflow_task)
				self.assertTrue(frappe.db.exists("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"}))
			for name, snapshot in prior.items():
				self.assertEqual(frappe.get_doc("Workflow Task", name).as_dict(), snapshot)
			self.assertEqual(frappe.db.count("Comment", scope), comments)
			frappe.db.set_value("Workflow Transition", workflow.transitions[1].name, "allowed", "System Manager")
			frappe.clear_cache(doctype="Workflow")
			frappe.get_meta("Issue").is_submittable = 1
			frappe.get_meta("Issue").queue_in_background = 1
			doc.reload()
			winner = engine._apply_automatic_votes(doc, tasks, engine._parse_manifest(tasks[0]), fingerprint)
			queue = frappe.get_doc("Submission Queue", winner["pending_submission"])
			submitted = frappe.get_doc("Issue", doc.name)
			submitted.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			queue.background_submission(submitted, "Submit")
			frappe.set_user("Administrator")
			self.assertEqual(queue.reload().status, "Finished", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Closed", 1))
			for task in tasks:
				task.reload()
				self.assertEqual(task.completion_source, "Automatic Unchanged")
				self.assertIn(task.reused_from_workflow_task, prior)
				self.assertFalse(task.failure_metadata)

	def test_native_worker_keeps_accepted_votes_when_rebuild_successor_fails(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].condition = f"frappe.session.user == {self.user!r}"
		workflow.transitions[1].allowed = self.empty_role
		workflow.save(ignore_permissions=True)
		frappe.db.set_value("Workflow Document State", workflow.states[1].name, "doc_status", "1")
		frappe.clear_cache(doctype="Workflow")
		meta = frappe.get_meta("Issue")
		with patch.object(meta, "is_submittable", 1), patch.object(meta, "queue_in_background", 1), \
			patch("frappe.utils.scheduler.is_scheduler_inactive", return_value=False), \
			patch.object(DinextSubmissionQueue, "queue_action"), patch.object(frappe.db, "commit"), \
			patch("frappe.core.doctype.submission_queue.submission_queue.get_current_job", return_value=SimpleNamespace(id="test-native-rebuild-admission")):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Rebuild queued admission", "status": "Open"}).insert(ignore_permissions=True)
			task = frappe.get_doc("Workflow Task", frappe.db.get_value("Workflow Task", {
				"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user}))
			engine.complete_task(task, task.available_workflow_transitions[0], comment="Already accepted",
				completion_source="Manual", content_fingerprint=engine.get_content_fingerprint(doc, workflow))
			task.reload()
			accepted_at = task.completed_at
			winner = engine._reached_winner(task.approval_round_id, engine._parse_manifest(task))
			self.assertFalse(engine._finalize_round(doc, task.approval_round_id, winner))
			task.reload()
			data = frappe.parse_json(task.failure_metadata)["pending_vote"]
			self.assertEqual(data["votes"], [])
			self.assertTrue(data["preserve_completed"])
			self.assertEqual(engine._vote_result(task, doc, transitioned=False)["pending_submission"], task.submission_queue)
			queue = frappe.get_doc("Submission Queue", task.submission_queue)
			submitted = frappe.get_doc("Issue", doc.name)
			submitted.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			queue.background_submission(submitted, "Submit")
			frappe.set_user("Administrator")
			self.assertEqual(queue.reload().status, "Failed", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Open", 0))
			task.reload()
			self.assertEqual((task.status, task.round_status), ("Completed", "Stalled"))
			self.assertEqual((task.completed_at, task.vote_comment), (accepted_at, "Already accepted"))
			self.assertEqual(frappe.parse_json(task.failure_metadata)["reason"], "no_eligible_approvers")
			frappe.db.set_value("Workflow Transition", workflow.transitions[1].name, "allowed", "System Manager")
			frappe.clear_cache(doctype="Workflow")
			frappe.get_meta("Issue").is_submittable = 1
			frappe.get_meta("Issue").queue_in_background = 1
			doc.reload()
			self.assertFalse(engine._finalize_round(doc, task.approval_round_id, winner))
			queue = frappe.get_doc("Submission Queue", task.reload().submission_queue)
			submitted = frappe.get_doc("Issue", doc.name)
			submitted.status = "Closed"
			frappe.set_user(queue.enqueued_by)
			queue.background_submission(submitted, "Submit")
			frappe.set_user("Administrator")
			self.assertEqual(queue.reload().status, "Finished", queue.exception)
			self.assertEqual((doc.reload().status, doc.docstatus), ("Closed", 1))
			self.assertEqual((task.reload().completed_at, task.vote_comment), (accepted_at, "Already accepted"))
