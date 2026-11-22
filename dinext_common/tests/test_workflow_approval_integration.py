import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkflowApprovalIntegration(FrappeTestCase):
	workflow_name = "_Test Parallel Approval Workflow"
	action_name = "_Test Approve"
	reopen_action_name = "_Test Reopen"
	user = "parallel-approver@example.com"

	def setUp(self):
		super().setUp()
		self.previous_flag = frappe.conf.get("enable_parallel_workflow_approval")
		frappe.conf.enable_parallel_workflow_approval = False
		# Keep the one-schema integration fixture independent of other active scenarios.
		frappe.db.set_value("Workflow", {"document_type": "Issue"}, "is_active", 0)
		self._ensure_master("Workflow State", "Open", {"workflow_state_name": "Open"})
		self._ensure_master("Workflow State", "Closed", {"workflow_state_name": "Closed"})
		self._ensure_master(
			"Workflow Action Master",
			self.action_name,
			{"workflow_action_name": self.action_name},
		)
		self._ensure_master(
			"Workflow Action Master",
			self.reopen_action_name,
			{"workflow_action_name": self.reopen_action_name},
		)
		if not frappe.db.exists("User", self.user):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": self.user,
					"first_name": "Parallel Approver",
					"enabled": 1,
					"user_type": "System User",
					"send_welcome_email": 0,
				}
			)
			user.append("roles", {"role": "System Manager"})
			user.insert(ignore_permissions=True)
		elif not frappe.db.exists(
			"Has Role",
			{"parent": self.user, "parenttype": "User", "role": "System Manager"},
		):
			user = frappe.get_doc("User", self.user)
			user.append("roles", {"role": "System Manager"})
			user.save(ignore_permissions=True)
		if frappe.db.exists("Workflow", self.workflow_name):
			frappe.delete_doc("Workflow", self.workflow_name, force=True)
		workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": self.workflow_name,
				"document_type": "Issue",
				"workflow_state_field": "status",
				"is_active": 1,
				"send_email_alert": 0,
				"states": [
					{"state": "Open", "doc_status": "0", "allow_edit": "All"},
					{"state": "Closed", "doc_status": "0", "allow_edit": "All"},
				],
				"transitions": [
					{
						"state": "Open",
						"action": self.action_name,
						"next_state": "Closed",
						"allowed": "System Manager",
						"allow_self_approval": 1,
						"custom_transition_uuid": "_test-transition",
						"custom_parallel_approval_policy": "Any",
						"custom_auto_complete_unchanged": 1,
					},
					{
						"state": "Closed",
						"action": self.reopen_action_name,
						"next_state": "Open",
						"allowed": "System Manager",
						"allow_self_approval": 1,
						"custom_transition_uuid": "_test-reopen-transition",
						"custom_parallel_approval_policy": "Any",
					},
				],
			}
		)
		workflow.insert(ignore_permissions=True)
		# Keep the integration fixture independent of site-specific role permissions.
		for doctype, access in (
			("Issue", {"read": 1, "write": 1, "create": 1}),
			("Workflow Task", {"read": 1}),
		):
			filters = {"parent": doctype, "role": "System Manager", "permlevel": 0}
			if permission := frappe.db.get_value("Custom DocPerm", filters):
				frappe.db.set_value("Custom DocPerm", permission, access)
			else:
				frappe.get_doc({
					"doctype": "Custom DocPerm", "parenttype": "DocType", "parentfield": "permissions",
					**filters, **access,
				}).insert(ignore_permissions=True)
			frappe.clear_cache(doctype=doctype)
		frappe.conf.enable_parallel_workflow_approval = True

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.conf.enable_parallel_workflow_approval = self.previous_flag
		frappe.clear_cache(doctype="Issue")
		frappe.clear_cache(doctype="Workflow Task")
		super().tearDown()

	def _ensure_master(self, doctype, name, values):
		if not frappe.db.exists(doctype, name):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(ignore_permissions=True)

	def test_round_vote_transition_and_standard_projections(self):
		source = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "Approval integration source",
				"status": "Open",
			}
		).insert(ignore_permissions=True)

		task_names = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": "Issue",
				"reference_name": source.name,
				"status": "Working",
			},
			pluck="name",
		)
		self.assertGreaterEqual(len(task_names), 1)
		task = frappe.get_doc("Workflow Task", task_names[0])
		self.assertEqual(task.available_workflow_transitions[0].action, self.action_name)
		self.assertTrue(
			frappe.db.exists(
				"Workflow Action",
				{"custom_workflow_task": task.name, "status": "Open"},
			)
		)
		self.assertTrue(
			frappe.db.exists(
				"ToDo",
				{
					"reference_type": "Workflow Task",
					"reference_name": task.name,
					"allocated_to": task.approver,
					"status": "Open",
				},
			)
		)

		frappe.set_user(task.approver)
		from dinext_common.workflow_approval.api import vote

		result = vote(
			task.name,
			transition_uuid=task.available_workflow_transitions[0].transition_uuid,
			request_id="integration-vote-1",
		)

		self.assertTrue(result["transitioned"])
		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Closed")
		self.assertEqual(frappe.db.get_value("Workflow Task", task.name, "status"), "Completed")
		self.assertEqual(
			frappe.db.get_value("Workflow Task", task.name, "round_status"),
			"Transitioned",
		)
		self.assertFalse(
			frappe.db.exists(
				"Workflow Action",
				{"custom_workflow_task": task.name, "status": "Open"},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				"Workflow Action",
				{
					"reference_doctype": "Issue",
					"reference_name": source.name,
					"custom_workflow_task": ("is", "not set"),
				},
			)
		)

	def test_same_action_uses_the_selected_transition_uuid(self):
		from dinext_common.workflow_approval import engine

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.append("transitions", {
			"state": "Open", "action": self.action_name, "next_state": "Open",
			"allowed": "System Manager", "allow_self_approval": 1,
			"custom_transition_uuid": "_test-same-action",
		})
		workflow.save(ignore_permissions=True)
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Exact workflow choice", "status": "Open"}).insert()
		task = frappe.get_doc("Workflow Task", {"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user})

		frappe.set_user(self.user)
		result = engine.cast_vote(task.name, transition_uuid="_test-transition")

		self.assertTrue(result["transitioned"])
		self.assertEqual((doc.reload().status, doc.docstatus), ("Closed", 0))
		self.assertEqual(task.reload().transition_uuid, "_test-transition")

	def test_finalizing_self_transition_applies_native_update_once(self):
		from dinext_common.workflow_approval import engine, finalization

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].next_state = "Open"
		workflow.transitions[0].custom_auto_complete_unchanged = 0
		workflow.save(ignore_permissions=True)
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Original subject", "status": "Open"}).insert()
		task = frappe.get_doc("Workflow Task", {
			"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user,
		})
		frappe.db.set_value(
			"Workflow Document State", workflow.states[0].name,
			{"update_field": "subject", "update_value": "Native self-transition applied"},
		)
		transition = task.available_workflow_transitions[0]
		engine.complete_task(task, transition, comment="", completion_source="Manual",
			content_fingerprint=engine.get_content_fingerprint(doc, workflow))
		engine._set_round_values(task.approval_round_id, {"round_status": "Finalizing", "finalization_status": "Queued"})

		finalization.repair_round(task.approval_round_id)
		self.assertEqual((doc.reload().status, doc.docstatus, doc.subject), ("Open", 0, "Native self-transition applied"))
		self.assertEqual(task.reload().round_status, "Transitioned")
		count = frappe.db.count("Comment", {"reference_doctype": doc.doctype, "reference_name": doc.name})
		finalization.repair_round(task.approval_round_id)
		self.assertEqual(frappe.db.count("Comment", {"reference_doctype": doc.doctype, "reference_name": doc.name}), count)

	def test_false_actions_do_not_block_and_availability_can_return_while_process_is_pinned(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.scenarios import service

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[1].condition = 'doc.subject == "Reopen available"'
		workflow.append("transitions", {
			"state": "Open", "action": self.reopen_action_name, "next_state": "Open",
			"allowed": "System Manager", "allow_self_approval": 1, "condition": "False",
			"custom_transition_uuid": "_test-currently-inapplicable",
		})
		workflow.save(ignore_permissions=True)
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Reopen unavailable", "status": "Open"}).insert()
		scope = {"reference_doctype": "Issue", "reference_name": doc.name, "approver": self.user}
		task = frappe.get_doc("Workflow Task", scope)
		self.assertEqual([row.transition_uuid for row in task.available_workflow_transitions], ["_test-transition"])
		process_id = service.get_context(doc)["process_id"]

		self.assertTrue(engine.cast_vote(task.name, transition_uuid="_test-transition")["transitioned"])
		self.assertEqual(doc.reload().status, "Closed")
		self.assertEqual(service.get_context(doc)["process_id"], process_id)
		self.assertEqual(service.get_context(doc)["process_status"], "Running")
		self.assertFalse(frappe.db.exists("Workflow Task", {**scope, "status": "Working"}))

		doc.subject = "Reopen available"
		doc.save()
		new_task = frappe.get_doc("Workflow Task", {**scope, "status": "Working"})
		self.assertEqual(new_task.workflow_process, process_id)
		self.assertEqual([row.transition_uuid for row in new_task.available_workflow_transitions], ["_test-reopen-transition"])

	def test_inapplicable_action_does_not_prevent_content_reset(self):
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].custom_reset_on_change = 1
		workflow.append("transitions", {
			"state": "Open", "action": self.reopen_action_name, "next_state": "Open",
			"allowed": "System Manager", "allow_self_approval": 1, "condition": "False",
			"custom_transition_uuid": "_test-inapplicable-with-reset",
		})
		workflow.save(ignore_permissions=True)
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Original content", "status": "Open"}).insert()
		scope = {"reference_doctype": doc.doctype, "reference_name": doc.name, "approver": self.user}
		original = frappe.get_doc("Workflow Task", scope)

		doc.subject = "Changed content"
		doc.save()

		self.assertEqual((original.reload().status, original.round_status), ("Cancelled", "Cancelled"))
		replacement = frappe.get_doc("Workflow Task", {**scope, "status": "Working"})
		self.assertNotEqual(replacement.approval_round_id, original.approval_round_id)

	def test_condition_evaluation_failure_reports_the_blocked_transition(self):
		from dinext_common.workflow_approval import engine

		workflow = frappe.get_doc("Workflow", self.workflow_name)
		# Runtime failure under a role member, after metadata validation has run.
		frappe.db.set_value("Workflow Transition", workflow.transitions[0].name, "condition", "1 / 0")
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Condition evaluation failure", "status": "Open"})
		with self.assertRaises(engine.NoEligibleApproversError) as caught:
			doc.insert()
		self.assertEqual(caught.exception.details["code"], "no_eligible_approvers")
		self.assertEqual(caught.exception.details["transitions"], [{
			"transition_uuid": "_test-transition", "action": self.action_name,
			"next_state": "Closed", "role": workflow.transitions[0].allowed,
		}])

	def test_configuration_restores_a_withdrawn_assignment_and_expires_its_old_link(self):
		from urllib.parse import urlsplit

		from dinext_common.workflow_approval import engine, projections, signed_links

		role = "_Test Restored Approver"
		self._ensure_master("Role", role, {"role_name": role})
		second = "workflow-restored-approver@example.com"
		if not frappe.db.exists("User", second):
			frappe.get_doc({
				"doctype": "User", "email": second, "first_name": "Restored Approver",
				"send_welcome_email": 0, "roles": [{"role": role}, {"role": "System Manager"}],
			}).insert(ignore_permissions=True)
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].condition = f"frappe.session.user == {self.user!r}"
		workflow.append("transitions", {
			"state": "Open", "action": self.reopen_action_name, "next_state": "Open",
			"allowed": role, "allow_self_approval": 1, "custom_transition_uuid": "_test-withdrawn",
		})
		workflow.save(ignore_permissions=True)
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Restore withdrawn action", "status": "Open"}).insert()
		task = frappe.get_doc("Workflow Task", {"reference_doctype": "Issue", "reference_name": doc.name, "approver": second})
		old_action = signed_links._open_action(task.name)
		old_key = signed_links.ensure_delivery_key(task.name)
		old_action.db_set("custom_notification_status", "Enqueued", update_modified=False)
		delivery = projections.delivery_snapshot(task.reload())
		withdrawn = workflow.transitions[-1].as_dict()
		workflow.remove(workflow.transitions[-1])
		workflow.save(ignore_permissions=True)
		engine.reconcile_source(doc)
		self.assertEqual(task.reload().status, "Cancelled")

		for key in ("name", "parent", "parenttype", "parentfield", "idx"):
			withdrawn.pop(key, None)
		workflow.append("transitions", withdrawn)
		workflow.save(ignore_permissions=True)
		engine.reconcile_source(doc)
		engine.reconcile_source(doc)

		self.assertEqual((task.reload().status, task.round_status), ("Working", "Open"))
		self.assertEqual([row.transition_uuid for row in task.available_workflow_transitions], ["_test-withdrawn"])
		self.assertEqual(frappe.db.count("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"}), 1)
		self.assertEqual(frappe.db.count("ToDo", {"reference_type": "Workflow Task", "reference_name": task.name, "status": "Open"}), 1)
		self.assertIsNone(signed_links._open_action(task.name, old_key))
		url = signed_links.get_task_action_url(task, task.available_workflow_transitions[0])
		link = urlsplit(url)
		self.assertFalse(bool(link.query))
		current_key = signed_links._read_signed_email_preview(link.fragment)["delivery_key"]
		self.assertNotEqual(current_key, old_key)
		self.assertTrue(signed_links._open_action(task.name, current_key))
		self.assertEqual(old_action.reload().custom_delivery_key, old_key)
		self.assertEqual(projections.delivery_snapshot(task)["custom_notification_status"], delivery["custom_notification_status"])

	def test_confirmation_rechecks_link_identity_after_locking_the_source(self):
		from dinext_common.workflow_approval import engine, projections, signed_links

		doc = frappe.get_doc({"doctype": "Issue", "subject": "Concurrent signed confirmation", "status": "Open"}).insert()
		task = frappe.get_doc("Workflow Task", {
			"reference_doctype": doc.doctype, "reference_name": doc.name, "approver": self.user,
		})
		key = signed_links.ensure_delivery_key(task.name)
		command = {
			"task_name": task.name, "transition_uuid": "_test-transition", "user": self.user, "delivery_key": key,
		}
		cast_vote = engine.cast_vote

		def vote_after_configuration_changed(*args, **kwargs):
			snapshot = projections.delivery_snapshot(task.reload())
			snapshot["configuration_restored"] = True
			engine._set_task_values(task.name, {"notification_delivery_snapshot": frappe.as_json(snapshot)})
			return cast_vote(*args, **kwargs)

		frappe.set_user(self.user)
		with (
			patch.object(signed_links, "_peek_command", return_value=command),
			patch.object(engine, "cast_vote", side_effect=vote_after_configuration_changed),
			patch.object(signed_links, "_show_expired_link") as expired,
		):
			signed_links.confirm_action("already-issued-command")
		expired.assert_called_once()
		self.assertEqual(doc.reload().status, "Open")
		self.assertEqual(task.reload().status, "Working")

	def test_missing_successor_rolls_back_only_the_deciding_vote(self):
		from dinext_common.workflow_approval import engine, request_receipts, signed_links

		second = "parallel-deciding-approver@example.com"
		if not frappe.db.exists("User", second):
			frappe.get_doc({
				"doctype": "User", "email": second, "first_name": "Deciding Approver",
				"send_welcome_email": 0, "roles": [{"role": "System Manager"}],
			}).insert(ignore_permissions=True)
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].allowed = "System Manager"
		workflow.transitions[0].custom_parallel_approval_policy = "All"
		workflow.transitions[0].condition = f"frappe.session.user in {[self.user, second]!r}"
		role = "_Test Empty Workflow Approval"
		self._ensure_master("Role", role, {"role_name": role})
		workflow.transitions[1].allowed = role
		action = "_Test Hold"
		self._ensure_master("Workflow Action Master", action, {"workflow_action_name": action})
		self._ensure_master("Workflow State", "On Hold", {"workflow_state_name": "On Hold"})
		workflow.append("states", {"state": "On Hold", "doc_status": "0", "allow_edit": "All", "is_optional_state": 1})
		workflow.append("transitions", {
			"state": "Closed", "action": action, "next_state": "On Hold", "allowed": role,
			"condition": "True", "allow_self_approval": 1, "custom_transition_uuid": "_test-hold-transition",
		})
		workflow.save(ignore_permissions=True)

		doc = frappe.get_doc({"doctype": "Issue", "subject": "Blocked successor round", "status": "Open"})
		doc.insert(ignore_permissions=True)
		scope = {"reference_doctype": doc.doctype, "reference_name": doc.name}
		tasks = {r.approver: r.name for r in frappe.get_all("Workflow Task", filters=scope, fields=["approver", "name"])}
		self.assertEqual(set(tasks), {self.user, second})
		first = engine.cast_vote(tasks[self.user], action=self.action_name, comment="First accepted vote")
		self.assertFalse(first["transitioned"])
		first_task = frappe.get_doc("Workflow Task", tasks[self.user]).as_dict()
		comment_filters = {"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": "Workflow"}
		comments = frappe.db.count("Comment", comment_filters)
		frappe.publish_realtime("workflow_test_preserved", user="Administrator", after_commit=True)
		callbacks = tuple(frappe.db.after_commit._functions)
		events = list(frappe.local._realtime_log)

		def notify(*_args):
			frappe.publish_realtime("workflow_test_rolled_back", user="Administrator", after_commit=True)

		request_id = frappe.generate_hash(length=20)
		with (
			patch.object(engine, "_dispatch_vote_completed", side_effect=notify),
			self.assertRaises(engine.WorkflowApprovalConflictError) as caught,
		):
			engine.cast_vote(tasks[second], action=self.action_name, comment="Deciding vote", request_id=request_id)

		self.assertEqual(doc.reload().status, "Open")
		self.assertEqual(frappe.get_doc("Workflow Task", tasks[self.user]).as_dict(), first_task)
		task = frappe.get_doc("Workflow Task", tasks[second])
		self.assertEqual((task.status, task.round_status), ("Working", "Open"))
		self.assertTrue(frappe.db.exists("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"}))
		self.assertEqual(frappe.db.count("Workflow Task", scope), 2)
		self.assertEqual(frappe.db.count("Comment", comment_filters), comments)
		self.assertEqual(tuple(frappe.db.after_commit._functions), callbacks)
		self.assertEqual(frappe.local._realtime_log, events)
		self.assertFalse(request_receipts.get(request_receipts.request_key("Vote", request_id)))
		details = getattr(caught.exception, "details", {})
		self.assertEqual(details.get("code"), "no_eligible_approvers")
		self.assertEqual((details["workflow"], details["state"]), (workflow.name, "Closed"))
		self.assertEqual(
			[(row["action"], row["next_state"], row["role"]) for row in details["transitions"]],
			[(self.reopen_action_name, "Open", role), (action, "On Hold", role)],
		)

		link = signed_links._issue_command({
			"task_name": task.name,
			"transition_uuid": "_test-transition",
			"user": second,
			"delivery_key": signed_links._open_action(task.name).custom_delivery_key,
		})
		self.addCleanup(signed_links._consume_command, link)
		frappe.set_user(second)
		with patch.object(frappe, "respond_as_web_page") as response:
			signed_links.confirm_action(link, comment="Same attempted vote from a link")
		self.assertEqual(response.call_args.kwargs["http_status_code"], 409)
		self.assertIn(action, response.call_args.args[1])
		self.assertIsNotNone(signed_links._peek_command(link))
		self.assertEqual(frappe.db.get_value("Workflow Task", task.name, "status"), "Working")
		frappe.set_user("Administrator")

		for row in workflow.transitions[1:]:
			row.allowed = "System Manager"
		workflow.save(ignore_permissions=True)
		result = engine.cast_vote(tasks[second], action=self.action_name, comment="Deciding vote", request_id=request_id)
		self.assertTrue(result["transitioned"])
		self.assertEqual(doc.reload().status, "Closed")
		self.assertEqual(frappe.db.get_value("Workflow Task", tasks[self.user], "completed_at"), first_task.completed_at)
		self.assertTrue(frappe.db.exists("Workflow Task", {**scope, "workflow_state": "Closed", "status": "Working"}))

	def test_direct_workflow_state_change_is_rejected(self):
		source = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "Approval bypass source",
				"status": "Open",
			}
		).insert(ignore_permissions=True)
		source.status = "Closed"
		with self.assertRaises(Exception) as raised:
			source.save(ignore_permissions=True)
		self.assertIn("Workflow state can only be changed", str(raised.exception))

	def test_unchanged_resubmission_reuses_same_approver_vote(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.api import vote

		exclusions = {
			"resolution_date",
			"resolution_details",
			"opening_date",
			"opening_time",
			"first_response_time",
			"resolution_time",
			"user_resolution_time",
		}
		with patch.object(engine, "_fingerprint_exclusions", return_value=exclusions):
			source = frappe.get_doc(
				{
					"doctype": "Issue",
					"subject": "Unchanged approval reuse",
					"status": "Open",
				}
			).insert(ignore_permissions=True)
			first_task = frappe.get_doc(
				"Workflow Task",
				frappe.get_all(
					"Workflow Task",
					filters={
						"reference_doctype": "Issue",
						"reference_name": source.name,
						"status": "Working",
					},
					pluck="name",
					limit=1,
				)[0],
			)
			frappe.set_user(first_task.approver)
			vote(
				first_task.name,
				transition_uuid="_test-transition",
				request_id="reuse-first",
			)

			reopen_task = frappe.get_doc(
				"Workflow Task",
				frappe.get_all(
					"Workflow Task",
					filters={
						"reference_doctype": "Issue",
						"reference_name": source.name,
						"status": "Working",
						"workflow_state": "Closed",
					},
					pluck="name",
					limit=1,
				)[0],
			)
			frappe.set_user(reopen_task.approver)
			vote(
				reopen_task.name,
				transition_uuid="_test-reopen-transition",
				request_id="reuse-reopen",
			)

		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Closed")
		auto_tasks = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": "Issue",
				"reference_name": source.name,
				"transition_uuid": "_test-transition",
				"completion_source": "Automatic Unchanged",
			},
			fields=["name", "reused_from_workflow_task"],
		)
		self.assertEqual(len(auto_tasks), 1)
		self.assertEqual(auto_tasks[0].reused_from_workflow_task, first_task.name)

	def _source_with_deletion_history(self):
		from dinext_common.workflow_approval import engine
		from dinext_common.workflow_approval.api import vote

		frappe.set_user("Administrator")
		frappe.conf.enable_parallel_workflow_approval = True
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.is_active = 1
		for transition in workflow.transitions:
			if transition.action == self.reopen_action_name:
				transition.custom_parallel_approval_policy = "All"
		workflow.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		with patch.object(engine, "_eligible_approvers", return_value=["Administrator", self.user]):
			source = frappe.get_doc(
				{"doctype": "Issue", "subject": "Source deletion integration", "status": "Open"}
			).insert(ignore_permissions=True, set_name="_TestDeleteSource-" + frappe.generate_hash(length=12))
			# This helper deliberately snapshots a synthetic cohort. Give its voter
			# actual source read access before exercising deletion/history behavior.
			frappe.share.add("Issue", source.name, self.user, read=1)
			from dinext_common.workflow_approval.permissions import _has_source_read_permission

			self.assertTrue(_has_source_read_permission({
				"reference_doctype": "Issue", "reference_name": source.name,
			}, self.user))
			history = frappe.get_doc(
				"Workflow Task",
				{"reference_doctype": "Issue", "reference_name": source.name, "approver": self.user},
			)
			frappe.set_user(self.user)
			result = vote(
				history.name,
				transition_uuid="_test-transition",
				comment="Historical approved vote",
				request_id=frappe.generate_hash(length=20),
			)
			self.assertTrue(result["transitioned"])
			partial = frappe.get_doc(
				"Workflow Task",
				{
					"reference_doctype": "Issue",
					"reference_name": source.name,
					"approver": self.user,
					"status": "Working",
					"workflow_state": "Closed",
				},
			)
			result = vote(
				partial.name,
				transition_uuid="_test-reopen-transition",
				comment="Accepted before source deletion",
				request_id=frappe.generate_hash(length=20),
			)
			self.assertFalse(result["transitioned"])
		frappe.set_user("Administrator")
		return source, history.reload(), partial.reload()

	def _queued_source(self, source):
		queue = frappe.new_doc("Submission Queue")
		queue.ref_doctype = source.doctype
		queue.ref_docname = source.name
		# Keep the real queue record and controller, without starting a worker.
		with patch.object(queue, "queue_action"):
			queue.insert(source, "Submit")
		self.assertEqual(queue.status, "Queued")
		return queue

	def _delete_source_and_check_history(self, source, history, partial):
		from frappe.model.delete_doc import check_if_doc_is_dynamically_linked

		from dinext_common.workflow_approval.api import get_my_queue

		filters = {"reference_doctype": source.doctype, "reference_name": source.name}
		tasks = frappe.get_all("Workflow Task", filters=filters, fields=["name", "status"])
		history_before = history.as_dict()
		partial_before = partial.as_dict()
		queued = self._queued_source(source)
		frappe.get_doc(
			{
				"doctype": "Workflow Action",
				**filters,
				"status": "Completed",
				"user": self.user,
				"permitted_roles": [{"role": "System Manager"}],
			}
		).insert(ignore_permissions=True)
		checked = []

		def check_links(doc, method="Delete"):
			if doc.doctype == source.doctype and doc.name == source.name:
				self.assertEqual(frappe.db.get_value("Submission Queue", queued.name, "status"), "Failed")
				self.assertFalse(frappe.db.exists("Workflow Action", filters))
				checked.append(doc.name)
			return check_if_doc_is_dynamically_linked(doc, method)

		with patch("frappe.model.delete_doc.check_if_doc_is_dynamically_linked", side_effect=check_links):
			frappe.delete_doc(source.doctype, source.name, ignore_permissions=True)
		self.assertEqual(checked, [source.name])
		self.assertFalse(frappe.db.exists(source.doctype, source.name))
		for task in tasks:
			self.assertTrue(frappe.db.get_value("Workflow Task", task.name, "source_deleted_at"))
			if task.status == "Working":
				cancelled = frappe.get_doc("Workflow Task", task.name)
				self.assertEqual(cancelled.status, "Cancelled")
				self.assertEqual(cancelled.round_status, "Cancelled")
				self.assertTrue(cancelled.cancelled_at)
				self.assertEqual(cancelled.cancellation_reason, frappe._("Source document deleted"))
		self.assertFalse(
			frappe.db.exists(
				"ToDo",
				{
					"reference_type": "Workflow Task",
					"reference_name": ["in", [t.name for t in tasks]],
					"status": "Open",
				},
			)
		)
		self.assertFalse(any(row.reference_name == source.name for row in get_my_queue()))
		history_after = history.reload().as_dict()
		history_before.pop("source_deleted_at", None)
		history_after.pop("source_deleted_at", None)
		self.assertEqual(history_after, history_before)
		partial_after = partial.reload().as_dict()
		self.assertEqual(partial_after["status"], "Completed")
		self.assertEqual(partial_after["round_status"], "Cancelled")
		for field in ("source_deleted_at", "round_status", "finalization_status"):
			partial_before.pop(field, None)
			partial_after.pop(field, None)
		self.assertEqual(partial_after, partial_before)

	def test_delete_source_closes_every_active_round_status(self):
		from dinext_common.workflow_approval import engine

		for status in engine.ACTIVE_ROUND_STATUSES:
			with self.subTest(round_status=status):
				source, history, partial = self._source_with_deletion_history()
				engine._set_round_values(
					partial.approval_round_id,
					{"round_status": status, "finalization_status": "Queued"},
				)
				partial.reload()
				self._delete_source_and_check_history(source, history, partial)
				finalizations = frappe.get_all(
					"Workflow Task",
					filters={"approval_round_id": partial.approval_round_id},
					pluck="finalization_status",
				)
				self.assertEqual(set(finalizations), {"Failed"})

	def test_delete_source_when_engine_is_disabled(self):
		source, history, partial = self._source_with_deletion_history()
		frappe.conf.enable_parallel_workflow_approval = False
		self._delete_source_and_check_history(source, history, partial)

	def test_delete_source_without_active_workflow(self):
		from frappe.model.workflow import get_workflow_name

		source, history, partial = self._source_with_deletion_history()
		frappe.db.set_value("Workflow", self.workflow_name, "is_active", 0)
		frappe.clear_cache(doctype="Issue")
		self.assertFalse(get_workflow_name("Issue"))
		self._delete_source_and_check_history(source, history, partial)

	def test_deleting_source_keeps_other_source_tasks_unchanged(self):
		source, history, partial = self._source_with_deletion_history()
		other, _history, _partial = self._source_with_deletion_history()
		other_tasks = {
			name: frappe.get_doc("Workflow Task", name).as_dict()
			for name in frappe.get_all(
				"Workflow Task",
				filters={"reference_doctype": "Issue", "reference_name": other.name},
				pluck="name",
			)
		}
		self._delete_source_and_check_history(source, history, partial)
		for name, expected in other_tasks.items():
			self.assertEqual(frappe.get_doc("Workflow Task", name).as_dict(), expected)

	def test_delete_source_without_tasks_removes_blocking_links(self):
		from frappe.model.delete_doc import check_if_doc_is_dynamically_linked

		frappe.conf.enable_parallel_workflow_approval = False
		frappe.db.set_value("Workflow", self.workflow_name, "is_active", 0)
		frappe.clear_cache(doctype="Issue")
		source = frappe.get_doc(
			{"doctype": "Issue", "subject": "Legacy deletion source", "status": "Open"}
		).insert(ignore_permissions=True, set_name="_TestDeleteSource-" + frappe.generate_hash(length=12))
		filters = {"reference_doctype": "Issue", "reference_name": source.name}
		self.assertFalse(frappe.db.exists("Workflow Task", filters))
		queue = self._queued_source(source)
		frappe.get_doc({"doctype": "Workflow Action", **filters, "status": "Open"}).insert(
			ignore_permissions=True
		)

		def check_links(doc, method="Delete"):
			if doc.doctype == "Issue" and doc.name == source.name:
				self.assertEqual(frappe.db.get_value("Submission Queue", queue.name, "status"), "Failed")
				self.assertFalse(frappe.db.exists("Workflow Action", filters))
			return check_if_doc_is_dynamically_linked(doc, method)

		with patch("frappe.model.delete_doc.check_if_doc_is_dynamically_linked", side_effect=check_links):
			frappe.delete_doc("Issue", source.name, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Issue", source.name))

	def test_delete_source_cancels_legacy_task_without_round(self):
		frappe.db.set_value("Workflow", self.workflow_name, "is_active", 0)
		frappe.clear_cache(doctype="Issue")
		source = frappe.get_doc(
			{"doctype": "Issue", "subject": "Legacy task deletion", "status": "Open"}
		).insert(ignore_permissions=True, set_name="_TestDeleteSource-" + frappe.generate_hash(length=12))
		task = frappe.get_doc(
			{
				"doctype": "Workflow Task",
				"name": "WT-legacy-delete-" + frappe.generate_hash(length=12),
				"doc": "Issue",
				"wt_docname": source.name,
				"reference_doctype": "Issue",
				"reference_name": source.name,
				"approver": self.user,
				"user": self.user,
				"status": "Working",
			}
		).insert(ignore_permissions=True)
		self.assertFalse(task.approval_round_id)
		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"reference_type": "Workflow Task",
				"reference_name": task.name,
				"allocated_to": self.user,
				"status": "Open",
				"description": "Legacy approval",
			}
		).insert(ignore_permissions=True)
		frappe.delete_doc("Issue", source.name, ignore_permissions=True)
		task.reload()
		self.assertEqual(task.status, "Cancelled")
		self.assertEqual(task.round_status, "Cancelled")
		self.assertTrue(task.source_deleted_at)
		self.assertEqual(frappe.db.get_value("ToDo", todo.name, "status"), "Closed")


class TestWorkflowApprovalDeletionServices(unittest.TestCase):
	def test_service_deletion_does_not_archive_sources(self):
		from types import SimpleNamespace

		from dinext_common.workflow_approval import lifecycle

		with patch("dinext_common.workflow_approval.engine.archive_source") as archive:
			for doctype in lifecycle.SERVICE_DOCTYPES:
				with self.subTest(doctype=doctype):
					lifecycle.on_source_trash(SimpleNamespace(doctype=doctype, name="SERVICE"))
			archive.assert_not_called()
