import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.workflow_approval import api, engine


class TestWorkflowApprovalReportRows(unittest.TestCase):
	def test_queue_rows_keep_attribute_access(self):
		row = {"name": "TASK-1", "completed_at": "2026-01-02 00:00:00"}
		with (
			patch.object(frappe, "get_all", return_value=[row]),
			patch.object(
				frappe,
				"get_doc",
				return_value=SimpleNamespace(available_workflow_transitions=[]),
			),
			patch.object(api, "has_workflow_task_permission", return_value=True),
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

		with (
			patch.object(
				frappe,
				"get_all",
				return_value=[row("OPEN", "Open"), row("STALL", "Stalled"), row("CONF", "Conflicted")],
			),
			patch.object(frappe, "get_doc", return_value=SimpleNamespace()),
			patch.object(api, "is_workflow_monitor", return_value=True),
			patch.object(api, "has_workflow_task_permission", return_value=True),
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
		with (
			patch.object(frappe, "get_all", return_value=[row]),
			patch.object(frappe, "get_doc", return_value=SimpleNamespace()),
			patch.object(api, "is_workflow_monitor", return_value=True),
			patch.object(api, "has_workflow_task_permission", return_value=True),
		):
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
			"dinext_common.dinext_common.report.my_approval_history.my_approval_history.get_my_history",
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
			round_manifest=json.dumps(
				{"transitions": [{"action": "Approve", "threshold": 2}]}
			),
		)
		with (
			patch(
				"dinext_common.dinext_common.report.my_approvals.my_approvals.get_my_queue",
				return_value=[row],
			),
			patch(
				"dinext_common.dinext_common.report.my_approvals.my_approvals._completed_votes",
				return_value={("ROUND-1"): 0},
			),
		):
			_columns, rows, _message, _chart = execute({})
		self.assertEqual(rows[0].available_actions, "Approve")
		self.assertEqual(rows[0].progress, "0/2")


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
