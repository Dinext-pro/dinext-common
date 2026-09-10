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
					"first_name": "Administrator",
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
					}
				],
			}
		)
		workflow.insert(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		frappe.conf.enable_parallel_workflow_approval = True

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.conf.enable_parallel_workflow_approval = self.previous_flag
		frappe.clear_cache(doctype="Issue")
		super().tearDown()

	def _ensure_master(self, doctype, name, values):
		if not frappe.db.exists(doctype, name):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(
				ignore_permissions=True
			)

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
