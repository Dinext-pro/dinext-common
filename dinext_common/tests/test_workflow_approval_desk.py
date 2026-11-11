import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.workflow_approval import api, engine


class TestWorkflowApprovalReportRows(unittest.TestCase):
	def setUp(self):
		# These tests exercise the legacy permission seam; batching has its own suite.
		helper = patch("dinext_common.workflow_approval.permissions._batch_read_helper", return_value=None)
		helper.start()
		self.addCleanup(helper.stop)

	def test_open_card_reads_task_rows_without_loading_transitions(self):
		row = frappe._dict(name="TASK-1", approver="Administrator", reference_doctype="Issue", reference_name="ISS-1")
		with (
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
			patch.object(frappe, "get_all", return_value=[row]) as get_all,
			patch.object(frappe, "get_doc", return_value=row) as get_doc,
			patch("dinext_common.workflow_approval.permissions._has_source_read_permission", return_value=True),
		):
			result = api.open_approval_count()

		self.assertEqual(result["value"], 1)
		self.assertEqual(result["route"], ["query-report", "My Approvals"])
		get_doc.assert_not_called()
		self.assertEqual(get_all.call_count, 1)
		self.assertNotIn("round_manifest", get_all.call_args.kwargs["fields"])

	def test_new_card_checks_access_only_for_tasks_created_today(self):
		from dinext_common.workflow_approval import notifications, permissions

		now = datetime(2026, 1, 2, 0, 30, tzinfo=timezone.utc)
		user = "approver@example.com"
		rows = {
			name: frappe._dict(
				name=name,
				creation=created,
				approver=user,
				available_workflow_transitions=[],
				reference_doctype="Issue",
				reference_name=name,
			)
			for name, created in (
				("TODAY", datetime(2026, 1, 1, 22, tzinfo=timezone.utc)),
				("YESTERDAY", datetime(2026, 1, 1, 10, tzinfo=timezone.utc)),
			)
		}
		with (
			patch.object(frappe, "session", frappe._dict(user=user)),
			patch.object(frappe, "get_roles", return_value=[]),
			patch.object(api, "now_datetime", return_value=now),
			patch.object(notifications, "_recipient_timezone", return_value="Europe/Moscow"),
			patch.object(frappe, "get_all", return_value=list(rows.values())) as get_all,
			patch.object(frappe, "get_doc", side_effect=lambda _doctype, name: rows[name]),
			patch.object(permissions, "_has_source_read_permission", return_value=True) as can_read,
		):
			result = api.new_approval_count()

		self.assertEqual(result["value"], 1)
		self.assertEqual(result["route_options"]["created_on"], "2026-01-02")
		self.assertEqual(get_all.call_args.kwargs["limit_page_length"], 500)
		can_read.assert_called_once()

	def test_decision_card_passes_exact_cutoff_and_completion_filter_to_report(self):
		from dinext_common.dinext_common.report.my_approval_history import my_approval_history

		now = datetime(2026, 1, 31, 13, 15, 42, 123456)
		cutoff = datetime(2026, 1, 1, 13, 15, 42, 123456)
		query_filters = []

		def candidates(doctype, *, filters, **options):
			self.assertEqual(doctype, "Workflow Task")
			query_filters.append(filters)
			return []

		with (
			patch.object(api, "now_datetime", return_value=now),
			patch.object(frappe, "get_all", side_effect=candidates),
		):
			card = api.automatic_approval_count()
			my_approval_history.execute(card["route_options"])

		self.assertEqual(card["route_options"]["completed_since"], "2026-01-01 13:15:42.123456")
		self.assertTrue(card["route_options"]["ignore_prepared_report"])
		self.assertEqual(query_filters[0], query_filters[1])
		self.assertEqual(query_filters[1]["completed_at"], (">=", cutoff))
		self.assertEqual(query_filters[1]["status"], "Completed")
		self.assertEqual(query_filters[1]["completion_source"], "Automatic Unchanged")

	def test_monitoring_checks_each_workflow_and_source_once_per_call(self):
		from dinext_common.workflow_approval import permissions

		rows = {
			name: frappe._dict(
				name=name,
				workflow="W",
				reference_doctype="Issue",
				reference_name=source,
				approval_round_id=source,
				status="Working",
				round_status="Open",
				approver="approver@example.com",
				creation=datetime(2026, 1, 1),
				round_manifest="{}",
				source_deleted_at=None,
			)
			for name, source in (("A", "VISIBLE"), ("B", "VISIBLE"), ("C", "HIDDEN"))
		}
		tasks = [rows["A"]] * 500 + [rows["B"], rows["C"]]

		def candidates(doctype, *, limit_start=0, limit_page_length=500, **kwargs):
			if doctype == "Workflow Task":
				return tasks[limit_start : limit_start + limit_page_length]
			return ["Monitor"]

		with (
			patch.object(frappe, "session", frappe._dict(user="monitor@example.com")),
			patch.object(frappe, "get_roles", return_value=["Monitor"]),
			patch.object(api, "get_monitorable_workflows", return_value=["W"]),
			patch("dinext_common.workflow_approval.scenarios.service.current_task_rows", side_effect=lambda rows: rows),
			patch.object(
				frappe,
				"get_all",
				side_effect=candidates,
			) as get_all,
			patch.object(frappe, "get_doc", side_effect=lambda _doctype, name: rows[name]) as get_doc,
			patch.object(
				permissions,
				"_has_source_read_permission",
				side_effect=lambda row, _user: row.get("reference_name") == "VISIBLE",
			) as can_read,
		):
			result = api.get_monitoring_rows()
			self.assertEqual(len(result), 1)
			self.assertEqual(result[0].active_task_count, 501)
			get_doc.assert_not_called()
			self.assertNotIn("source_deleted_at", result[0])
			self.assertEqual(get_all.call_count, 3)
			self.assertEqual(can_read.call_count, 2)
			can_read.side_effect = None
			can_read.return_value = False
			self.assertEqual(api.get_monitoring_rows(), [])

	def test_queue_rows_keep_attribute_access(self):
		row = {"name": "TASK-1", "completed_at": "2026-01-02 00:00:00"}
		with (
			patch.object(frappe, "get_all", side_effect=[[row], []]),
			patch.object(api, "get_task_read_checker", return_value=lambda _: True),
		):
			result = api._filtered_tasks({"name": "TASK-1"})
		self.assertEqual(result[0].completed_at, "2026-01-02 00:00:00")

	def test_monitoring_attention_filter_keeps_stalled_and_conflicted(self):
		def row(name, status):
			return frappe._dict(
				name=name,
				approval_round_id=name,
				status="Working",
				approver="a@x",
				creation=frappe.utils.now_datetime(),
				round_manifest="{}",
				round_status=status,
				workflow="W",
				reference_doctype="Issue",
				reference_name=name,
				workflow_state="Open",
			)

		with patch.object(
			api,
			"_monitoring_candidates",
			return_value=[row("OPEN", "Open"), row("STALL", "Stalled"), row("CONF", "Conflicted")],
		):
			rows = api.get_monitoring_rows({"round_status": "Attention"})
		self.assertEqual({row.approval_round_id for row in rows}, {"STALL", "CONF"})

	def test_load_report_counts_tasks_per_person(self):
		from dinext_common.dinext_common.report.approval_load import approval_load

		created = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-5)
		tasks = [
			frappe._dict(
				approver="a@x",
				approval_round_id="R1",
				creation=created,
				source_title="Doc",
				reference_name="D1",
			),
			frappe._dict(
				approver="b@x",
				approval_round_id="R1",
				creation=created,
				source_title="Doc",
				reference_name="D1",
			),
		]
		with (
			patch.object(approval_load, "get_monitored_tasks", return_value=tasks),
			patch.object(
				approval_load,
				"approver_display_names",
				return_value={"a@x": "Анна", "b@x": "Борис"},
			),
		):
			columns, rows, _message, chart = approval_load.execute({"chart": "Open age"})
		self.assertIn("approver_name", {column["fieldname"] for column in columns})
		self.assertEqual(sum(row["open_tasks"] for row in rows), 2)
		self.assertEqual({row["open_rounds"] for row in rows}, {1})
		self.assertEqual(len(chart["data"]["datasets"]), 2)

	def test_duration_report_splits_manual_average_and_open_rounds(self):
		from dinext_common.dinext_common.report.approval_duration import approval_duration

		now = frappe.utils.now_datetime()
		tasks = [
			frappe._dict(
				approver="a@x",
				reference_doctype="Issue",
				workflow="W",
				status="Completed",
				completion_source="Manual",
				creation=frappe.utils.add_to_date(now, hours=-10),
				completed_at=now,
			),
			frappe._dict(
				approver="a@x",
				reference_doctype="Issue",
				workflow="W",
				status="Completed",
				completion_source="Automatic Unchanged",
				creation=frappe.utils.add_to_date(now, hours=-1),
				completed_at=now,
			),
		]
		open_round = frappe._dict(
			reference_doctype="Issue",
			workflow="W",
			pending_approvers="a@x",
			round_status="Open",
		)
		with (
			patch.object(approval_duration, "get_monitored_tasks", return_value=tasks),
			patch.object(approval_duration, "get_monitoring_rows", return_value=[open_round]),
			patch.object(approval_duration, "approver_display_names", return_value={}),
		):
			_columns, rows, _message, chart = approval_duration.execute(
				{"chart": "Open rounds", "group_by": "Document Type"}
			)
		self.assertEqual(rows[0]["manual_count"], 1)
		self.assertEqual(rows[0]["automatic_count"], 1)
		self.assertEqual(rows[0]["avg_hours"], 10.0)
		self.assertEqual(chart["data"]["labels"], ["Issue"])
		self.assertEqual(chart["data"]["datasets"][0]["values"], [1])

	def test_monitoring_join_skips_empty_approver(self):
		row = frappe._dict(
			name="TASK-1",
			approval_round_id="ROUND-1",
			status="Working",
			approver=None,
			creation=frappe.utils.now_datetime(),
			round_manifest=json.dumps(
				{"transitions": [{"action": "Reject", "transition_uuid": "uuid-1"}]}
			),
			workflow="W",
			reference_doctype="Issue",
			reference_name="ISS-1",
			workflow_state="Open",
		)
		with patch.object(api, "_monitoring_candidates", return_value=[row]):
			rows = api.get_monitoring_rows()
		self.assertEqual(rows[0].pending_approvers, "")
		self.assertIn("Reject", rows[0].available_actions)

	def test_history_report_reads_completed_row(self):
		from dinext_common.dinext_common.report.my_approval_history.my_approval_history import (
			execute,
		)

		row = frappe._dict(
			name="TASK-1",
			reference_doctype="Issue",
			reference_name="ISS-1",
			source_title="Issue",
			workflow="W",
			action="Reject",
			status="Completed",
			completion_source="Manual",
			completed_at=frappe.utils.now_datetime(),
			cancelled_at=None,
			vote_comment="because",
			reused_from_workflow_task=None,
		)
		with patch(
			"dinext_common.dinext_common.report.my_approval_history.my_approval_history.get_personal_history",
			return_value=[row],
		):
			_columns, rows, _message, _chart = execute({})
		self.assertEqual(rows[0].vote_comment, "because")
		self.assertEqual(rows[0].event_at, row.completed_at)

	def test_queue_report_reads_working_row(self):
		from dinext_common.dinext_common.report.my_approvals.my_approvals import execute

		created = frappe.utils.now_datetime()
		row = frappe._dict(
			name="TASK-1",
			approval_round_id="ROUND-1",
			reference_doctype="Issue",
			reference_name="ISS-1",
			source_title="Issue",
			workflow="W",
			workflow_state="Open",
			creation=created,
			available_transitions=[{"action": "Approve", "transition_uuid": "approve"}],
			round_manifest=json.dumps(
				{"transitions": [{"action": "Approve", "transition_uuid": "approve", "threshold": 2}]}
			),
		)
		with (
			patch(
				"dinext_common.dinext_common.report.my_approvals.my_approvals.get_personal_queue",
				return_value=[row],
			),
			patch(
				"dinext_common.dinext_common.report.my_approvals.my_approvals._completed_votes",
				return_value={("ROUND-1", "approve"): 0},
			),
		):
			_columns, rows, _message, _chart = execute({})
		self.assertEqual(rows[0].available_actions, "Approve")
		self.assertEqual(rows[0].progress, "Approve 0/2")


