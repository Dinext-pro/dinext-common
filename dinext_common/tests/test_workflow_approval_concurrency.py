import multiprocessing
import os
import queue

import frappe
from frappe.tests.utils import FrappeTestCase


def _process_vote(
	site,
	sites_path,
	barrier,
	results,
	core_transition_count,
	mode,
	task_name,
	transition_uuid,
	user,
):
	frappe.init(site=site, sites_path=sites_path, force=True)
	frappe.connect()
	frappe.flags.in_test = True
	frappe.conf.enable_parallel_workflow_approval = True
	frappe.set_user(user)
	try:
		from dinext_common.workflow_approval import api, engine

		original_apply_workflow = engine.core_apply_workflow

		def counted_apply_workflow(*args, **kwargs):
			with core_transition_count.get_lock():
				core_transition_count.value += 1
			return original_apply_workflow(*args, **kwargs)

		engine.core_apply_workflow = counted_apply_workflow
		barrier.wait(timeout=60)
		if mode == "single":
			outcome = api.vote(
				task_name,
				transition_uuid=transition_uuid,
				request_id=f"process-single-{task_name}",
			)
			frappe.db.commit()
			results.put(
				{
					"pid": os.getpid(),
					"mode": mode,
					"transitioned": bool(outcome["transitioned"]),
					"failed": False,
				}
			)
			return

		outcome = api.bulk_task_vote(
			[
				{
					"task_name": task_name,
					"transition_uuid": transition_uuid,
				}
			],
			request_id=f"process-bulk-{task_name}",
		)
		frappe.db.commit()
		results.put(
			{
				"pid": os.getpid(),
				"mode": mode,
				"transitioned": bool(
					outcome["succeeded"]
					and outcome["succeeded"][0]["result"]["transitioned"]
				),
				"failed": bool(outcome["failed"]),
			}
		)
	except Exception as exc:
		frappe.db.rollback()
		results.put(
			{
				"pid": os.getpid(),
				"mode": mode,
				"transitioned": False,
				"failed": True,
				"error_type": exc.__class__.__name__,
				"error": str(exc),
			}
		)
	finally:
		frappe.destroy()


def _process_reconcile(site, sites_path, barrier, results, reference_name):
	frappe.init(site=site, sites_path=sites_path, force=True)
	frappe.connect()
	frappe.flags.in_test = True
	frappe.conf.enable_parallel_workflow_approval = True
	try:
		from dinext_common.workflow_approval.engine import reconcile_source

		barrier.wait(timeout=60)
		task_names = reconcile_source(frappe.get_doc("Issue", reference_name))
		frappe.db.commit()
		results.put(
			{
				"pid": os.getpid(),
				"failed": False,
				"task_names": sorted(task_names),
			}
		)
	except Exception as exc:
		frappe.db.rollback()
		results.put(
			{
				"pid": os.getpid(),
				"failed": True,
				"error_type": exc.__class__.__name__,
				"error": str(exc),
			}
		)
	finally:
		frappe.destroy()


