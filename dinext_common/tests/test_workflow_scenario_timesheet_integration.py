"""Real Timesheets parent actions preserve mixed schemas, quorum and domain rollup."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from dinext_common.workflow_approval import api
from dinext_common.workflow_approval.scenarios import service, timesheet_actions
from dinext_common.workflow_approval.scenarios.metadata import next_selection_order

POSITION = "User Timesheet Position"
FIELDS = ("custom_timesheet_scenario_a", "custom_timesheet_scenario_b")


class TestWorkflowScenarioTimesheetIntegration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not getattr(frappe.local, "db", None) or not frappe.conf.get("workflow_scenarios_test_site"):
			raise unittest.SkipTest("Requires an explicitly disposable Workflow scenario test site")
		if "dinext_timesheets" not in frappe.get_installed_apps():
			raise unittest.SkipTest("Requires the optional Timesheets app")
		for doctype, module, name in (
			("Worker Utilization Table", "project_workload_assignment", "worker_utilization_table"),
			("Cost Center Table", "dinext_projects_pl", "cost_center_table"),
		):
			if not frappe.db.exists("DocType", doctype):
				frappe.reload_doc(module, "doctype", name)
		create_custom_fields({POSITION: [{"fieldname": field, "fieldtype": "Data", "label": field,
			"module": "Dinext Common"} for field in FIELDS]}, update=True)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		self.previous_engine = frappe.conf.get("enable_parallel_workflow_approval")
		self.previous_mute = frappe.flags.get("mute_emails")
		self.previous_after_commit = tuple(frappe.db.after_commit._functions)
		frappe.conf.enable_parallel_workflow_approval = True
		frappe.flags.mute_emails = True
		frappe.db.savepoint("scenario_timesheet_test")
		self.addCleanup(self._rollback_fixture)
		self.marker = "Mixed-TS-" + frappe.generate_hash(length=8)
		self.roles = [self.marker + " Role A", self.marker + " Role B"]
		for role in self.roles:
			frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
		self.reviewer = self.marker.lower() + "-reviewer@example.com"
		self.other = self.marker.lower() + "-other@example.com"
		self.reviewer_name = "Mixed Timesheet Reviewer " + self.marker
		self.other_name = "Remaining Timesheet Reviewer " + self.marker
		for user, full_name, roles in (
			(self.reviewer, self.reviewer_name, self.roles),
			(self.other, self.other_name, self.roles[:1]),
		):
			# No User Email rows are created; avoid taking its unchanged global summary lock
			# for the duration of this transactional fixture alongside other test processes.
			with patch("frappe.core.doctype.user.user.ask_pass_update"):
				frappe.get_doc({"doctype": "User", "email": user, "first_name": full_name,
					"send_welcome_email": 0, "roles": [{"role": role} for role in [
						*roles, "System Manager", "Dinext_UT_Full_Access", "Dinext_UTP_Appoval",
					]]}).insert(ignore_permissions=True)
		self._calendar_and_worker()
		# Reserve only this transaction's synthetic custom_data values; ordinary positions
		# continue to match their existing producer scenarios.
		for name in frappe.get_all("Workflow", filters={"document_type": POSITION, "is_active": 1}, pluck="name"):
			workflow = frappe.get_doc("Workflow", name)
			condition = str(workflow.get("custom_activation_condition") or "True")
			frappe.db.set_value("Workflow", name, "custom_activation_condition",
				f"not (doc.custom_data or '').startswith('{self.marker}') and ({condition})", update_modified=False)
		for state in ("Pending Approval", "Rejected"):
			self._master("Workflow State", state, {"workflow_state_name": state})
		self.action = self.marker + " Reject"
		self.reopen = self.marker + " Reopen"
		for action in (self.action, self.reopen):
			self._master("Workflow Action Master", action, {"workflow_action_name": action})
		self.workflows = [self._workflow(index, suffix) for index, suffix in enumerate(("A", "B"))]
		settings = frappe.get_single("Timesheet Settings")
		settings.set("position_rules", [
			{"position_status": "Rejected", "timesheet_status": "Rejected", "threshold": "Any",
				"check_timesheet": 0, "move_all_positions": 0},
			{"position_status": "Pending Approval", "timesheet_status": "Pending Approval", "threshold": "Any",
				"check_timesheet": 0, "move_all_positions": 0},
		])
		# Populate only the rule table owned by this transactional fixture.
		settings.update_child_table("position_rules")
		self.parent = frappe.get_doc({"doctype": "User Timesheet", "timesheet_from": self.reviewer,
			"timesheet_from_name": self.marker, "ts_from_template": self.template.name,
			"ts_valid_from": "2026-11-02", "ts_valid_for": "2026-11-06", "ut_status": "Pending Approval",
		}).insert(ignore_permissions=True, set_name=self.marker)
		previous_defer = getattr(frappe.flags, "defer_timesheet_rollup", None)
		previous_in_test = frappe.flags.in_test
		frappe.flags.defer_timesheet_rollup = True
		# Keep the producer's unrelated limit notifications deferred until commit, as in
		# production. This fixture is rolled back and never starts that background job.
		frappe.flags.in_test = False
		try:
			self.positions = [frappe.get_doc({"doctype": POSITION, "user_timesheet": self.parent.name,
				"user": self.reviewer, "status": "Pending Approval", "workflow_state": "Pending Approval",
				"custom_data": self.marker + "-" + suffix,
			}).insert(ignore_permissions=True, set_name=self.marker + "-" + suffix) for suffix in ("A", "B")]
		finally:
			frappe.flags.defer_timesheet_rollup = previous_defer
			frappe.flags.in_test = previous_in_test

	def _rollback_fixture(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="scenario_timesheet_test")
		frappe.db.after_commit.reset()
		for callback in self.previous_after_commit:
			frappe.db.after_commit.add(callback)
		frappe.conf.enable_parallel_workflow_approval = self.previous_engine
		frappe.flags.mute_emails = self.previous_mute
		frappe.local.workflow_scenario_cascade = None
		frappe.clear_cache(doctype=POSITION)

	def _master(self, doctype, name, values):
		if not frappe.db.exists(doctype, name):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(ignore_permissions=True)

	def _calendar_and_worker(self):
		group = frappe.get_doc({"doctype": "User Group", "name": self.marker,
			"user_group_members": [{"user": self.reviewer}]}).insert(ignore_permissions=True, set_name=self.marker)
		calendar = frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": self.marker,
			"from_date": "2026-01-01", "to_date": "2027-12-31"}).insert(ignore_permissions=True)
		hours = frappe.get_doc({"doctype": "Working Hours On Date", "hod_subject": self.marker,
			"hod_from_date": "2026-01-01", "hod_to_date": "2027-12-31"}).insert(ignore_permissions=True)
		self.template = frappe.get_doc({"doctype": "Timesheet Template", "ttsubject": self.marker,
			"enabled": 1, "doctype_for_timesheet": [{"dtdoctype": "Task"}],
			"tt_working_hours_on_date": hours.name, "ttreporting_period": "Недельный",
			"hours_on_date": 8, "minimum_hours": 0, "maximum_hours": 8, "working_days": 1,
		}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Worker", "wuser": self.reviewer,
			"wuser_group": group.name, "wtimesheet_template": self.template.name,
			"wholiday_list": calendar.name, "wvalid_from": "2026-01-01"}).insert(ignore_permissions=True)

	def _workflow(self, index, suffix):
		return frappe.get_doc({"doctype": "Workflow", "workflow_name": self.marker + " " + suffix,
			"document_type": POSITION, "workflow_state_field": FIELDS[index], "is_active": 1,
			"send_email_alert": 0, "custom_selection_order": next_selection_order(POSITION),
			"custom_activation_condition": f"doc.custom_data == '{self.marker}-{suffix}'",
			"states": [{"state": state, "doc_status": "0", "allow_edit": self.roles[index],
				"update_field": "status", "update_value": state} for state in ("Pending Approval", "Rejected")],
			"transitions": [
				{"state": "Pending Approval", "action": self.action, "next_state": "Rejected",
					"allowed": self.roles[index], "allow_self_approval": 1,
					"custom_transition_uuid": self.marker + "-" + suffix,
					"custom_parallel_approval_policy": "All" if index == 0 else "Any",
					"custom_comment_is_required": int(index == 1)},
				{"state": "Rejected", "action": self.reopen, "next_state": "Pending Approval",
					"allowed": self.roles[index], "allow_self_approval": 1,
					"custom_transition_uuid": self.marker + "-reopen-" + suffix,
					"custom_parallel_approval_policy": "Any"},
			],
		}).insert(ignore_permissions=True)

	def test_parent_exact_targets_keep_quorum_status_bridge_progress_and_pending_names(self):
		frappe.set_user(self.reviewer)
		pending = api.get_pending_approvers("User Timesheet", self.parent.name)
		self.assertEqual({row["approver"] for row in pending}, {self.reviewer, self.other})
		self.assertEqual({row["approver_name"] for row in pending},
			{self.reviewer_name, self.other_name})
		available = timesheet_actions.get_timesheet_position_actions(self.parent.name)
		chosen = next(row for row in available["actions"] if row["action"] == self.action)
		self.assertTrue(chosen["comment_is_required"])
		self.assertEqual({row["transition_uuid"] for row in chosen["targets"]},
			{self.marker + "-A", self.marker + "-B"})
		self.assertEqual({row["workflow"] for row in chosen["targets"]}, {row.name for row in self.workflows})
		with self.assertRaises(frappe.ValidationError):
			timesheet_actions.apply_timesheet_position_action(self.parent.name, self.action, targets=chosen["targets"])
		events = []
		with patch.object(frappe, "publish_realtime", side_effect=lambda event, data=None, **kwargs: events.append((event, data or kwargs.get("message") or {}))):
			result = timesheet_actions.apply_timesheet_position_action(self.parent.name, self.action,
				comment="Synthetic mixed-schema review", request_id=self.marker, track_progress=True,
				targets=chosen["targets"])
		self.assertEqual((result["processed"], result["total"]), (2, 2))
		self.assertEqual([row["transitioned"] for row in result["results"]], [False, True])
		progress = [data["count"] for event, data in events if event == "dinext_workflow_progress"]
		self.assertEqual(progress, [1, 2])
		a, b = [doc.reload() for doc in self.positions]
		self.assertEqual((a.get(FIELDS[0]), b.get(FIELDS[1])), ("Pending Approval", "Rejected"))
		self.assertEqual((a.status, b.status), ("Pending Approval", "Rejected"))
		self.assertEqual(b.workflow_state, "Pending Approval")
		self.assertEqual(self.parent.reload().ut_status, "Rejected")
		self.assertEqual(service.get_context(a)["process_status"], "Running")
		# A completed vote cannot reappear as a domain action while quorum waits.
		actions_after = timesheet_actions.get_timesheet_position_actions(self.parent.name)
		self.assertNotIn(self.action, {row["action"] for row in actions_after["actions"]})
		before = frappe.db.count("Workflow Task", {"reference_doctype": POSITION,
			"reference_name": ("in", [a.name, b.name]), "status": "Completed"})
		replayed = timesheet_actions.apply_timesheet_position_action(self.parent.name, self.action,
			comment="Synthetic mixed-schema review", request_id=self.marker, targets=chosen["targets"])
		self.assertEqual(replayed["results"], result["results"])
		self.assertEqual(frappe.db.count("Workflow Task", {"reference_doctype": POSITION,
			"reference_name": ("in", [a.name, b.name]), "status": "Completed"}), before)
		remaining = api.get_pending_approvers("User Timesheet", self.parent.name)
		self.assertIn(self.other_name, {row["approver_name"] for row in remaining})

	def test_individual_vote_rolls_up_parent_when_only_selected_field_changes(self):
		workflow = self.workflows[1]
		for row in workflow.states:
			if row.state == "Rejected":
				row.update_field = None
				row.update_value = None
		workflow.save(ignore_permissions=True)
		frappe.set_user(self.reviewer)
		source = self.positions[1]
		task = frappe.db.get_value("Workflow Task", {"reference_doctype": POSITION,
			"reference_name": source.name, "approver": self.reviewer,
			"status": "Working", "round_status": "Open"}, "name")
		result = api.vote(task, transition_uuid=self.marker + "-B", comment="Individual selected-field vote")
		self.assertTrue(result["transitioned"])
		source.reload()
		self.assertEqual(source.get(FIELDS[1]), "Rejected")
		self.assertEqual(source.status, "Pending Approval")
		self.assertEqual(source.workflow_state, "Pending Approval")
		self.assertEqual(self.parent.reload().ut_status, "Rejected")