class TestWorkflowApprovalDesk(FrappeTestCase):
	role = "_Test WF Desk Approver"

	def setUp(self):
		super().setUp()
		self.previous_flag = frappe.conf.get("enable_parallel_workflow_approval")
		frappe.conf.enable_parallel_workflow_approval = True
		self.previous_active = frappe.get_all(
			"Workflow",
			filters={"document_type": "Issue", "is_active": 1},
			pluck="name",
		)
		for name in self.previous_active:
			frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
		self._ensure_master("Workflow State", "Open", {"workflow_state_name": "Open"})
		self._ensure_master("Workflow State", "Closed", {"workflow_state_name": "Closed"})
		if not frappe.db.exists("Role", self.role):
			frappe.get_doc({"doctype": "Role", "role_name": self.role}).insert(
				ignore_permissions=True
			)
		frappe.db.delete("Has Role", {"role": self.role, "parenttype": "User"})
		if not frappe.db.exists(
			"Custom DocPerm",
			{"parent": "Issue", "role": self.role, "permlevel": 0},
		):
			frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": "Issue",
					"role": self.role,
					"permlevel": 0,
					"read": 1,
					"write": 0,
					"create": 0,
					"delete": 0,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.conf.enable_parallel_workflow_approval = self.previous_flag
		for name in self.previous_active:
			if frappe.db.exists("Workflow", name):
				frappe.db.set_value("Workflow", name, "is_active", 1, update_modified=False)
		frappe.clear_cache(doctype="Issue")
		super().tearDown()

	def test_required_comment_nested_entities_are_normalized_once(self):
		user = self._user("desk-nested-entities@example.com")
		self._workflow("_Test Desk Nested Entities", [self._transition(
			"_Test Desk Approve Nested", "Closed", policy="Any",
			uuid="_test-desk-nested", comment_required=1,
		)])
		source = self._issue("Nested entities comment")
		task = self._tasks(source.name)[0]
		frappe.set_user(user)
		engine.cast_vote(task.name, transition_uuid="_test-desk-nested",
			comment="&amp;lt;b&amp;gt;&amp;lt;/b&amp;gt;", request_id="desk-nested-comment")
		self.assertEqual(frappe.db.get_value("Workflow Task", task.name, "vote_comment"), "&lt;b&gt;&lt;/b&gt;")
		self.assertEqual(frappe.db.get_value("Workflow Task", task.name, "status"), "Completed")

	def test_all_policy_threshold_counts_both_eligible_approvers(self):
		users = [self._user(f"desk-all-{index}@example.com") for index in (1, 2)]
		self._workflow(
			"_Test Desk All",
			[
				self._transition(
					"_Test Desk Approve",
					"Closed",
					policy="All",
					uuid="_test-desk-all",
				)
			],
		)
		source = self._issue("All cohort")
		tasks = self._tasks(source.name)
		self.assertEqual(sorted(task.approver for task in tasks), sorted(users))
		manifest = json.loads(tasks[0].round_manifest)
		self.assertEqual(manifest["transitions"][0]["threshold"], 2)
		frappe.set_user(tasks[0].approver)
		result = engine.cast_vote(
			tasks[0].name,
			transition_uuid="_test-desk-all",
			request_id="desk-all-1",
		)
		self.assertFalse(result["transitioned"])
		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Open")
		self.assertEqual(
			frappe.db.get_value("Workflow Task", tasks[0].name, "round_status"),
			"Open",
		)

	def test_read_only_reject_finalizes_without_write(self):
		user = self._user("desk-readonly@example.com")
		self._workflow(
			"_Test Desk Reject",
			[
				self._transition(
					"_Test Desk Reject",
					"Closed",
					policy="Any",
					uuid="_test-desk-reject",
					comment_required=1,
					condition="doc.owner != frappe.session.user",
					allow_self_approval=0,
				)
			],
		)
		source = self._issue("Read only reject")
		task = self._tasks(source.name)[0]
		self.assertEqual(task.approver, user)
		self.assertFalse(
			frappe.has_permission("Issue", ptype="write", doc=source.name, user=user)
		)
		frappe.set_user(user)
		comment = "Desk D6 Any-reject comment"
		result = engine.cast_vote(
			task.name,
			transition_uuid="_test-desk-reject",
			comment=comment,
			request_id="desk-reject-1",
		)
		self.assertTrue(result["transitioned"])
		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Closed")
		self.assertEqual(
			frappe.db.get_value("Workflow Task", task.name, "round_status"),
			"Transitioned",
		)
		self.assertNotEqual(
			frappe.db.get_value("Workflow Task", task.name, "round_status"),
			"Conflicted",
		)
		self.assertEqual(
			frappe.db.get_value("Workflow Task", task.name, "vote_comment"),
			comment,
		)

	def test_approver_without_source_access_is_excluded_from_threshold(self):
		kept = self._user("desk-kept@example.com")
		dropped = self._user("desk-dropped@example.com")
		self._workflow(
			"_Test Desk Cohort",
			[
				self._transition(
					"_Test Desk Cohort",
					"Closed",
					policy="All",
					uuid="_test-desk-cohort",
				)
			],
		)

		def allow_read(_doc, user):
			return user == kept

		with patch.object(engine, "_has_source_read_permission", side_effect=allow_read):
			source = self._issue("Cohort filter")
		tasks = self._tasks(source.name)
		self.assertEqual([task.approver for task in tasks], [kept])
		self.assertNotIn(dropped, [task.approver for task in tasks])
		manifest = json.loads(tasks[0].round_manifest)
		self.assertEqual(manifest["transitions"][0]["threshold"], 1)

	def test_field_edit_without_reset_keeps_round_and_accepts_vote(self):
		user = self._user("desk-edit@example.com")
		self._workflow(
			"_Test Desk Edit",
			[
				self._transition(
					"_Test Desk Edit",
					"Closed",
					policy="Any",
					uuid="_test-desk-edit",
					reset_on_change=0,
				)
			],
		)
		source = self._issue("Mid round edit")
		source.subject = "Mid round edit changed"
		source.save(ignore_permissions=True)
		task = self._tasks(source.name)[0]
		self.assertEqual(task.approver, user)
		self.assertEqual(task.round_status, "Open")
		frappe.set_user(user)
		result = engine.cast_vote(
			task.name,
			transition_uuid="_test-desk-edit",
			request_id="desk-edit-1",
		)
		self.assertTrue(result["transitioned"])
		self.assertNotEqual(result["round_status"], "Conflicted")

	def test_new_transition_keeps_an_open_round_and_its_vote(self):
		first = self._user("desk-amend-a@example.com")
		self._user("desk-amend-b@example.com")
		self._workflow(
			"_Test Desk Amend",
			[self._transition("_Test Desk Keep", "Closed", policy="All", uuid="_test-amend-keep")],
		)
		source = self._issue("Amend add transition")
		task = next(row for row in self._tasks(source.name) if row.approver == first)
		frappe.set_user(first)
		engine.cast_vote(task.name, transition_uuid="_test-amend-keep", request_id="amend-keep")
		frappe.set_user("Administrator")
		workflow = frappe.get_doc("Workflow", "_Test Desk Amend")
		workflow.append(
			"transitions",
			self._transition("_Test Desk Extra", "Closed", policy="Any", uuid="_test-amend-extra"),
		)
		workflow.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		engine.reconcile_source(source)
		tasks = self._tasks(source.name)
		self.assertTrue(all(row.round_status == "Open" for row in tasks))
		kept = frappe.get_doc("Workflow Task", task.name)
		self.assertEqual(kept.status, "Completed")
		self.assertEqual(kept.transition_uuid, "_test-amend-keep")
		manifest = json.loads(kept.round_manifest)
		self.assertIn("_test-amend-extra", {row["transition_uuid"] for row in manifest["transitions"]})

	def test_removed_unvoted_action_rejects_the_vote_and_stays_open(self):
		first = self._user("desk-drop-a@example.com")
		self._user("desk-drop-b@example.com")
		self._workflow(
			"_Test Desk Drop Action",
			[
				self._transition("_Test Desk Keep", "Closed", policy="All", uuid="_test-drop-keep"),
				self._transition("_Test Desk Drop", "Closed", policy="All", uuid="_test-drop-action"),
			],
		)
		source = self._issue("Drop unvoted action")
		task = next(row for row in self._tasks(source.name) if row.approver == first)
		workflow = frappe.get_doc("Workflow", "_Test Desk Drop Action")
		for row in list(workflow.transitions):
			if row.custom_transition_uuid == "_test-drop-action":
				workflow.remove(row)
		workflow.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		frappe.set_user(first)
		with self.assertRaises(engine.WorkflowApprovalConflictError):
			engine.cast_vote(
				task.name,
				transition_uuid="_test-drop-action",
				request_id="drop-action",
			)
		manifest = json.loads(
			frappe.db.get_value("Workflow Task", task.name, "round_manifest")
		)
		self.assertNotIn(
			"_test-drop-action",
			{row["transition_uuid"] for row in manifest["transitions"]},
		)
		self.assertEqual(
			frappe.db.get_value("Workflow Task", task.name, "round_status"),
			"Open",
		)

	def test_reconciliation_restores_missing_action_without_repeating_formed_mail(self):
		self._user("desk-repair-delivery@example.com")
		self._workflow("_Test Desk Repair Delivery", [self._transition(
			"_Test Repair Delivery", "Closed", policy="Any", uuid="_test-repair-delivery",
		)])
		source = self._issue("Warehouse acceptance: approval delivery recovery")
		task = self._tasks(source.name)[0]
		action = frappe.get_doc("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"})
		action.db_set({
			"custom_notification_mode": "Immediate", "custom_notification_status": "Enqueued",
			"custom_delivery_key": "retained-personal-delivery-key",
		}, update_modified=False)
		frappe.db.delete("Workflow Action", {"name": action.name})
		frappe.db.delete("ToDo", {"reference_type": "Workflow Task", "reference_name": task.name})
		with patch("dinext_common.workflow_approval.notifications.schedule_task_notification") as schedule:
			engine.reconcile_source(source)
			engine.reconcile_source(source)
			schedule.assert_not_called()
		restored = frappe.get_doc("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"})
		self.assertEqual(restored.custom_delivery_key, "retained-personal-delivery-key")
		self.assertEqual(restored.custom_notification_status, "Enqueued")
		self.assertEqual(frappe.db.count("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"}), 1)
		self.assertEqual(frappe.db.count("ToDo", {"reference_type": "Workflow Task", "reference_name": task.name, "status": "Open"}), 1)

	def test_reconciliation_repairs_assignment_without_resetting_existing_action(self):
		self._user("desk-repair-assignment@example.com")
		self._workflow("_Test Desk Repair Assignment", [self._transition(
			"_Test Repair Assignment", "Closed", policy="Any", uuid="_test-repair-assignment",
		)])
		source = self._issue("Project office: restore a missing approval assignment")
		task = self._tasks(source.name)[0]
		action = frappe.get_doc("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"})
		action.db_set({"custom_notification_status": "Enqueued", "custom_delivery_key": "keep-existing-key"}, update_modified=False)
		frappe.db.delete("ToDo", {"reference_type": "Workflow Task", "reference_name": task.name})
		with patch("dinext_common.workflow_approval.notifications.schedule_task_notification") as schedule:
			engine.reconcile_source(source)
			schedule.assert_not_called()
		self.assertEqual(frappe.db.count("ToDo", {"reference_type": "Workflow Task", "reference_name": task.name, "status": "Open"}), 1)
		action.reload()
		self.assertEqual(action.custom_delivery_key, "keep-existing-key")
		self.assertEqual(action.custom_notification_status, "Enqueued")

	def test_delivery_snapshot_backfill_preserves_legacy_keys_and_unknown_history(self):
		from dinext_common.workflow_approval.notifications import send_immediate_notification
		from dinext_common.workflow_approval.projections import backfill_delivery_snapshots

		self._user("desk-legacy-delivery@example.com")
		self._workflow("_Test Desk Legacy Delivery", [self._transition(
			"_Test Legacy Delivery", "Closed", policy="Any", uuid="_test-legacy-delivery",
		)])
		source = self._issue("Supplier acceptance: restore legacy delivery evidence")
		task = self._tasks(source.name)[0]
		action = frappe.get_doc("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"})
		action.db_set({"custom_notification_status": "Enqueued", "custom_delivery_key": "legacy-key"}, update_modified=False)
		frappe.db.set_value("Workflow Task", task.name, "notification_delivery_snapshot", None)
		backfill_delivery_snapshots()
		backfill_delivery_snapshots()
		snapshot = json.loads(frappe.db.get_value("Workflow Task", task.name, "notification_delivery_snapshot"))
		self.assertEqual(snapshot["custom_delivery_key"], "legacy-key")
		frappe.db.delete("Workflow Action", {"name": action.name})
		frappe.db.set_value("Workflow Task", task.name, "notification_delivery_snapshot", None)
		backfill_delivery_snapshots()
		engine.reconcile_source(source)
		with patch("dinext_common.workflow_approval.notifications._delivery_context") as delivery:
			send_immediate_notification(task.name)
			delivery.assert_not_called()
		self.assertTrue(json.loads(frappe.db.get_value("Workflow Task", task.name, "notification_delivery_snapshot"))["legacy_unknown"])

	def test_delivery_snapshot_rolls_back_with_its_action(self):
		self._user("desk-rollback-delivery@example.com")
		self._workflow("_Test Desk Rollback Delivery", [self._transition(
			"_Test Rollback Delivery", "Closed", policy="Any", uuid="_test-rollback-delivery",
		)])
		source = self._issue("Project office: notification transaction rollback")
		task = self._tasks(source.name)[0]
		action = frappe.get_doc("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"})
		before = frappe.db.get_value("Workflow Task", task.name, "notification_delivery_snapshot")
		frappe.db.savepoint("delivery_snapshot_rollback")
		action.db_set({"custom_notification_status": "Enqueued", "custom_delivery_key": "rolled-back-key"}, update_modified=False)
		self.assertNotEqual(frappe.db.get_value("Workflow Task", task.name, "notification_delivery_snapshot"), before)
		frappe.db.rollback(save_point="delivery_snapshot_rollback")
		self.assertEqual(frappe.db.get_value("Workflow Task", task.name, "notification_delivery_snapshot"), before)
		action.reload()
		self.assertNotEqual(action.custom_delivery_key, "rolled-back-key")

	def test_pending_projection_is_rescheduled_once_after_repair(self):
		self._user("desk-pending-delivery@example.com")
		self._workflow("_Test Desk Pending Delivery", [self._transition(
			"_Test Pending Delivery", "Closed", policy="Any", uuid="_test-pending-delivery",
		)])
		source = self._issue("Warehouse integration: recover interrupted notification")
		task = self._tasks(source.name)[0]
		action = frappe.get_doc("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"})
		action.db_set({"custom_notification_status": "Pending", "custom_delivery_key": "pending-key"}, update_modified=False)
		frappe.db.delete("Workflow Action", {"name": action.name})
		with patch("dinext_common.workflow_approval.notifications.schedule_task_notification") as schedule:
			engine.reconcile_source(source)
			engine.reconcile_source(source)
			schedule.assert_called_once()
		self.assertEqual(frappe.db.get_value("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"}, "custom_delivery_key"), "pending-key")

	def test_scheduling_keeps_key_written_by_another_loaded_action(self):
		from types import SimpleNamespace

		from dinext_common.workflow_approval.notifications import schedule_task_notification

		self._user("desk-nested-delivery@example.com")
		self._workflow("_Test Desk Nested Delivery", [self._transition(
			"_Test Nested Delivery", "Closed", policy="Any", uuid="_test-nested-delivery",
		)])
		source = self._issue("Project approval: retain a newly allocated delivery key")
		task = self._tasks(source.name)[0]
		with (
			patch("dinext_common.workflow_approval.notifications.profile_for_state", return_value=SimpleNamespace(enabled=True, mode="Digest")),
			patch("dinext_common.workflow_approval.notifications.notification_transitions", return_value=[object()]),
		):
			schedule_task_notification(task)
		key = frappe.db.get_value("Workflow Action", {"custom_workflow_task": task.name, "status": "Open"}, "custom_delivery_key")
		self.assertTrue(key)
		snapshot = json.loads(frappe.db.get_value("Workflow Task", task.name, "notification_delivery_snapshot"))
		self.assertEqual(snapshot["custom_delivery_key"], key)

	def test_changed_vote_conflicts_and_rebuild_carries_the_stable_vote(self):
		first = self._user("desk-carry-a@example.com")
		second = self._user("desk-carry-b@example.com")
		self._ensure_master("Workflow State", "Replied", {"workflow_state_name": "Replied"})
		self._workflow(
			"_Test Desk Carry",
			[
				self._transition("_Test Desk Keep", "Closed", policy="All", uuid="_test-carry-keep"),
				self._transition("_Test Desk Drop", "Closed", policy="All", uuid="_test-carry-drop"),
			],
			states=["Open", "Closed", "Replied"],
		)
		source = self._issue("Carry stable vote")
		tasks = {row.approver: row for row in self._tasks(source.name)}
		frappe.set_user(first)
		engine.cast_vote(tasks[first].name, transition_uuid="_test-carry-keep", request_id="carry-keep")
		frappe.set_user(second)
		engine.cast_vote(tasks[second].name, transition_uuid="_test-carry-drop", request_id="carry-drop")
		frappe.set_user("Administrator")
		workflow = frappe.get_doc("Workflow", "_Test Desk Carry")
		for row in workflow.transitions:
			if row.custom_transition_uuid == "_test-carry-drop":
				row.next_state = "Replied"
		workflow.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		engine.reconcile_source(source)
		self.assertEqual(
			frappe.db.get_value("Workflow Task", tasks[first].name, "round_status"),
			"Conflicted",
		)
		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Open")
		banner = api.get_form_approval_banner("Issue", source.name)
		self.assertEqual(banner["configuration_change"]["reason"], "configuration_changed")
		self.assertEqual(banner["configuration_change"]["stable"][0]["action"], "_Test Desk Keep")
		self.assertEqual(banner["configuration_change"]["void"][0]["change"], "semantic")
		self.assertEqual(banner["configuration_change"]["void"][0]["action"], "_Test Desk Drop")
		self.assertTrue(banner["can_reset"])
		frappe.db.delete("Has Role", {"parent": second, "role": self.role, "parenttype": "User"})
		frappe.clear_cache()
		api.reset_round(tasks[first].approval_round_id, "workflow changed")
		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Closed")
		timeline = " ".join(
			frappe.get_all(
				"Comment",
				filters={
					"reference_doctype": "Issue",
					"reference_name": source.name,
					"comment_type": "Workflow",
				},
				pluck="content",
			)
		)
		self.assertIn(first, timeline)
		self.assertIn("_Test Desk Keep", timeline)
		self.assertIn("_Test Desk Drop", timeline)
		carried = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_name": source.name,
				"completion_source": "Carried",
				"transition_uuid": "_test-carry-keep",
				"approver": first,
			},
		)
		self.assertEqual(len(carried), 1)
		dropped = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_name": source.name,
				"round_status": ("!=", "Cancelled"),
				"transition_uuid": "_test-carry-drop",
				"status": "Completed",
			},
		)
		self.assertEqual(dropped, [])

	def test_replaced_transition_uuid_is_not_carried(self):
		first = self._user("desk-uuid-a@example.com")
		self._user("desk-uuid-b@example.com")
		self._workflow(
			"_Test Desk Uuid",
			[self._transition("_Test Desk Keep", "Closed", policy="All", uuid="_test-uuid-old")],
		)
		source = self._issue("Replace uuid")
		task = next(row for row in self._tasks(source.name) if row.approver == first)
		frappe.set_user(first)
		engine.cast_vote(task.name, transition_uuid="_test-uuid-old", request_id="uuid-old")
		frappe.set_user("Administrator")
		workflow = frappe.get_doc("Workflow", "_Test Desk Uuid")
		workflow.transitions[0].custom_transition_uuid = "_test-uuid-new"
		workflow.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		engine.reconcile_source(source)
		self.assertEqual(frappe.db.get_value("Workflow Task", task.name, "round_status"), "Conflicted")
		api.reset_round(task.approval_round_id, "uuid replaced")
		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Open")
		carried = frappe.get_all(
			"Workflow Task",
			filters={"reference_name": source.name, "completion_source": "Carried"},
		)
		self.assertEqual(carried, [])

	def test_deleted_voted_transition_is_not_in_the_new_round(self):
		first = self._user("desk-delete-a@example.com")
		self._user("desk-delete-b@example.com")
		self._workflow(
			"_Test Desk Delete",
			[
				self._transition("_Test Desk Keep", "Closed", policy="All", uuid="_test-delete-keep"),
				self._transition("_Test Desk Drop", "Closed", policy="All", uuid="_test-delete-drop"),
			],
		)
		source = self._issue("Delete voted transition")
		task = next(row for row in self._tasks(source.name) if row.approver == first)
		frappe.set_user(first)
		engine.cast_vote(task.name, transition_uuid="_test-delete-keep", request_id="delete-keep")
		frappe.set_user("Administrator")
		workflow = frappe.get_doc("Workflow", "_Test Desk Delete")
		for row in list(workflow.transitions):
			if row.custom_transition_uuid == "_test-delete-keep":
				workflow.remove(row)
		workflow.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		engine.reconcile_source(source)
		self.assertEqual(frappe.db.get_value("Workflow Task", task.name, "round_status"), "Conflicted")
		api.reset_round(task.approval_round_id, "transition removed")
		self.assertEqual(frappe.db.get_value("Issue", source.name, "status"), "Open")
		kept = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_name": source.name,
				"round_status": "Open",
				"transition_uuid": "_test-delete-keep",
				"status": "Completed",
			},
		)
		self.assertEqual(kept, [])

	def test_duplicate_action_follows_role_or_uuid(self):
		role_b = "_Test WF Desk Approver B"
		if not frappe.db.exists("Role", role_b):
			frappe.get_doc({"doctype": "Role", "role_name": role_b}).insert(
				ignore_permissions=True
			)
		frappe.db.delete("Has Role", {"role": role_b, "parenttype": "User"})
		single = self._user("desk-split-one@example.com")
		both = self._user("desk-split-both@example.com", extra_roles=[role_b])
		if not frappe.db.exists("Has Role", {"parent": both, "role": role_b, "parenttype": "User"}):
			frappe.get_doc(
				{
					"doctype": "Has Role",
					"parent": both,
					"parenttype": "User",
					"parentfield": "roles",
					"role": role_b,
				}
			).db_insert()
		frappe.clear_cache(user=both)
		self._ensure_master("Workflow State", "Replied", {"workflow_state_name": "Replied"})
		action = "_Test Split"
		self._workflow(
			"_Test Desk Split",
			[
				self._transition(
					action,
					"Replied",
					policy="Any",
					uuid="_test-split-a",
					allowed=self.role,
				),
				self._transition(
					action,
					"Closed",
					policy="Any",
					uuid="_test-split-b",
					allowed=role_b,
				),
			],
			states=["Open", "Replied", "Closed"],
		)
		single_source = self._issue("Split one role")
		single_task = next(task for task in self._tasks(single_source.name) if task.approver == single)
		self.assertEqual(
			[row.action for row in single_task.available_workflow_transitions],
			[action],
		)
		frappe.set_user(single)
		named = engine.cast_vote(
			single_task.name,
			action=action,
			request_id="split-name",
		)
		self.assertTrue(named["transitioned"])
		self.assertEqual(frappe.db.get_value("Issue", single_source.name, "status"), "Replied")

		both_source = self._issue("Split both roles")
		both_task = next(task for task in self._tasks(both_source.name) if task.approver == both)
		self.assertEqual(len(both_task.available_workflow_transitions), 2)
		frappe.set_user(both)
		with self.assertRaises(engine.WorkflowApprovalConflictError) as raised:
			engine.cast_vote(
				both_task.name,
				action=action,
				request_id="split-ambiguous",
			)
		self.assertIn("transition UUID", str(raised.exception))
		chosen = engine.cast_vote(
			both_task.name,
			transition_uuid="_test-split-b",
			request_id="split-uuid",
		)
		self.assertTrue(chosen["transitioned"])
		self.assertEqual(frappe.db.get_value("Issue", both_source.name, "status"), "Closed")

	def _ensure_master(self, doctype, name, values):
		if not frappe.db.exists(doctype, name):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(
				ignore_permissions=True
			)

	def _user(self, email, extra_roles=None):
		if not frappe.db.exists("User", email):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@", 1)[0],
					"enabled": 1,
					"user_type": "System User",
					"send_welcome_email": 0,
				}
			)
			user.append("roles", {"role": self.role})
			user.append("roles", {"role": "System Manager"})
			for role in extra_roles or []:
				user.append("roles", {"role": role})
			with patch(
				"raven.raven.doctype.raven_user.raven_user.add_user_to_raven",
				return_value=None,
			):
				user.insert(ignore_permissions=True)
		return email

	def _transition(
		self,
		action,
		next_state,
		*,
		policy,
		uuid,
		comment_required=0,
		condition=None,
		allow_self_approval=1,
		reset_on_change=0,
		allowed=None,
	):
		self._ensure_master(
			"Workflow Action Master",
			action,
			{"workflow_action_name": action},
		)
		return {
			"state": "Open",
			"action": action,
			"next_state": next_state,
			"allowed": allowed or self.role,
			"allow_self_approval": allow_self_approval,
			"condition": condition,
			"custom_transition_uuid": uuid,
			"custom_parallel_approval_policy": policy,
			"custom_comment_is_required": comment_required,
			"custom_reset_on_change": reset_on_change,
		}

	def _workflow(self, name, transitions, states=None):
		if frappe.db.exists("Workflow", name):
			frappe.delete_doc("Workflow", name, force=True)
		state_rows = [
			{"state": state, "doc_status": "0", "allow_edit": "All"}
			for state in (states or ["Open", "Closed"])
		]
		workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": name,
				"document_type": "Issue",
				"workflow_state_field": "status",
				# These decision tests stop at their terminal result; repeat instances have a separate suite.
				"custom_activation_condition": "doc.status == 'Open'",
				"is_active": 1,
				"send_email_alert": 0,
				"states": state_rows,
				"transitions": transitions,
			}
		)
		workflow.insert(ignore_permissions=True)
		frappe.clear_cache(doctype="Issue")
		return workflow

	def _issue(self, subject):
		return frappe.get_doc(
			{"doctype": "Issue", "subject": subject, "status": "Open"}
		).insert(ignore_permissions=True)

	def _tasks(self, name):
		names = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": "Issue",
				"reference_name": name,
				"status": "Working",
			},
			pluck="name",
			order_by="approver asc",
		)
		return [frappe.get_doc("Workflow Task", task_name) for task_name in names]