class TestWorkflowApprovalProcessConcurrency(FrappeTestCase):
	workflow_name = "_Test Process Parallel Approval Workflow"
	approve_action = "_Test Process Approve"
	reopen_action = "_Test Process Reopen"
	users = (
		"process-approver-one@example.com",
		"process-approver-two@example.com",
		"process-approver-three@example.com",
	)

	def setUp(self):
		super().setUp()
		self.site = frappe.local.site
		self.sites_path = frappe.local.sites_path
		self.previous_flag = frappe.conf.get("enable_parallel_workflow_approval")
		self.previous_active_workflows = frappe.get_all(
			"Workflow",
			filters={"document_type": "Issue", "is_active": 1},
			pluck="name",
		)
		self.created_users = []
		self.reference_names = []
		frappe.conf.enable_parallel_workflow_approval = False
		self._delete_stale_test_workflow()
		self._ensure_master("Workflow State", "Open", {"workflow_state_name": "Open"})
		self._ensure_master("Workflow State", "Closed", {"workflow_state_name": "Closed"})
		self._ensure_master(
			"Workflow Action Master",
			self.approve_action,
			{"workflow_action_name": self.approve_action},
		)
		self._ensure_master(
			"Workflow Action Master",
			self.reopen_action,
			{"workflow_action_name": self.reopen_action},
		)
		for index, user_name in enumerate(self.users, start=1):
			if not frappe.db.exists("User", user_name):
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": user_name,
						"first_name": f"Process Approver {index}",
						"enabled": 1,
						"user_type": "System User",
						"send_welcome_email": 0,
					}
				)
				user.append("roles", {"role": "System Manager"})
				user.append("roles", {"role": "Support Team"})
				user.insert(ignore_permissions=True)
				self.created_users.append(user_name)
			else:
				user = frappe.get_doc("User", user_name)
				roles = {
					row.role
					for row in frappe.get_all(
						"Has Role",
						filters={"parent": user_name, "parenttype": "User"},
						fields=["role"],
					)
				}
				changed = False
				for role in ("System Manager", "Support Team"):
					if role not in roles:
						user.append("roles", {"role": role})
						changed = True
				if changed:
					user.save(ignore_permissions=True)
			frappe.clear_cache(user=user_name)

		frappe.get_doc(
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
						"action": self.approve_action,
						"next_state": "Closed",
						"allowed": "System Manager",
						"allow_self_approval": 1,
						"custom_transition_uuid": "_test-process-approve",
						"custom_parallel_approval_policy": "Minimum",
						"custom_minimum_approvals": 2,
					},
					{
						"state": "Closed",
						"action": self.reopen_action,
						"next_state": "Open",
						"allowed": "System Manager",
						"allow_self_approval": 1,
						"custom_transition_uuid": "_test-process-reopen",
						"custom_parallel_approval_policy": "Any",
					},
				],
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		frappe.conf.enable_parallel_workflow_approval = True
		frappe.db.commit()

	def tearDown(self):
		try:
			frappe.db.rollback()
			frappe.set_user("Administrator")
			frappe.conf.enable_parallel_workflow_approval = False
			for reference_name in self.reference_names:
				self._delete_source_records(reference_name)
			self._delete_stale_test_workflow()
			for workflow_name in self.previous_active_workflows:
				if frappe.db.exists("Workflow", workflow_name):
					frappe.db.set_value(
						"Workflow",
						workflow_name,
						"is_active",
						1,
						update_modified=False,
					)
			for user_name in self.created_users:
				if frappe.db.exists("User", user_name):
					frappe.delete_doc(
						"User",
						user_name,
						force=True,
						ignore_permissions=True,
					)
			frappe.db.commit()
		finally:
			frappe.conf.enable_parallel_workflow_approval = self.previous_flag
			frappe.clear_cache(doctype="Issue")
			super().tearDown()

	def _delete_stale_test_workflow(self):
		if frappe.db.exists("Workflow", self.workflow_name):
			frappe.delete_doc(
				"Workflow",
				self.workflow_name,
				force=True,
				ignore_permissions=True,
			)

	def _delete_source_records(self, reference_name):
		task_names = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": "Issue",
				"reference_name": reference_name,
			},
			pluck="name",
		)
		if task_names:
			frappe.db.delete(
				"Available Workflow Transitions",
				{"parent": ("in", task_names)},
			)
			frappe.db.delete("Workflow Task", {"name": ("in", task_names)})
		frappe.db.delete(
			"Workflow Action",
			{
				"reference_doctype": "Issue",
				"reference_name": reference_name,
			},
		)
		frappe.db.delete(
			"ToDo",
			{
				"reference_type": "Issue",
				"reference_name": reference_name,
			},
		)
		frappe.db.delete(
			"DocShare",
			{
				"share_doctype": "Issue",
				"share_name": reference_name,
			},
		)
		if frappe.db.exists("Issue", reference_name):
			frappe.delete_doc(
				"Issue",
				reference_name,
				force=True,
				ignore_permissions=True,
			)

	def _ensure_master(self, doctype, name, values):
		if not frappe.db.exists(doctype, name):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(
				ignore_permissions=True
			)

	def _make_source(self, subject):
		from frappe.share import add_docshare

		frappe.conf.enable_parallel_workflow_approval = False
		source = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": subject,
				"status": "Open",
			}
		).insert(ignore_permissions=True)
		for user_name in self.users:
			add_docshare(
				"Issue",
				source.name,
				user=user_name,
				read=1,
				write=1,
				flags={"ignore_share_permission": True},
			)
		frappe.conf.enable_parallel_workflow_approval = True
		from dinext_common.workflow_approval.engine import reconcile_source

		reconcile_source(source)
		self.reference_names.append(source.name)
		frappe.db.commit()
		return source

	def _task_for_user(self, reference_name, user):
		task_name = frappe.db.get_value(
			"Workflow Task",
			{
				"reference_doctype": "Issue",
				"reference_name": reference_name,
				"approver": user,
				"status": "Working",
				"round_status": "Open",
			},
		)
		self.assertTrue(
			task_name,
			(
				f"missing Workflow Task for {user}; "
				f"round approvers={frappe.get_all('Workflow Task', filters={'reference_doctype': 'Issue', 'reference_name': reference_name}, pluck='approver')}; "
				f"roles={frappe.get_roles(user)}; "
				f"can_read={frappe.has_permission('Issue', ptype='read', doc=reference_name, user=user)}"
			),
		)
		return frappe.get_doc("Workflow Task", task_name)

	def _run_processes(self, target, process_arguments, *, count_core_transitions=False):
		context = multiprocessing.get_context("spawn")
		barrier = context.Barrier(len(process_arguments))
		results = context.Queue()
		core_transition_count = context.Value("i", 0)
		processes = []
		for arguments in process_arguments:
			if count_core_transitions:
				arguments = (
					self.site,
					self.sites_path,
					barrier,
					results,
					core_transition_count,
					*arguments,
				)
			else:
				arguments = (
					self.site,
					self.sites_path,
					barrier,
					results,
					*arguments,
				)
			processes.append(context.Process(target=target, args=arguments))

		for process in processes:
			process.start()
		for process in processes:
			process.join(timeout=90)
			if process.is_alive():
				process.terminate()
				process.join(timeout=10)
				self.fail(f"concurrency worker {process.pid} did not finish")
			self.assertEqual(process.exitcode, 0)

		outcomes = []
		for _process in processes:
			try:
				outcomes.append(results.get(timeout=10))
			except queue.Empty:
				self.fail("concurrency worker returned no result")
		results.close()
		results.join_thread()
		self.assertEqual(len({outcome["pid"] for outcome in outcomes}), len(processes))
		return outcomes, core_transition_count.value

	def _assert_one_projection_and_notification_decision_per_task(
		self,
		reference_name,
		round_id,
	):
		tasks = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": "Issue",
				"reference_name": reference_name,
				"approval_round_id": round_id,
			},
			fields=["name", "approver", "round_manifest"],
		)
		self.assertTrue(tasks)
		self.assertEqual(len({task.round_manifest for task in tasks}), 1)
		for task in tasks:
			actions = frappe.get_all(
				"Workflow Action",
				filters={
					"custom_workflow_task": task.name,
					"status": "Open",
				},
				fields=["name", "custom_notification_status"],
			)
			self.assertEqual(len(actions), 1)
			self.assertEqual(actions[0].custom_notification_status, "Skipped")

	def test_simultaneous_last_single_and_typed_bulk_votes_finalize_once(self):
		from dinext_common.workflow_approval import api

		source = self._make_source("Process concurrency final vote")
		first_task = self._task_for_user(source.name, self.users[0])
		second_task = self._task_for_user(source.name, self.users[1])
		third_task = self._task_for_user(source.name, self.users[2])
		initial_round_id = first_task.approval_round_id

		frappe.set_user(first_task.approver)
		first_result = api.vote(
			first_task.name,
			transition_uuid=first_task.available_workflow_transitions[0].transition_uuid,
			request_id="process-initial-vote",
		)
		self.assertFalse(first_result["transitioned"])
		frappe.db.commit()

		outcomes, core_transition_count = self._run_processes(
			_process_vote,
			[
				(
					"single",
					second_task.name,
					second_task.available_workflow_transitions[0].transition_uuid,
					second_task.approver,
				),
				(
					"typed_bulk",
					third_task.name,
					third_task.available_workflow_transitions[0].transition_uuid,
					third_task.approver,
				),
			],
			count_core_transitions=True,
		)
		frappe.set_user("Administrator")
		frappe.db.rollback()

		self.assertEqual(core_transition_count, 1)
		self.assertEqual(sum(outcome["transitioned"] for outcome in outcomes), 1)
		self.assertEqual(
			frappe.db.get_value("Issue", source.name, "status"),
			"Closed",
		)
		initial_tasks = frappe.get_all(
			"Workflow Task",
			filters={"approval_round_id": initial_round_id},
			fields=["name", "status", "round_status"],
		)
		self.assertEqual(
			sum(task.status == "Completed" for task in initial_tasks),
			2,
		)
		self.assertEqual({task.round_status for task in initial_tasks}, {"Transitioned"})

		next_rounds = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": "Issue",
				"reference_name": source.name,
				"workflow_state": "Closed",
				"status": "Working",
				"round_status": "Open",
			},
			pluck="approval_round_id",
			distinct=True,
		)
		self.assertEqual(len(next_rounds), 1)
		self._assert_one_projection_and_notification_decision_per_task(
			source.name,
			next_rounds[0],
		)
		self.assertFalse(
			frappe.db.exists(
				"Workflow Action",
				{
					"reference_doctype": "Issue",
					"reference_name": source.name,
					"status": "Open",
					"custom_workflow_task": ("is", "not set"),
				},
			)
		)

	def test_concurrent_reconcile_repairs_partial_round_once_and_is_idempotent(self):
		from dinext_common.workflow_approval.policy import make_task_name

		source = self._make_source("Process concurrency partial repair")
		remaining_task = self._task_for_user(source.name, self.users[0])
		missing_task = self._task_for_user(source.name, self.users[1])
		round_id = remaining_task.approval_round_id
		manifest = remaining_task.round_manifest
		manifest_dict = frappe.parse_json(manifest)
		expected_approvers = sorted(
			{
				approver
				for transition in manifest_dict["transitions"]
				for approver in transition["eligible_approvers"]
			}
		)
		expected_task_names = {
			make_task_name(round_id, approver) for approver in expected_approvers
		}

		frappe.db.delete(
			"Available Workflow Transitions",
			{"parent": missing_task.name},
		)
		frappe.db.delete(
			"Workflow Action",
			{"custom_workflow_task": missing_task.name},
		)
		frappe.db.delete(
			"ToDo",
			{
				"reference_type": "Issue",
				"reference_name": source.name,
				"allocated_to": missing_task.approver,
			},
		)
		frappe.db.delete("Workflow Task", {"name": missing_task.name})
		frappe.db.commit()

		for _attempt in range(2):
			outcomes, _core_transition_count = self._run_processes(
				_process_reconcile,
				[(source.name,), (source.name,)],
			)
			self.assertFalse(any(outcome["failed"] for outcome in outcomes), outcomes)
			frappe.db.rollback()
			actual_task_names = set(
				frappe.get_all(
					"Workflow Task",
					filters={"approval_round_id": round_id},
					pluck="name",
				)
			)
			self.assertEqual(actual_task_names, expected_task_names)
			self.assertEqual(
				frappe.db.count(
					"Workflow Task",
					{"approval_round_id": round_id},
				),
				len(expected_task_names),
			)
			self._assert_one_projection_and_notification_decision_per_task(
				source.name,
				round_id,
			)
