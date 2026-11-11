"""Real source/round/process transactions on an isolated Frappe site."""

from __future__ import annotations

import unittest

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from dinext_common.workflow_approval import api, engine
from dinext_common.workflow_approval.scenarios import service

PREFIX = "_Test Scenario "
FIELDS = ("custom_scenario_a", "custom_scenario_b")


class TestWorkflowScenarioLifecycle(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not getattr(frappe.local, "db", None):
			raise unittest.SkipTest("Requires an isolated Frappe test site")
		create_custom_fields(
			{
				"Note": [
					dict(
						fieldname=name,
						fieldtype="Data",
						label=name,
						allow_on_submit=1,
						module="Dinext Common",
					)
					for name in FIELDS
				]
			},
			update=True,
		)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		self.old_flag = frappe.conf.get("enable_parallel_workflow_approval")
		frappe.conf.enable_parallel_workflow_approval = True
		frappe.local.workflow_scenario_cascade = None
		frappe.db.savepoint("scenario_test")
		self.user = "scenario-voter@example.com"
		self.role = "_Test Scenario Approver"
		if not frappe.db.exists("Role", self.role):
			frappe.get_doc({"doctype": "Role", "role_name": self.role}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", self.user):
			frappe.get_doc(
				dict(
					doctype="User",
					email=self.user,
					first_name="Scenario Voter",
					send_welcome_email=0,
					roles=[{"role": self.role}],
				)
			).insert(ignore_permissions=True)
		self.first_user = "scenario-first@example.com"
		if not frappe.db.exists("User", self.first_user):
			frappe.get_doc(
				dict(
					doctype="User",
					email=self.first_user,
					first_name="First Scenario Voter",
					send_welcome_email=0,
					roles=[{"role": self.role}],
				)
			).insert(ignore_permissions=True)
		self.a = self.make_workflow("A", 1, "doc.title.startswith('A')", FIELDS[0])
		self.b = self.make_workflow("B", 2, "doc.title.startswith('B')", FIELDS[1])

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="scenario_test")
		frappe.conf.enable_parallel_workflow_approval = self.old_flag
		frappe.local.workflow_scenario_cascade = None
		frappe.clear_cache(doctype="Note")

	def make_workflow(self, suffix, order, condition, field):
		states = [PREFIX + "Start " + suffix, PREFIX + "Done " + suffix]
		for state in states:
			if not frappe.db.exists("Workflow State", state):
				frappe.get_doc(
					{"doctype": "Workflow State", "workflow_state_name": state, "style": "Primary"}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Workflow Action Master", "Approve"):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": "Approve"}).insert(
				ignore_permissions=True
			)
		workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": PREFIX + suffix,
				"document_type": "Note",
				"workflow_state_field": field,
				"is_active": 1,
				"send_email_alert": 0,
				"custom_selection_order": order,
				"custom_activation_condition": condition,
				"states": [{"state": state, "doc_status": "0", "allow_edit": "All"} for state in states],
				"transitions": [
					{
						"state": states[0],
						"action": "Approve",
						"next_state": states[1],
						"allowed": self.role,
						"allow_self_approval": 1,
						"custom_parallel_approval_policy": "All",
						"custom_transition_uuid": "scenario-" + suffix,
					}
				],
			}
		)
		return workflow.insert(ignore_permissions=True)

	def source(self, title):
		return frappe.get_doc(
			dict(
				doctype="Note",
				title=title + " " + frappe.generate_hash(length=8),
				public=1,
				content="Test content",
			)
		).insert(ignore_permissions=True)

	def tasks(self, source):
		return frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": source.doctype,
				"reference_name": source.name,
				"round_status": "Open",
				"status": "Working",
			},
			fields=["*"],
		)

	def vote(self, source, user=None, request_id=None):
		user = user or self.first_user
		frappe.set_user(user)
		task = next(task for task in self.tasks(source) if task.approver == user)
		return engine.cast_vote(
			task.name,
			transition_uuid="scenario-" + ("A" if task.workflow == self.a.name else "B"),
			request_id=request_id,
		)

	def test_prepare_different_fields_and_replace_before_first_vote(self):
		source = self.source("A document")
		first = service.get_context(source)
		self.assertEqual(first["workflow"], self.a.name)
		self.assertEqual(first["process_status"], "Prepared")
		old_tasks = self.tasks(source)
		self.assertTrue(old_tasks)
		source.title = "B changed"
		source.save(ignore_permissions=True)
		context = service.get_context(source)
		self.assertEqual(context["workflow"], self.b.name)
		self.assertEqual(context["state_field"], FIELDS[1])
		self.assertNotEqual(context["process_id"], first["process_id"])
		self.assertTrue(
			all(frappe.db.get_value("Workflow Task", t.name, "status") == "Cancelled" for t in old_tasks)
		)

	def test_first_vote_pins_until_terminal_then_same_schema_repeats(self):
		source = self.source("A document")
		first = service.get_context(source)
		result = self.vote(source, request_id="pin")
		self.assertFalse(result["transitioned"])
		source.reload()
		self.assertEqual(service.get_context(source)["process_status"], "Running")
		source.title = "B changed after first vote"
		source.save(ignore_permissions=True)
		self.assertEqual(service.get_context(source)["workflow"], self.a.name)
		source.title = "A restored"
		source.save(ignore_permissions=True)
		result = self.vote(source, self.user, request_id="finish")
		self.assertTrue(result["transitioned"])
		source.reload()
		second = service.get_context(source)
		self.assertEqual(second["workflow"], self.a.name)
		self.assertNotEqual(second["process_id"], first["process_id"])
		self.assertEqual(second["process_status"], "Prepared")
		self.assertEqual(frappe.db.get_value(service.PROCESS, first["process_id"], "status"), "Completed")
		self.assertTrue(all(task.workflow_process == second["process_id"] for task in self.tasks(source)))

	def test_running_schema_ignores_disabled_flag_and_conditions(self):
		source = self.source("A document")
		self.vote(source)
		frappe.db.set_value("Workflow", self.a.name, {"is_active": 0, "custom_activation_condition": "False"})
		source.reload()
		source.title = "B now"
		source.save(ignore_permissions=True)
		self.assertEqual(service.get_context(source)["workflow"], self.a.name)
		self.assertTrue(self.vote(source, self.user)["transitioned"])
		source.reload()
		self.assertEqual(service.get_context(source)["workflow"], self.b.name)

	def test_no_match_uses_normal_save(self):
		source = self.source("Unmatched")
		self.assertIsNone(service.get_context(source)["workflow"])
		self.assertEqual(self.tasks(source), [])
		source.content = "Normal edit"
		source.save(ignore_permissions=True)

	def test_mixed_bulk_uses_own_uuid(self):
		a = self.source("A selected")
		b = self.source("B selected")
		frappe.set_user(self.first_user)
		rows = api.get_common_list_transitions("Note", [a.name, b.name])
		self.assertEqual(len(rows), 1)
		self.assertEqual({t["workflow"] for t in rows[0]["targets"]}, {self.a.name, self.b.name})
		self.assertEqual({t["transition_uuid"] for t in rows[0]["targets"]}, {"scenario-A", "scenario-B"})
		for target in rows[0]["targets"]:
			api._vote_source_action(
				"Note",
				target["name"],
				"Approve",
				transition_uuid=target["transition_uuid"],
				workflow=target["workflow"],
				process_id=target["process_id"],
				task_name=target["task_name"],
			)
		self.assertTrue(all(service.get_context(doc)["process_status"] == "Running" for doc in [a, b]))

	def test_identical_rpc_retry_does_not_vote_in_the_repeated_process(self):
		source = self.source("A retry")
		self.vote(source)
		frappe.set_user(self.user)
		api._vote_source_action(
			"Note", source.name, "Approve", transition_uuid="scenario-A", request_id="retry-me"
		)
		source.reload()
		process = service.get_context(source)["process_id"]
		new_tasks = self.tasks(source)
		result = api._vote_source_action(
			"Note", source.name, "Approve", transition_uuid="scenario-A", request_id="retry-me"
		)
		self.assertTrue(result["transitioned"])
		self.assertEqual(service.get_context(source)["process_id"], process)
		self.assertEqual([row.name for row in self.tasks(source)], [row.name for row in new_tasks])

	def test_automation_allows_repeats_but_pauses_after_twenty(self):
		frappe.db.set_value(
			"Workflow Transition", self.a.transitions[0].name, "custom_auto_complete_unchanged", 1
		)
		source = self.source("A automation")
		self.vote(source)
		self.assertTrue(self.vote(source, self.user)["transitioned"])
		source.reload()
		process = service.active_process(source)
		self.assertEqual(process.status, "Prepared")
		self.assertEqual(process.automatic_transition_count, 20)
		self.assertTrue(self.tasks(source))
		self.assertEqual(
			len(
				frappe.get_all(
					service.PROCESS, filters={"source_key": service.source_key(source), "status": "Completed"}
				)
			),
			21,
		)
		self.assertTrue(
			all("automation_paused" in (task.failure_metadata or "") for task in self.tasks(source))
		)

		self.assertEqual(
			frappe.db.count(
				"Comment",
				{
					"reference_doctype": "Note",
					"reference_name": source.name,
					"comment_type": "Workflow",
					"content": frappe._(
						"Automatic Workflow processing paused. A new user action is required."
					),
				},
			),
			1,
		)

	def test_stale_task_does_not_accept_a_vote(self):
		source = self.source("A old")
		task = next(task for task in self.tasks(source) if task.approver == self.first_user)
		old_context = service.get_context(source)
		source.title = "B replacement"
		source.save(ignore_permissions=True)
		with self.assertRaises(engine.WorkflowApprovalConflictError):
			engine.cast_vote(task.name, transition_uuid="scenario-A")
		self.assertNotEqual(old_context["process_id"], service.get_context(source)["process_id"])

	def test_configured_rework_edge_retains_process_through_reset_and_return(self):
		workflow = frappe.get_doc("Workflow", self.a.name)
		if not frappe.db.exists("Workflow Action Master", "Edit"):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": "Edit"}).insert(
				ignore_permissions=True
			)
		workflow.append(
			"transitions",
			{
				"state": workflow.states[1].state,
				"action": "Edit",
				"next_state": workflow.states[0].state,
				"allowed": self.role,
				"allow_self_approval": 1,
				"custom_transition_uuid": "scenario-edit",
				"custom_parallel_approval_policy": "Any",
			},
		)
		workflow.save(ignore_permissions=True)
		source = self.source("A rework")
		initial = service.get_context(source)
		self.vote(source)
		self.vote(source, self.user)
		source.reload()
		self.assertEqual(service.get_context(source)["process_id"], initial["process_id"])
		self.assertEqual(service.get_context(source)["state"], workflow.states[1].state)
		frappe.set_user(self.first_user)
		task = next(row for row in self.tasks(source) if row.approver == self.first_user)
		engine.cast_vote(task.name, transition_uuid="scenario-edit")
		source.reload()
		self.assertEqual(service.get_context(source)["process_id"], initial["process_id"])
		frappe.set_user("Administrator")
		round_id = self.tasks(source)[0].approval_round_id
		api.reset_round(round_id, "Rebuild after setup correction")
		self.assertEqual(service.get_context(source)["process_id"], initial["process_id"])
		self.assertNotEqual(self.tasks(source)[0].approval_round_id, round_id)

	def test_no_available_users_is_not_a_terminal_state(self):
		source = self.source("A pending")
		process = service.active_process(source)
		self.assertFalse(service.finish_transition(source))
		self.assertEqual(service.active_process(source).name, process.name)

	def test_database_prevents_two_active_instances(self):
		source = self.source("A uniqueness")
		process = service.active_process(source)
		with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
			service._insert(
				service.PROCESS,
				{
					"reference_doctype": "Note",
					"reference_name": source.name,
					"source_created_at": source.creation,
					"source_key": process.source_key,
					"active_source_key": process.source_key,
					"workflow": process.workflow,
					"status": "Prepared",
				},
			)

	def test_new_process_entry_error_keeps_completed_action(self):
		source = self.source("A entry mismatch")
		first = service.get_context(source)
		self.vote(source)
		# Running schema remains usable; only its next initial state is now incompatible.
		frappe.db.set_value("Workflow Document State", self.a.states[0].name, "doc_status", 1)
		self.assertTrue(self.vote(source, self.user)["transitioned"])
		source.reload()
		self.assertEqual(frappe.db.get_value(service.PROCESS, first["process_id"], "status"), "Completed")
		self.assertIsNone(service.get_context(source)["process_id"])
		self.assertEqual(source.get(FIELDS[0]), self.a.states[1].state)
		self.assertIn(
			self.a.name, frappe.db.get_value(service.CONTEXT, service.source_key(source), "routing_error")
		)

	def test_persisted_budget_survives_a_worker_boundary(self):
		source = self.source("A worker budget")
		service.start_cascade(source, manual=True)
		service.consume_automatic_transition(source, state_key="visited-in-worker")
		frappe.local.workflow_scenario_cascade = None
		self.assertTrue(service.automation_budget_available(source))
		self.assertFalse(service.automation_budget_available(source, state_key="visited-in-worker"))
		for index in range(19):
			service.consume_automatic_transition(source, state_key=str(index))
		frappe.local.workflow_scenario_cascade = None
		self.assertFalse(service.automation_budget_available(source))
		service.start_cascade(source, manual=True)
		self.assertTrue(service.automation_budget_available(source, state_key="visited-in-worker"))

	def test_deleted_and_recreated_source_cannot_inherit_process(self):
		source = self.source("A recreated")
		old = service.get_context(source)
		old_creation = source.creation
		frappe.delete_doc("Note", source.name, ignore_permissions=True, force=True)
		self.assertEqual(frappe.db.get_value(service.PROCESS, old["process_id"], "status"), "Archived")
		recreated = frappe.get_doc(
			dict(doctype="Note", name=source.name, title=source.name, public=1, content="Test content")
		)
		recreated.insert(ignore_permissions=True, set_name=source.name)
		self.assertEqual(recreated.name, source.name)
		self.assertNotEqual(recreated.creation, old_creation)
		self.assertNotEqual(service.get_context(recreated)["process_id"], old["process_id"])

	def test_rest_cannot_change_creation_to_escape_a_pinned_process(self):
		source = self.source("A immutable creation")
		self.vote(source)
		source.reload()
		process_id = service.get_context(source)["process_id"]
		source.creation = "2000-01-01 00:00:00"
		with self.assertRaises(service.WorkflowScenarioError):
			source.save(ignore_permissions=True)
		source.reload()
		self.assertEqual(service.get_context(source)["process_id"], process_id)

	def test_native_rename_preserves_pinned_process_and_tasks(self):
		source = self.source("A rename")
		self.vote(source)
		source.reload()
		old_name = source.name
		context = service.get_context(source)
		tasks = self.tasks(source)
		frappe.set_user("Administrator")
		new_name = "renamed-" + frappe.generate_hash(length=12)
		frappe.rename_doc(
			"Note",
			old_name,
			new_name,
			force=True,
			show_alert=False,
			rebuild_search=False,
		)
		source = frappe.get_doc("Note", new_name)
		self.assertEqual(service.get_context(source)["process_id"], context["process_id"])
		self.assertEqual({t.name for t in self.tasks(source)}, {t.name for t in tasks})
		source.title = "B after rename"
		source.save(ignore_permissions=True)
		self.assertEqual(service.get_context(source)["workflow"], self.a.name)

	def test_duplicate_repair_does_not_refinalize_the_previous_process(self):
		from unittest.mock import patch

		from dinext_common.workflow_approval import finalization

		source = self.source("A raced repair")
		self.vote(source)
		with patch.object(engine, "_finalize_round", return_value=False):
			self.vote(source, self.user)
		old_process = service.get_context(source)["process_id"]
		round_id = frappe.db.get_value(
			"Workflow Task", {"workflow_process": old_process}, "approval_round_id"
		)
		engine._set_round_values(round_id, {"round_status": "Finalizing"})
		winner = finalization._winner(frappe.get_doc("Workflow Task", engine._round_task_names(round_id)[0]))
		completed = []
		original_lock = engine._lock_domain_dependencies

		def other_worker(*args):
			if not completed:
				completed.append(True)
				engine._finalize_round(frappe.get_doc(source.doctype, source.name), round_id, winner)
			return original_lock(*args)

		with patch.object(engine, "_lock_domain_dependencies", side_effect=other_worker):
			finalization.repair_round(round_id)
		self.assertTrue(completed)
		source.reload()
		self.assertNotEqual(service.get_context(source)["process_id"], old_process)
		self.assertTrue(
			all(
				frappe.db.get_value("Workflow Task", name, "round_status") == "Transitioned"
				for name in engine._round_task_names(round_id)
			)
		)
		self.assertFalse(engine._finalize_round(source, round_id, winner))

	def test_legacy_url_only_binds_migrated_tasks_not_repeated_instances(self):
		import json

		from dinext_common.workflow_approval.signed_links import _legacy_task_is_eligible

		source = self.source("A legacy link")
		old_process = service.get_context(source)["process_id"]
		old_tasks = self.tasks(source)
		frappe.db.set_value(
			service.PROCESS, old_process, "legacy_task_names", json.dumps([t.name for t in old_tasks])
		)
		self.assertTrue(_legacy_task_is_eligible(frappe.get_doc("Workflow Task", old_tasks[0].name)))
		self.vote(source)
		self.vote(source, self.user)
		self.assertTrue(self.tasks(source))
		self.assertTrue(
			all(
				not _legacy_task_is_eligible(frappe.get_doc("Workflow Task", t.name))
				for t in self.tasks(source)
			)
		)

	def test_source_history_is_scoped_to_creation_after_recreation(self):
		source = self.source("A private history")
		frappe.set_user(self.first_user)
		task = next(row for row in self.tasks(source) if row.approver == self.first_user)
		engine.cast_vote(
			task.name,
			transition_uuid="scenario-A",
			comment="Old instance private note",
			request_id="old-note",
		)
		frappe.set_user("Administrator")
		frappe.delete_doc("Note", source.name, force=True, ignore_permissions=True)
		recreated = frappe.get_doc(
			{
				"doctype": "Note",
				"name": source.name,
				"title": source.name,
				"content": "New instance",
				"public": 1,
			}
		).insert(ignore_permissions=True, set_name=source.name)
		self.assertEqual(api.get_source_approval_history("Note", recreated.name), [])
		self.assertEqual(api.get_workflow_comments("Note", recreated.name), [])
		frappe.set_user(self.first_user)
		with self.assertRaises(engine.WorkflowApprovalConflictError):
			engine.cast_vote(task.name, transition_uuid="scenario-A", request_id="old-note")
