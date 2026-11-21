"""Delegated Workflow decisions retain their author and effective approver."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.tests import test_workflow_approval_integration as fixtures
from dinext_common.workflow_approval import api, engine, request_receipts, signed_links


class TestWorkflowDelegationAudit(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.fixture = fixtures.TestWorkflowApprovalIntegration("runTest")
		self.fixture.workflow_name = "_Test Delegated Approval Audit"
		self.fixture.setUp()
		self.addCleanup(self.fixture.tearDown)

	def _task(self):
		source = frappe.get_doc({
			"doctype": "Issue", "subject": "Synthetic delegation audit", "status": "Open",
		}).insert(ignore_permissions=True)
		return frappe.get_doc("Workflow Task", {
			"reference_doctype": "Issue", "reference_name": source.name, "approver": self.fixture.user,
		})

	def test_deputy_is_recorded_but_assigned_approver_still_owns_vote(self):
		task = self._task()
		frappe.set_user(task.approver)
		request_id = frappe.generate_hash(length=24)
		direct_key = request_receipts.request_key("Vote", request_id)
		frappe.session.data = frappe._dict(impersonated_by="Administrator")
		delegated_key = request_receipts.request_key("Vote", request_id)
		kwargs = {"transition_uuid": "_test-transition", "request_id": request_id}
		result = api.vote(task.name, **kwargs)
		self.assertEqual(api.vote(task.name, **kwargs), result)
		task.reload()
		self.assertEqual((task.get("performed_by"), task.get("performed_as")), ("Administrator", task.approver))
		self.assertEqual(task.approver, self.fixture.user)
		self.assertNotEqual(delegated_key, direct_key)
		self.assertTrue(result["transitioned"])
		history = api.get_source_approval_history(task.reference_doctype, task.reference_name)
		accepted = next(row for row in history if row["name"] == task.name)
		self.assertEqual(accepted["performed_by"], "Administrator")
		self.assertEqual(accepted["performed_as"], task.approver)
		self.assertIn("on behalf of", frappe.db.get_value(
			"Comment", {"reference_doctype": task.reference_doctype, "reference_name": task.reference_name,
				"comment_type": "Workflow", "content": ("like", "%on behalf of%")}, "content",
		) or "")
		frappe.session.data = frappe._dict()
		with self.assertRaises(engine.WorkflowApprovalConflictError):
			api.vote(task.name, **kwargs)
		self.assertEqual(task.reload().performed_by, "Administrator")

	def test_direct_vote_records_the_authenticated_user(self):
		task = self._task()
		frappe.set_user(task.approver)
		api.vote(task.name, transition_uuid="_test-transition")
		task.reload()
		self.assertEqual((task.get("performed_by"), task.get("performed_as")), (task.approver, task.approver))

	def test_worker_uses_both_identities_without_a_browser_session(self):
		task = self._task()

		frappe.set_user(task.approver)
		frappe.session.data = frappe._dict(impersonated_by="Administrator")
		with patch.object(frappe, "enqueue") as enqueue:
			api.bulk_workflow_approval(
				[str(i) for i in range(20)], task.reference_doctype, self.fixture.action_name,
			)
		job = enqueue.call_args.kwargs
		self.assertEqual((job["initiator"], job["deputy"]), (task.approver, "Administrator"))
		frappe.set_user("Administrator")
		with patch.object(frappe.db, "commit"):
			result = api.run_background_bulk(
				initiator=task.approver, deputy="Administrator",
				doctype=task.reference_doctype, names=[task.reference_name], action=self.fixture.action_name,
				transition_uuid="_test-transition", request_id=frappe.generate_hash(length=24),
			)
		self.assertTrue(result["succeeded"], result)
		task.reload()
		self.assertEqual((task.performed_by, task.performed_as), ("Administrator", task.approver))

	def test_guest_email_confirmation_records_recipient_without_guessing_the_person(self):
		task = self._task()
		command = {
			"task_name": task.name, "transition_uuid": "_test-transition", "user": task.approver,
			"delivery_key": signed_links.ensure_delivery_key(task.name),
		}
		frappe.set_user("Guest")
		with (
			patch.object(signed_links, "_peek_command", return_value=command),
			patch.object(signed_links, "return_success_page") as success,
		):
			signed_links.confirm_action(frappe.generate_hash(length=32))
		success.assert_called_once()
		frappe.set_user("Administrator")
		task.reload()
		self.assertEqual(task.completion_source, "Signed Link")
		self.assertIsNone(task.performed_by)
		self.assertEqual(task.performed_as, task.approver)

	def test_old_receipt_marker_cannot_act_on_a_new_task_after_expiry(self):
		task = self._task()
		request_id = frappe.generate_hash(length=24)
		engine._set_task_values(task.name, {"correlation_id": request_id, "request_receipt_recorded": 1})
		frappe.set_user(task.approver)
		frappe.session.data = frappe._dict(impersonated_by="Administrator")
		with (
			patch.object(api, "_find_task_for_action") as find_new,
			self.assertRaises(engine.WorkflowApprovalConflictError),
		):
			api._vote_source_action(
				task.reference_doctype, task.reference_name, self.fixture.action_name,
				transition_uuid="_test-transition", request_id=request_id,
			)
		find_new.assert_not_called()
		self.assertEqual(task.reload().status, "Working")
