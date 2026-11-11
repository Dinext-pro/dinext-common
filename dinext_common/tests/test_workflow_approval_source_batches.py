import unittest
from datetime import datetime
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval import api, permissions


class TestApprovalSourceBatches(unittest.TestCase):
	def test_prepares_each_new_source_only_once_across_pages(self):
		rows = [
			frappe._dict(reference_doctype="Issue", reference_name=name, source_deleted_at=None)
			for name in ("visible", "hidden", "visible")
		]
		cache = {}
		with (
			patch.object(frappe, "session", frappe._dict(user="reader")),
			patch.object(
				permissions,
				"_batch_read_helper",
				return_value=lambda dt, names: {"visible"},
			),
		):
			permissions.prepare_source_permissions(rows, "reader", cache)
			self.assertEqual(cache, {("Issue", "visible"): True, ("Issue", "hidden"): False})
			with patch.object(
				permissions, "_batch_read_helper", side_effect=AssertionError("already checked")
			):
				permissions.prepare_source_permissions(rows, "reader", cache)

	def test_archived_and_other_user_checks_do_not_prefetch_sources(self):
		row = frappe._dict(
			reference_doctype="Issue", reference_name="archived", source_deleted_at="2026-01-01"
		)
		with (
			patch.object(frappe, "session", frappe._dict(user="reader")),
			patch.object(permissions, "_batch_read_helper", side_effect=AssertionError("must not load")),
		):
			permissions.prepare_source_permissions([row], "reader", {})
			row.source_deleted_at = None
			permissions.prepare_source_permissions([row], "different-user", {})

	def test_task_checker_uses_prepared_source_result(self):
		row = {"approver": "reader", "reference_doctype": "Issue", "reference_name": "source"}
		cache = {("Issue", "source"): False}
		with (
			patch.object(permissions, "_is_system_manager", return_value=False),
			patch.object(
				permissions, "_has_source_read_permission", side_effect=AssertionError("prefetched")
			),
		):
			self.assertFalse(permissions.get_task_read_checker("reader", source_permissions=cache)(row))
			cache[("Issue", "source")] = True
			self.assertTrue(permissions.get_task_read_checker("reader", source_permissions=cache)(row))

	def test_old_plugin_falls_back_to_existing_source_permission(self):
		row = frappe._dict(reference_doctype="Issue", reference_name="source")
		cache = {}
		with (
			patch.object(frappe, "session", frappe._dict(user="reader")),
			patch.object(permissions, "_batch_read_helper", return_value=None),
		):
			permissions.prepare_source_permissions([row], "reader", cache)
		self.assertEqual(cache, {})
		with (
			patch.object(permissions, "_is_system_manager", return_value=False),
			patch.object(permissions, "_has_source_read_permission", return_value=True) as read,
		):
			self.assertTrue(
				permissions.get_task_read_checker("reader", source_permissions=cache)(
					{**row, "approver": "reader"}
				)
			)
		read.assert_called_once()

	def test_issues_card_returns_zero_before_reading_open_sources(self):
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(api, "_control_rounds", side_effect=AssertionError("must not scan open sources")),
		):
			result = api.attention_control_round_count()
		self.assertEqual(result["value"], 0)
		self.assertEqual(result["route_options"], {"round_status": "Attention"})

	def test_batch_results_are_reused_across_task_pages(self):
		rows = [
			frappe._dict(
				name=f"TASK-{i}",
				workflow="W",
				reference_doctype="Issue",
				reference_name="SOURCE",
				approval_round_id="ROUND",
				round_status="Open",
				status="Working",
				approver="other",
				creation=datetime(2026, 1, 1),
				source_deleted_at=None,
			)
			for i in range(1001)
		]
		calls = []

		def read(doctype, names):
			calls.append((doctype, set(names)))
			return set(names)

		with (
			patch.object(frappe, "session", frappe._dict(user="monitor")),
			patch.object(frappe, "get_roles", return_value=["Monitor"]),
			patch.object(api, "get_monitorable_workflows", return_value=["W"]),
			patch("dinext_common.workflow_approval.scenarios.service.current_task_rows", side_effect=lambda rows: rows),
			patch.object(permissions, "_is_system_manager", return_value=False),
			patch.object(permissions, "_is_workflow_monitor", return_value=True),
			patch.object(permissions, "_batch_read_helper", return_value=read),
			patch.object(
				frappe,
				"get_all",
				side_effect=lambda dt, **kw: rows[
					kw["limit_start"] : kw["limit_start"] + kw["limit_page_length"]
				],
			),
		):
			self.assertEqual(api.open_control_round_count()["value"], 1)
		self.assertEqual(calls, [("Issue", {"SOURCE"})])
