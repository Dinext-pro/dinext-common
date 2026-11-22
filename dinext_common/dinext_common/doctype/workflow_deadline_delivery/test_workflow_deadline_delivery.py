"""Retention of deadline deliveries through standard Frappe Log Settings."""

import json
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.core.doctype.log_settings.log_settings import _supports_log_clearing
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from dinext_common.workflow_approval import notifications

DOCTYPE = "Workflow Deadline Delivery"
STATE = "Pending Approval"
RECIPIENT = "Administrator"
POLICY = "retention-test-deadline"


class TestWorkflowDeadlineDelivery(FrappeTestCase):
	def setUp(self):
		self.now = now_datetime()
		self.workflow = "Deadline Retention " + frappe.generate_hash(length=12)

	def _log_settings(self):
		settings = frappe.get_single("Log Settings")
		settings.set("logs_to_clear", [row for row in settings.logs_to_clear if row.ref_doctype != DOCTYPE])
		settings.add_default_logtypes()
		entries = [row for row in settings.logs_to_clear if row.ref_doctype == DOCTYPE]
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].days, 7)
		settings.set("logs_to_clear", entries)
		return settings, entries[0]

	def _elapsed_days_ago(self, days):
		# Hourly schedules count elapsed UTC hours across a site clock change.
		return notifications._database_datetime(notifications._aware_utc(self.now) - timedelta(days=days))

	def _task(self, name, assignment, *, active=True):
		frappe.get_doc({
			"doctype": "Workflow Task",
			"name": name,
			"workflow": self.workflow,
			"workflow_state": STATE,
			"status": "Working" if active else "Completed",
			"round_status": "Open" if active else "Transitioned",
			"deadline_assignment_id": assignment,
			"deadline_transition_uuid": POLICY,
			"deadline_due_at": add_days(self.now, -30),
		}).db_insert()

	def _delivery(self, assignment, age, *, slot=None, policy=POLICY):
		mode = "Deadline Digest" if slot else "Deadline Immediate"
		identity = f"{notifications._aware_utc(slot).isoformat()}:{policy}" if slot else assignment
		key = notifications.make_delivery_key(mode, self.workflow, RECIPIENT, identity, state=STATE)
		frappe.get_doc({
			"doctype": DOCTYPE,
			"name": key,
			"delivery_key": key,
			"recipient": RECIPIENT,
			"workflow": self.workflow,
			"workflow_state": STATE,
			"slot": slot,
			"task_names": json.dumps([assignment]),
			"status": "Enqueued",
			"creation": add_days(self.now, -age),
			"modified": self.now,
		}).db_insert()
		return key

	def test_log_settings_register_seven_days_and_keep_custom_period(self):
		self.assertTrue(_supports_log_clearing(DOCTYPE))
		settings, entry = self._log_settings()
		entry.days = 0
		settings.add_default_logtypes()
		self.assertEqual([row.days for row in settings.logs_to_clear if row.ref_doctype == DOCTYPE], [0])

	def test_cleanup_preserves_recent_and_active_logical_assignments(self):
		settings, entry = self._log_settings()
		tag = frappe.generate_hash(length=12)
		replaced, recent, closed = [f"{tag}-{suffix}" for suffix in ("original", "recent", "closed")]
		self._task(replaced, replaced, active=False)
		self._task(f"{tag}-rebuilt", replaced)
		self._task(closed, closed, active=False)
		protected = self._delivery(replaced, age=8)
		fresh = self._delivery(recent, age=6)
		expired = self._delivery(closed, age=8)
		with patch.object(frappe.db, "commit"):
			settings.clear_logs()
			settings.clear_logs()
			self.assertTrue(frappe.db.exists(DOCTYPE, protected))
			self.assertTrue(frappe.db.exists(DOCTYPE, fresh))
			self.assertFalse(frappe.db.exists(DOCTYPE, expired))
			entry.days = 5
			settings.clear_logs()
			self.assertFalse(frappe.db.exists(DOCTYPE, fresh))
			self.assertTrue(frappe.db.exists(DOCTYPE, protected))

	def _digest_workflow(self, interval_unit):
		order = frappe.db.get_value(
			"Workflow", {"document_type": "ToDo"}, "custom_selection_order", order_by="custom_selection_order desc"
		)
		workflow = frappe.get_doc({
			"doctype": "Workflow",
			"name": self.workflow,
			"workflow_name": self.workflow,
			"document_type": "ToDo",
			"custom_selection_order": (order or 0) + 1,
			"transitions": [{
				"custom_transition_uuid": POLICY,
				"custom_deadline_enabled": 1,
				"custom_deadline_email_mode": "Digest",
				"custom_deadline_interval_unit": interval_unit,
				"custom_deadline_interval_value": 240,
				"custom_deadline_schedule_anchor": self._elapsed_days_ago(28),
			}],
		})
		workflow.db_insert()
		for transition in workflow.transitions:
			transition.db_insert()
		return workflow

	def test_withdrawn_assignment_keeps_its_delivery_when_restored(self):
		from dinext_common.workflow_approval import engine

		settings, _entry = self._log_settings()
		name = frappe.generate_hash(length=24)
		self._task(name, name)
		key = self._delivery(name, age=8)
		engine._retire_working_task(name)
		with patch.object(frappe.db, "commit"):
			settings.clear_logs()
			withdrawn = frappe.get_doc("Workflow Task", name)
			self.assertEqual(withdrawn.status, "Cancelled")
			engine._restore_withdrawn_task(withdrawn, [])
			self.assertEqual(frappe.db.get_value("Workflow Task", name, "status"), "Working")
			settings.clear_logs()
			self.assertTrue(frappe.db.exists(DOCTYPE, key))

	def test_active_round_manifest_keeps_absent_approver_immediate_and_digest_keys(self):
		settings, _entry = self._log_settings()
		workflow = self._digest_workflow("Hours")
		name, missing, round_id = [frappe.generate_hash(length=24) for _ in range(3)]
		self._task(name, name)
		frappe.db.set_value("Workflow Task", name, {
			"approval_round_id": round_id,
			"deadline_assignment_id": None,
			"round_manifest": json.dumps({"deadline_assignments": {"absent-approver": {
				"deadline_assignment_id": missing,
				"deadline_due_at": str(add_days(self.now, -30)),
				"deadline_transition_uuid": POLICY,
			}}}),
		})
		immediate = self._delivery(missing, age=8)
		current = self._delivery(missing, age=8, slot=self._elapsed_days_ago(8))
		older = self._delivery(missing, age=18, slot=self._elapsed_days_ago(18))
		with patch.object(frappe.db, "commit"):
			settings.clear_logs()
			self.assertTrue(frappe.db.exists(DOCTYPE, immediate))
			self.assertTrue(frappe.db.exists(DOCTYPE, current))
			self.assertFalse(frappe.db.exists(DOCTYPE, older))
			# The transition itself can disappear and return with the same UUID.
			frappe.db.set_value("Workflow Transition", workflow.transitions[0].name,
				"custom_transition_uuid", "replacement-policy")
			frappe.clear_document_cache("Workflow", self.workflow)
			unrelated = self._delivery(missing, age=8, slot=self._elapsed_days_ago(8), policy="unrelated")
			settings.clear_logs()
			self.assertTrue(frappe.db.exists(DOCTYPE, current))
			self.assertFalse(frappe.db.exists(DOCTYPE, unrelated))
			frappe.db.set_value("Workflow Task", name, "round_status", "Transitioned")
			settings.clear_logs()
			self.assertFalse(frappe.db.exists(DOCTYPE, immediate))
			self.assertFalse(frappe.db.exists(DOCTYPE, current))

	def test_cleanup_keeps_the_current_slot_for_a_digest_with_a_long_interval(self):
		settings, _entry = self._log_settings()
		workflow = self._digest_workflow("Hours")
		active = frappe.generate_hash(length=24)
		self._task(active, active)
		# A previously included task has disappeared. Another active task can still use the slot.
		old_task = frappe.generate_hash(length=24)
		current = self._delivery(old_task, age=8, slot=self._elapsed_days_ago(8))
		superseded = self._delivery(old_task, age=18, slot=self._elapsed_days_ago(18))
		with patch.object(frappe.db, "commit"):
			settings.clear_logs()
			self.assertTrue(frappe.db.exists(DOCTYPE, current))
			self.assertFalse(frappe.db.exists(DOCTYPE, superseded))
			frappe.db.set_value("Workflow Transition", workflow.transitions[0].name, "custom_deadline_enabled", 0)
			frappe.clear_document_cache("Workflow", self.workflow)
			settings.clear_logs()
			self.assertTrue(frappe.db.exists(DOCTYPE, current))
			frappe.db.set_value("Workflow Transition", workflow.transitions[0].name, "custom_deadline_enabled", 1)
			frappe.clear_document_cache("Workflow", self.workflow)
			frappe.db.set_value("Workflow Task", active, {
				"deadline_due_at": None,
				"deadline_transition_uuid": None,
				"deadline_error": "Calendar lookup failed",
			})
			settings.clear_logs()
			self.assertTrue(frappe.db.exists(DOCTYPE, current))
			frappe.db.set_value("Workflow Task", active, "status", "Completed")
			settings.clear_logs()
			self.assertFalse(frappe.db.exists(DOCTYPE, current))

	def test_cleanup_distinguishes_an_unavailable_schedule_from_no_due_slot(self):
		from dinext_common.workflow_approval.deadlines import delivery

		settings, _entry = self._log_settings()
		self._digest_workflow("Working Days")
		active = frappe.generate_hash(length=24)
		self._task(active, active)
		old = self._delivery(active, age=8, slot=self._elapsed_days_ago(8))
		extensions = {"sending_intervals": {"Working Days": {"latest_slot": lambda context: None}}}
		with patch.object(frappe.db, "commit"):
			with patch.object(delivery, "get_extensions", return_value={}):
				settings.clear_logs()
				self.assertTrue(frappe.db.exists(DOCTYPE, old))
			with patch.object(delivery, "get_extensions", return_value=extensions):
				settings.clear_logs()
				self.assertFalse(frappe.db.exists(DOCTYPE, old))
