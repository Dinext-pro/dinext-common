from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import frappe

from dinext_common.tests.test_workflow_approval_integration import TestWorkflowApprovalIntegration as Base
from dinext_common.workflow_approval import engine


class TestDeadlineIntegration(Base):
	def test_dropped_completed_vote_opens_new_obligation_while_unfinished_assignment_keeps_clock(self):
		other = "deadline-new-obligation-" + frappe.generate_hash(length=8) + "@example.test"
		frappe.get_doc(
			dict(
				doctype="User",
				email=other,
				first_name="Other Approver",
				send_welcome_email=0,
				roles=[{"role": self.role}, {"role": "System Manager"}],
			)
		).insert(ignore_permissions=True)
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].custom_parallel_approval_policy = "All"
		workflow.save(ignore_permissions=True)
		source, old = self.source_task(share_with=[self.user, other])
		old_other = frappe.get_doc(
			"Workflow Task",
			frappe.db.get_value(
				"Workflow Task", {"reference_name": source.name, "approver": other, "status": "Working"}
			),
		)
		frappe.session.user = self.user
		try:
			engine.cast_vote(
				old.name,
				transition_uuid=old.available_workflow_transitions[0].transition_uuid,
				request_id="deadline-drop-" + frappe.generate_hash(length=8),
			)
		finally:
			frappe.session.user = "Administrator"
		old.reload()
		self.assertEqual(old.status, "Completed")
		workflow.reload()
		workflow.transitions[0].condition = "doc.subject != 'Blocked'"
		workflow.save(ignore_permissions=True)
		engine.reconcile_source(source)
		result = engine.rebuild_configuration_conflict(source, old.approval_round_id, "Decision rule changed")
		new = next(
			frappe.get_doc("Workflow Task", name)
			for name in result["new_tasks"]
			if frappe.db.get_value("Workflow Task", name, "approver") == self.user
		)
		new_other = next(
			frappe.get_doc("Workflow Task", name)
			for name in result["new_tasks"]
			if frappe.db.get_value("Workflow Task", name, "approver") == other
		)
		self.assertEqual(
			new.status,
			"Working",
			{"carried": result["carried"], "dropped": result["dropped"], "source": source.status},
		)
		self.assertNotEqual(new.deadline_assignment_id, old.deadline_assignment_id)
		self.assertGreaterEqual(new.deadline_started_at, old.completed_at)
		self.assertEqual(new_other.deadline_assignment_id, old_other.deadline_assignment_id)
		self.assertEqual(new_other.deadline_due_at, old_other.deadline_due_at)
		from dinext_common.workflow_approval.deadlines.discipline import observations

		rows = observations(
			[old.as_dict(), new.as_dict()],
			now=new.deadline_started_at + timedelta(days=2),
			site_timezone="Europe/Moscow",
		)
		self.assertEqual(len(rows), 2)
		self.assertEqual({row["discipline_status"] for row in rows}, {"On Time", "Overdue"})

	def test_public_deadline_cards_are_readable_by_an_ordinary_approver_but_not_writable(self):
		user = frappe.get_doc("User", self.user)
		original_roles = [{"role": row.role} for row in user.roles]
		previous_user = frappe.session.user
		try:
			user.set("roles", [row for row in user.roles if row.role != "System Manager"])
			user.save(ignore_permissions=True)
			frappe.set_user(self.user)
			for name in (
				"Overdue Approval Assignments",
				"On-time Approvals",
				"Approvals Completed Late",
				"Approval Deadline Errors",
				"On-time Timesheet Submissions",
				"On-time Timesheet Approvals",
				"Overdue Timesheet Approvals",
				"Overdue Timesheet Positions",
				"Timesheet Hours Awaiting Approval",
			):
				with self.subTest(card=name):
					self.assertFalse(frappe.get_doc("Number Card", name).currency)
					self.assertTrue(frappe.has_permission("Number Card", "read", doc=name, user=self.user))
					self.assertFalse(frappe.has_permission("Number Card", "write", doc=name, user=self.user))
		finally:
			frappe.set_user("Administrator")
			user.reload().set("roles", original_roles)
			user.save(ignore_permissions=True)
			frappe.set_user(previous_user)

	def test_discipline_bounds_history_before_permission_checks_and_loads_no_full_tasks(self):
		from dinext_common.workflow_approval.deadlines.discipline import visible_rows

		source, current = self.source_task()
		old_names = []
		for index in range(12):
			old = frappe.copy_doc(current)
			old.name = "deadline-old-" + frappe.generate_hash(length=16)
			old.update(
				dict(
					status="Completed",
					round_status="Completed",
					completion_source="Manual",
					deadline_assignment_id=old.name,
					deadline_due_at="2020-01-01 10:00:00",
					completed_at="2020-01-01 09:00:00",
				)
			)
			old.db_insert()
			old_names.append(old.name)
		original = frappe.get_doc
		loads = []

		def counted(*args, **kwargs):
			if args and args[0] == "Workflow Task" and len(args) > 1:
				loads.append(args[1])
			return original(*args, **kwargs)

		with patch.object(frappe, "get_doc", side_effect=counted):
			rows = visible_rows(
				{
					"workflow": self.workflow_name,
					"reference_name": source.name,
					"from_date": "2026-11-01",
					"to_date": "2026-11-30",
				}
			)
		self.assertEqual({row["name"] for row in rows}, {current.name})
		self.assertEqual(loads, [])

	workflow_name = "_Test Deadline Integration"
	action_name = "_Test Deadline Approve"
	reopen_action_name = "_Test Deadline Reopen"
	user = "deadline-approver@example.com"

	def setUp(self):
		super().setUp()
		self.role = "_Test Deadline Approver"
		self._ensure_master("Role", self.role, {"role_name": self.role})
		user = frappe.get_doc("User", self.user)
		user.append("roles", {"role": self.role})
		user.save(ignore_permissions=True)
		if not frappe.db.exists("Custom DocPerm", {"parent": "Issue", "role": self.role}):
			frappe.get_doc(
				dict(doctype="Custom DocPerm", parent="Issue", role=self.role, permlevel=0, read=1, write=1)
			).insert(ignore_permissions=True)
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		for row in workflow.transitions:
			row.allowed = self.role
		workflow.save(ignore_permissions=True)
		frappe.clear_cache()

	def source_task(self, *, share_with=None):
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		transition = workflow.transitions[0]
		transition.update(
			dict(
				custom_deadline_enabled=1,
				custom_deadline_value=24,
				custom_deadline_unit="Hours",
				custom_deadline_recipient_type="User",
				custom_deadline_recipient_user=self.user,
				custom_deadline_email_mode="Digest",
				custom_deadline_interval_unit="Days",
				custom_deadline_interval_value=1,
				custom_deadline_send_times="08:00, 17:00",
			)
		)
		workflow.save(ignore_permissions=True)
		if share_with:
			frappe.conf.enable_parallel_workflow_approval = False
		source = frappe.get_doc(dict(doctype="Issue", subject="Deadline test", status="Open")).insert(
			ignore_permissions=True
		)
		if share_with:
			from frappe.share import add

			for user in share_with:
				add("Issue", source.name, user, read=1, flags={"ignore_share_permission": True})
			frappe.conf.enable_parallel_workflow_approval = True
			engine.reconcile_source(source)
		name = frappe.db.get_value(
			"Workflow Task",
			dict(reference_doctype="Issue", reference_name=source.name, approver=self.user, status="Working"),
			"name",
		)
		return source, frappe.get_doc("Workflow Task", name)

	def digest_source_task(self):
		# Digest identity includes workflow/state/recipient/slot/policy, not the source.
		# A distinct policy isolates these cases from committed fixtures of another run.
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].custom_transition_uuid = str(uuid4())
		workflow.save(ignore_permissions=True)
		frappe.db.set_value("User", self.user, "time_zone", "Europe/Moscow")
		return self.source_task()

	def test_assignment_gets_frozen_deadline_and_changes_apply_only_to_new_tasks(self):
		source, task = self.source_task()
		self.assertTrue(task.deadline_due_at)
		self.assertEqual(task.deadline_due_at - task.deadline_started_at, timedelta(hours=24))
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].custom_deadline_value = 1
		workflow.save(ignore_permissions=True)
		engine.reconcile_source(source)
		task.reload()
		self.assertEqual(task.deadline_due_at - task.deadline_started_at, timedelta(hours=24))

	def test_configuration_rebuild_preserves_assignment_and_due(self):
		source, task = self.source_task()
		self.assertTrue(task.deadline_assignment_id)
		rebuilt = engine.rebuild_configuration_conflict(source, task.approval_round_id, "Test repair")
		current = next(
			frappe.get_doc("Workflow Task", name)
			for name in rebuilt["new_tasks"]
			if frappe.db.get_value("Workflow Task", name, "approver") == self.user
		)
		self.assertEqual(current.deadline_assignment_id, task.deadline_assignment_id)
		self.assertEqual(current.deadline_started_at, task.deadline_started_at)
		self.assertEqual(current.deadline_due_at, task.deadline_due_at)

	def test_recipient_timezone_does_not_reinterpret_site_timestamp(self):
		frappe.db.set_value("User", self.user, "time_zone", "America/New_York")
		source, task = self.source_task()
		self.assertEqual(task.deadline_due_at - task.deadline_started_at, timedelta(hours=24))

	def test_missing_task_repair_keeps_original_deadline(self):
		other = "deadline-repair-" + frappe.generate_hash(length=8) + "@example.test"
		frappe.get_doc(
			dict(
				doctype="User",
				email=other,
				first_name="Repair Approver",
				send_welcome_email=0,
				roles=[{"role": self.role}, {"role": "System Manager"}],
			)
		).insert(ignore_permissions=True)
		source, task = self.source_task()
		original = (task.deadline_assignment_id, task.deadline_started_at, task.deadline_due_at)
		# Controlled corruption of a task-owned fixture, representing interrupted retention/repair.
		child = task.meta.get_field("available_workflow_transitions").options
		frappe.db.delete(child, {"parent": task.name})
		frappe.db.delete("Workflow Task", {"name": task.name})
		frappe.db.value_cache.clear()
		engine.reconcile_source(source)
		repaired = frappe.get_doc("Workflow Task", task.name)
		self.assertEqual(
			(repaired.deadline_assignment_id, repaired.deadline_started_at, repaired.deadline_due_at),
			original,
		)

	def test_overdue_digest_retries_share_one_queue_and_closed_task_is_excluded(self):
		from datetime import datetime, timezone

		from dinext_common.workflow_approval.deadlines.delivery import send_group
		from dinext_common.workflow_approval.email_preferences import email_allowed

		source, task = self.digest_source_task()
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.send_email_alert = 1
		workflow.save(ignore_permissions=True)
		self.assertTrue(email_allowed(self.user))
		frappe.db.set_value("Workflow Task", task.name, "deadline_due_at", "2026-01-01 00:00:00")
		task.reload()
		slot = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=5, minute=0, second=0, microsecond=0)
		kwargs = dict(
			workflow=workflow,
			recipient=self.user,
			task_names=[task.name],
			slot=slot,
			now=slot + timedelta(minutes=1),
		)
		with patch("dinext_common.workflow_approval.notifications._sendmail_for_user") as send:
			send_group(**kwargs)
			send_group(**kwargs)
			self.assertEqual(send.call_count, 1)
			workflow.transitions[0].custom_deadline_email_template = "Dinext Workflow Correction"
			workflow.save(ignore_permissions=True)
			send_group(**kwargs)
			self.assertEqual(send.call_count, 1)
			self.assertNotIn("preview_action", send.call_args.kwargs["message"])
			frappe.db.set_value("Workflow Task", task.name, "status", "Completed")
			kwargs["slot"] = slot.replace(hour=14)
			kwargs["now"] = kwargs["slot"] + timedelta(minutes=1)
			send_group(**kwargs)
			self.assertEqual(send.call_count, 1)

	def test_queue_and_delivery_claim_rollback_together_and_retry_forms_one_mime(self):
		from datetime import datetime, timezone

		from dinext_common.workflow_approval import notifications as mail
		from dinext_common.workflow_approval.deadlines.delivery import send_group

		source, task = self.digest_source_task()
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.send_email_alert = 1
		workflow.save(ignore_permissions=True)
		frappe.db.set_value("Workflow Task", task.name, "deadline_due_at", "2026-01-01 00:00:00")
		slot = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=5, minute=0, second=0, microsecond=0)
		kwargs = dict(
			workflow=workflow,
			recipient=self.user,
			task_names=[task.name],
			slot=slot,
			now=slot + timedelta(minutes=1),
		)
		before = frappe.db.count("Email Queue")
		previous_deliveries = frappe.db.count("Workflow Deadline Delivery", {"workflow": workflow.name})
		native = mail._sendmail_for_user

		def enqueue_then_fail(*args, **values):
			native(*args, **values)
			raise RuntimeError("Injected interruption after queue insert")

		with patch.object(mail, "_sendmail_for_user", side_effect=enqueue_then_fail):
			with self.assertRaisesRegex(RuntimeError, "Injected interruption"):
				send_group(**kwargs)
		self.assertEqual(frappe.db.count("Email Queue"), before)
		self.assertEqual(
			frappe.db.count("Workflow Deadline Delivery", {"workflow": workflow.name}), previous_deliveries
		)
		send_group(**kwargs)
		send_group(**kwargs)
		self.assertEqual(frappe.db.count("Email Queue"), before + 1)
		self.assertEqual(
			frappe.db.count("Workflow Deadline Delivery", {"workflow": workflow.name}),
			previous_deliveries + 1,
		)

	def test_deadline_uses_live_template_and_new_schedule_before_forming_email(self):
		from datetime import datetime, timezone

		from dinext_common.workflow_approval.deadlines.delivery import send_group

		source, task = self.digest_source_task()
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.send_email_alert = 1
		workflow.save(ignore_permissions=True)
		stale = frappe.get_doc("Workflow", self.workflow_name)
		template = frappe.get_doc(
			dict(
				doctype="Email Template",
				name="_Test Live Deadline " + frappe.generate_hash(length=6),
				use_html=1,
				subject="Current deadline",
				response_html="<p>LIVE_DEADLINE_TEMPLATE</p>",
			)
		).insert(ignore_permissions=True)
		workflow.transitions[0].custom_deadline_email_template = template.name
		workflow.transitions[0].custom_deadline_send_times = "09:00"
		workflow.save(ignore_permissions=True)
		frappe.db.set_value("Workflow Task", task.name, "deadline_due_at", "2026-01-01 00:00:00")
		slot = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=5, minute=0, second=0, microsecond=0)
		kwargs = dict(
			workflow=stale,
			recipient=self.user,
			task_names=[task.name],
			slot=slot,
			now=slot + timedelta(minutes=1),
		)
		with patch("dinext_common.workflow_approval.notifications._sendmail_for_user") as send:
			send_group(**kwargs)
			self.assertEqual(send.call_count, 0)
			kwargs["slot"] = slot.replace(hour=6)
			kwargs["now"] = kwargs["slot"] + timedelta(minutes=1)
			send_group(**kwargs)
			self.assertEqual(send.call_count, 1)
			self.assertIn("LIVE_DEADLINE_TEMPLATE", send.call_args.kwargs["message"])

	def test_signed_comment_uses_live_rule_and_invalid_input_keeps_retry(self):
		from dinext_common.workflow_approval import signed_links

		source, task = self.source_task()
		token = signed_links._issue_command(
			dict(
				task_name=task.name,
				user=task.approver,
				transition_uuid=task.available_workflow_transitions[0].transition_uuid,
				delivery_key=signed_links.ensure_delivery_key(task.name),
			)
		)
		self.addCleanup(signed_links._consume_command, token)
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		workflow.transitions[0].custom_comment_is_required = 1
		workflow.save(ignore_permissions=True)
		frappe.set_user(task.approver)
		with self.assertRaises(frappe.ValidationError):
			signed_links.confirm_action(token, comment=" ")
		self.assertIsNotNone(signed_links._peek_command(token))
		task.reload()
		self.assertEqual(task.status, "Working")
		with patch.object(signed_links, "return_success_page"):
			signed_links.confirm_action(token, comment="Verified current requirement")
		task.reload()
		self.assertEqual(task.status, "Completed")

	def test_discipline_filters_cannot_expose_another_approver_or_denied_source(self):
		from dinext_common.workflow_approval.deadlines.discipline import visible_rows

		user = frappe.get_doc("User", self.user)
		user.set("roles", [row for row in user.roles if row.role != "System Manager"])
		user.save(ignore_permissions=True)
		other = "deadline-other-" + frappe.generate_hash(length=8) + "@example.test"
		frappe.get_doc(
			dict(
				doctype="User",
				email=other,
				first_name="Other Approver",
				send_welcome_email=0,
				roles=[{"role": self.role}],
			)
		).insert(ignore_permissions=True)
		source, task = self.source_task(share_with=[self.user, other])
		frappe.set_user(self.user)
		rows = visible_rows({"workflow": self.workflow_name})
		self.assertEqual({row["approver"] for row in rows}, {self.user})
		self.assertEqual(visible_rows({"workflow": self.workflow_name, "approver": other}), [])
		frappe.set_user("Administrator")
		for name in frappe.get_all(
			"Custom DocPerm", filters={"parent": "Issue", "role": self.role}, pluck="name"
		):
			frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True)
		frappe.share.remove("Issue", source.name, self.user, flags={"ignore_share_permission": True})
		frappe.clear_cache()
		frappe.set_user(self.user)
		self.assertEqual(visible_rows({"workflow": self.workflow_name}), [])

	def test_source_permission_check_preserves_browser_session_and_request(self):
		source, task = self.source_task()
		old_sid = frappe.session.sid
		old_form = frappe.local.form_dict
		try:
			frappe.session.sid = "unchanged-browser-session"
			frappe.local.form_dict = frappe._dict(request_marker="keep")
			self.assertTrue(engine._has_source_read_permission(source, task.approver))
			self.assertEqual(frappe.session.sid, "unchanged-browser-session")
			self.assertEqual(frappe.local.form_dict.get("request_marker"), "keep")
		finally:
			frappe.session.sid = old_sid
			frappe.local.form_dict = old_form

	def test_fixture_import_preserves_deadline_policy_and_explicit_disable(self):
		from frappe.modules.import_file import import_doc

		source, task = self.source_task()
		workflow = frappe.get_doc("Workflow", self.workflow_name)
		fixture = workflow.as_dict()
		fixture["transitions"][0]["custom_deadline_value"] = 6
		before = frappe.flags.in_fixtures
		try:
			frappe.flags.in_fixtures = True
			import_doc(fixture)
			current = frappe.get_doc("Workflow", self.workflow_name)
			self.assertEqual(current.transitions[0].custom_deadline_value, 24)
			self.assertEqual(
				current.transitions[0].custom_deadline_schedule_anchor,
				workflow.transitions[0].custom_deadline_schedule_anchor,
			)
			frappe.flags.in_fixtures = False
			current.transitions[0].custom_deadline_enabled = 0
			current.save(ignore_permissions=True)
			frappe.flags.in_fixtures = True
			import_doc(fixture)
			self.assertFalse(
				frappe.get_doc("Workflow", self.workflow_name).transitions[0].custom_deadline_enabled
			)
		finally:
			frappe.flags.in_fixtures = before
