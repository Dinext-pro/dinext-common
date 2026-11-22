"""Separate database connections must claim and queue a deadline only once."""

import os
from datetime import datetime, timedelta, timezone

import frappe

from dinext_common.tests.test_workflow_approval_concurrency import TestWorkflowApprovalProcessConcurrency


def _deliver(site, sites_path, barrier, results, workflow_name, task_name, recipient, slot_text):
	frappe.init(site=site, sites_path=sites_path, force=True)
	frappe.connect()
	frappe.flags.in_test = True
	frappe.flags.mute_emails = True
	try:
		from dinext_common.workflow_approval.deadlines.delivery import send_group

		workflow = frappe.get_doc("Workflow", workflow_name)
		slot = datetime.fromisoformat(slot_text)
		barrier.wait(timeout=60)
		send_group(workflow=workflow, recipient=recipient, task_names=[task_name], slot=slot,
			now=slot + timedelta(minutes=1))
		frappe.db.commit()
		results.put(dict(pid=os.getpid(), error=None))
	except Exception as exc:
		frappe.db.rollback()
		results.put(dict(pid=os.getpid(), error=repr(exc)))
	finally:
		frappe.destroy()


class TestDeadlineDeliveryProcess(TestWorkflowApprovalProcessConcurrency):
	workflow_name = "_Test Deadline Delivery Process Workflow"
	users = tuple(f"deadline-process-{number}@example.test" for number in (1, 2, 3))

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")
		for name in frappe.get_all("Email Queue", filters={"reference_doctype": "Workflow",
			"reference_name": self.workflow_name}, pluck="name"):
			frappe.delete_doc("Email Queue", name, ignore_permissions=True)
		frappe.db.delete("Workflow Deadline Delivery", {"workflow": self.workflow_name})
		frappe.db.commit()
		super().tearDown()

	def test_two_processes_form_one_native_queue_for_the_same_slot(self):
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.send_email_alert = 1
		workflow.transitions[0].update(dict(custom_deadline_enabled=1, custom_deadline_value=24,
			custom_deadline_unit="Hours", custom_deadline_recipient_type="User",
			custom_deadline_recipient_user=self.users[0], custom_deadline_email_mode="Digest",
			custom_deadline_interval_unit="Days", custom_deadline_interval_value=1,
			custom_deadline_send_times="08:00, 17:00"))
		workflow.save(ignore_permissions=True)
		source = self._make_source("Concurrent deadline delivery")
		task = self._task_for_user(source.name, self.users[0])
		self.assertTrue(task.deadline_assignment_id)
		frappe.db.set_value("Workflow Task", task.name, "deadline_due_at", "2026-01-01 00:00:00")
		frappe.db.commit()
		slot = datetime(2026, 11, 10, 5, tzinfo=timezone.utc)
		arguments = (workflow.name, task.name, self.users[0], slot.isoformat())
		outcomes, _count = self._run_processes(_deliver, [arguments, arguments])
		self.assertTrue(all(not row["error"] for row in outcomes), outcomes)
		frappe.db.rollback()
		self.assertEqual(frappe.db.count("Workflow Deadline Delivery", {"workflow": workflow.name}), 1)
		self.assertEqual(frappe.db.count("Email Queue", {"reference_doctype": "Workflow",
			"reference_name": workflow.name}), 1)
