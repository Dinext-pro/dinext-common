"""Regressions for personal actions, competing thresholds and card boundaries."""
import json
import unittest
from collections import Counter
from datetime import datetime
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval import api, permissions
from dinext_common.dinext_common.report.my_approvals import my_approvals as queue
from dinext_common.dinext_common.report.approval_duration import approval_duration as duration


class TestMyApprovalsAudit(unittest.TestCase):
	def setUp(self):
		previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict(in_test=False)
		self.addCleanup(setattr, frappe.local, "flags", previous_flags)
		clock = patch.object(duration, "now_datetime", return_value=datetime(2026, 11, 7))
		clock.start()
		self.addCleanup(clock.stop)

	def test_personal_actions_and_uuid_progress(self):
		row = frappe._dict(name="A", approval_round_id="R", creation=datetime(2026, 11, 6),
			reference_doctype="Issue", available_transitions=[{"action": "Approve", "transition_uuid": "a"}],
			round_manifest=json.dumps({"transitions": [
				{"action": "Approve", "transition_uuid": "a", "threshold": 2},
				{"action": "Reject", "transition_uuid": "r", "threshold": 1}]}))
		with patch.object(queue, "now_datetime", return_value=datetime(2026, 11, 7)), patch.object(queue, "get_personal_queue", return_value=[row]), patch.object(
			queue, "_completed_votes", return_value=Counter({("R", "a"): 1})), patch.object(queue, "_", side_effect=lambda x: x):
			self.assertEqual(queue.execute({"action": "Reject"})[1], [])
			self.assertEqual(row.available_actions, "Approve")
			self.assertEqual(row.progress, "Approve 1/2; Reject 0/1")
			self.assertEqual(row.progress_transitions[0]["votes"], 1)

	def test_completed_votes_are_grouped_by_uuid(self):
		with patch.object(frappe, "get_all", return_value=[
			frappe._dict(approval_round_id="R", transition_uuid="a"),
			frappe._dict(approval_round_id="R", transition_uuid="r")]):
			try:
				counts = queue._completed_votes({"R"})
			except TypeError:
				self.fail("completed votes must group records by round and transition UUID")
			self.assertEqual(counts, Counter({("R", "a"): 1, ("R", "r"): 1}))

	def test_manager_live_source_access_is_required(self):
		with patch.object(permissions, "_has_source_read_permission", return_value=False):
			self.assertFalse(permissions.has_workflow_task_permission({"reference_doctype": "Issue", "reference_name": "X"}, user="Administrator"))
			self.assertTrue(permissions.has_workflow_task_permission({"source_deleted_at": "2026-01-01"}, user="Administrator"))

	def test_control_card_routes_exact_cutoff_and_resets_scope(self):
		with patch.object(duration, "now_datetime", return_value=datetime(2026, 11, 7, 13, 15, 42)), patch.object(api, "now_datetime", return_value=datetime(2026, 11, 7, 13, 15, 42)), patch.object(api, "get_monitored_tasks", return_value=[]):
			card = api.control_decision_count()
		options = card["route_options"]
		self.assertEqual(options.get("completed_since"), "2026-10-08 13:15:42")
		self.assertEqual(options["workflow"], "")
		self.assertEqual(options["reference_doctype"], "")
		self.assertEqual(duration._period(options)[0], datetime(2026, 10, 8, 13, 15, 42))
		self.assertEqual(str(duration._period({"from_date": "2026-10-08", "to_date": "2026-11-07"})[0]), "2026-10-08")

	def test_old_platform_task_lists_fail_closed(self):
		from frappe.model.db_query import DatabaseQuery

		self.assertTrue(hasattr(permissions, "require_final_task_permission_queries"))
		for version, method in [(0, lambda *args: ""), (1, None)]:
			with self.subTest(version=version, method=method), patch.object(
				DatabaseQuery, "final_permission_query_conditions_version", version, create=True
			), patch.object(DatabaseQuery, "get_final_permission_query_conditions", method, create=True), patch.object(
				frappe, "throw", side_effect=frappe.PermissionError
			), patch.object(frappe, "_", side_effect=lambda text: text):
				with self.assertRaises(frappe.PermissionError):
					permissions.require_final_task_permission_queries("Administrator")
