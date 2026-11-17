import unittest
from datetime import datetime
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval import api, permissions
from dinext_common.workflow_approval.scenarios import service


class TestApprovalSourceBatches(unittest.TestCase):
	def test_narrow_reads_keep_each_tasks_context_and_permission(self):
		user = "reader"
		created = datetime(2026, 1, 1)
		tasks = [
			frappe._dict(
				name=f"task-{name}", workflow="W", workflow_process=f"process-{name}",
				reference_doctype="Note", reference_name=name, source_created_at=created,
				approver=user, round_status="Open",
			)
			for name in ("first", "hidden", "second", "stale")
		]
		contexts = [
			frappe._dict(
				name=service.source_key({"doctype": "Note", "name": row.reference_name, "creation": created}),
				active_process=row.workflow_process,
			)
			for row in tasks[:-1]
		]

		def get_all(doctype, *, fields, **kwargs):
			rows = contexts if doctype == service.CONTEXT else tasks
			return [frappe._dict({field: row.get(field) for field in fields}) for row in rows]

		with (
			patch.object(frappe, "session", frappe._dict(user=user)),
			patch.object(frappe, "get_roles", return_value=["System Manager"]),
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(service, "is_ready", return_value=True),
			patch.object(permissions, "_batch_read_helper", return_value=lambda dt, names: names - {"hidden"}),
		):
			self.assertEqual(api.open_approval_count()["value"], 2)
			self.assertEqual({row.reference_name for row in api.get_monitored_tasks()}, {"first", "second"})

	def test_list_hook_batches_task_source_permissions(self):
		user = "reader"
		rows = [
			frappe._dict(name=f"task-{name}", approver=user, reference_doctype="Note", reference_name=name)
			for name in ("visible", "hidden")
		]
		with (
			patch.object(frappe, "session", frappe._dict(user=user)),
			patch.object(permissions, "_is_system_manager", return_value=False),
			patch.object(permissions, "get_monitorable_workflows", return_value=["Monitored"]),
			patch.object(frappe, "get_all", return_value=rows) as candidates,
			patch.object(permissions, "_batch_read_helper") as helper,
			patch.object(permissions, "_has_source_read_permission", side_effect=AssertionError("one source per query")),
		):
			helper.return_value.return_value = {"visible"}
			condition = permissions.get_workflow_task_permission_query_conditions(user)

		helper.return_value.assert_called_once_with("Note", {"visible", "hidden"})
		self.assertIn("task-visible", condition)
		self.assertNotIn("task-hidden", condition)
		self.assertEqual(candidates.call_args.kwargs["or_filters"], [
			["approver", "=", user], ["user", "=", user], ["workflow", "in", ["Monitored"]],
		])

	def test_list_hook_pages_by_task_name_and_reuses_source_access(self):
		user = "reader"
		rows = [
			frappe._dict(name=f"task-{index:03}", approver=user, reference_doctype="Note", reference_name="source")
			for index in range(501)
		]
		with (
			patch.object(frappe, "session", frappe._dict(user=user)),
			patch.object(permissions, "_is_system_manager", return_value=False),
			patch.object(permissions, "get_monitorable_workflows", return_value=[]),
			patch.object(frappe, "get_all", side_effect=[rows[:500], rows[500:]]) as candidates,
			patch.object(permissions, "_batch_read_helper") as helper,
		):
			helper.return_value.return_value = {"source"}
			condition = permissions.get_workflow_task_permission_query_conditions(user)

		helper.return_value.assert_called_once_with("Note", {"source"})
		self.assertEqual(candidates.call_args.kwargs["filters"], {"name": (">", "task-499")})
		self.assertIn("task-000", condition)
		self.assertIn("task-500", condition)

	def test_limited_personal_queue_avoids_reading_unneeded_source_pages(self):
		user = "reader"
		rows = [
			frappe._dict(name=f"task-{index}", approver=user, reference_doctype="Note", reference_name=f"source-{index}")
			for index in range(3)
		]
		with (
			patch.object(frappe, "session", frappe._dict(user=user)),
			patch.object(permissions, "_is_system_manager", return_value=False),
			patch.object(service, "current_task_rows", side_effect=lambda rows: rows),
			patch.object(frappe, "get_all", side_effect=lambda dt, **kw: rows[:kw["limit_page_length"]]),
			patch.object(permissions, "_batch_read_helper") as helper,
		):
			helper.return_value.return_value = {"source-0", "source-1"}
			result = api.get_personal_queue(limit=2, fields=("name",))

		self.assertEqual([row.name for row in result], ["task-0", "task-1"])
		helper.return_value.assert_called_once_with("Note", {"source-0", "source-1"})

	def test_skipping_unreadable_sources_preserves_other_request_messages(self):
		row = frappe._dict(reference_doctype="Issue", reference_name="hidden")
		message = {"message": "Existing message"}
		flags = frappe._dict(mute_messages=False, error_message="Existing error")

		def batch_read(doctype, names):
			try:
				frappe.flags.error_message = "No source permission"
				frappe.msgprint("No source permission", title="Permission", raise_exception=frappe.PermissionError)
			except frappe.PermissionError:
				return set()

		with (
			patch.object(frappe, "session", frappe._dict(user="reader")),
			patch.object(frappe.local, "flags", flags),
			patch.object(frappe.local, "message_log", [message]),
			patch.object(permissions, "_batch_read_helper", return_value=batch_read),
		):
			cache = {}
			permissions.prepare_source_permissions([row], "reader", cache)
			self.assertEqual(cache, {("Issue", "hidden"): False})
			self.assertEqual(frappe.get_message_log(), [message])
			self.assertFalse(frappe.flags.mute_messages)
			self.assertEqual(frappe.flags.error_message, "Existing error")

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
