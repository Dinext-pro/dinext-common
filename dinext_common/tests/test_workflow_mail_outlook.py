"""Recipient-visible regressions from the November Outlook screenshots."""

# Russian workflow labels intentionally use Cyrillic characters.
# ruff: noqa: RUF001

from copy import deepcopy
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkflowMailOutlook(FrappeTestCase):
	def setUp(self):
		super().setUp()
		from dinext_common.tests.test_workflow_email_refinements import TestWorkflowEmailRefinements

		frappe.set_user("Administrator")
		self.fixture = TestWorkflowEmailRefinements()
		self.fixture.users = []
		for first, last in (("Иван", "Петров"), ("Мария", "Соколова"), ("Алексей", "Смирнов")):
			user = frappe.get_doc(
				dict(
					doctype="User",
					email="outlook-" + frappe.generate_hash(length=10) + "@example.test",
					first_name=first,
					last_name=last,
					language="ru",
					send_welcome_email=0,
				)
			).insert(ignore_permissions=True)
			self.fixture.users.append(user.name)
		self.fixture.user = self.fixture.users[0]

	def test_footer_background_is_a_full_width_presentation_table(self):
		_subject, _message, soup = self.fixture.native_message("Dinext Workflow Digest")
		footer = soup.select_one('[data-dinext-email-footer="1"]')
		background = footer.find_parent("table", attrs={"width": "100%", "bgcolor": "#f3f5f8"})
		self.assertIsNotNone(background)
		self.assertEqual(background.get("role"), "presentation")
		self.assertNotIn("max-width", background.get("style", ""))
		self.assertEqual(len(background.select('img[alt="Dinext"]')), 1)

	def test_actions_share_one_table_row_without_display_css(self):
		_subject, _message, soup = self.fixture.native_message("Dinext Workflow Action")
		links = soup.select('a[href*="preview_action"]')
		self.assertEqual(len(links), 2)
		rows = [link.find_parent("table").find_parent("td").find_parent("tr") for link in links]
		self.assertIs(rows[0], rows[1])
		self.assertEqual(len(rows[0].find_all("td", recursive=False)), 2)
		self.assertNotIn("inline-table", str(rows[0]))

	@staticmethod
	def choices():
		rows = [
			frappe._dict(
				state="На согласовании",
				action=action,
				next_state=target,
				transition_uuid=uuid,
				transition_idx=idx,
				policy="Any",
				threshold=1,
				comment_is_required=0,
				auto_complete_unchanged=0,
			)
			for idx, action, target, uuid in [
				(1, "Согласовано", "Согласовано", "approve"),
				(2, "Не согласовано", "Отклонено", "manager"),
				(3, "Не согласовано", "Отклонено", "director"),
			]
		]
		workflow = frappe._dict(
			transitions=[
				frappe._dict(
					state=r.state,
					action=r.action,
					next_state=r.next_state,
					custom_transition_uuid=r.transition_uuid,
					condition="doc.is_active == 'No'",
					allow_self_approval=1,
					custom_reset_on_change=0,
					custom_comment_is_required=0,
					custom_parallel_approval_policy="Any",
				)
				for r in rows
			]
		)
		return frappe._dict(name="personal-project-assignment", available_workflow_transitions=rows), workflow

	def test_equivalent_project_rejections_use_one_authorized_link_and_preserve_task_rows(self):
		from dinext_common.workflow_approval.notifications import _task_actions

		task, workflow = self.choices()
		before = deepcopy(task.available_workflow_transitions)
		with patch(
			"dinext_common.workflow_approval.signed_links.get_task_action_url",
			side_effect=lambda task, row: "/preview_action?choice=" + row.transition_uuid,
		):
			actions = _task_actions(task, workflow=workflow)
			self.assertEqual([a["action_name"] for a in actions], ["Согласовано", "Не согласовано"])
			self.assertTrue(actions[1]["action_link"].endswith("manager"))
			# Creator/live-flag filtering happens first: never select a removed option.
			filtered = _task_actions(
				task, transitions=[task.available_workflow_transitions[-1]], workflow=workflow
			)
			self.assertTrue(filtered[0]["action_link"].endswith("director"))
		self.assertEqual(task.available_workflow_transitions, before)

	def test_distinct_targets_conditions_comments_and_multivote_choices_are_preserved(self):
		from dinext_common.workflow_approval.notifications import _task_actions

		for variant in ("target", "condition", "comment", "all", "unknown"):
			with self.subTest(variant=variant):
				task, workflow = self.choices()
				if variant == "target":
					task.available_workflow_transitions[-1].next_state = "Draft"
				elif variant == "condition":
					workflow.transitions[-1].condition = "doc.budget > 1000"
				elif variant == "comment":
					task.available_workflow_transitions[-1].comment_is_required = 1
				elif variant == "all":
					for row in task.available_workflow_transitions[1:]:
						row.policy, row.threshold = "All", 2
				else:
					workflow.transitions = []
				with patch(
					"dinext_common.workflow_approval.signed_links.get_task_action_url",
					return_value="/preview_action",
				):
					self.assertEqual(len(_task_actions(task, workflow=workflow)), 3)

	def hours_context(self):
		context = self.fixture.timesheets()
		position = context["rows"][0]
		position.update(
			hours=8,
			hours_details=[
				dict(hours=2, description="тестирование"),
				dict(hours=3.5, description="доработка"),
				dict(hours=2.5, description="документация"),
				dict(hours=0, description="неиспользованный день"),
			],
		)
		context["rows"] = [position]
		return context

	def test_timesheet_digest_explains_fractional_hours_and_comments(self):
		_subject, _message, soup = self.fixture.native_message(
			"Dinext Timesheet Workflow Digest", self.hours_context()
		)
		self.assertIn(
			"Часы: 8 (2 ч. — тестирование, 3,5 ч. — доработка, 2,5 ч. — документация)",
			soup.get_text(" ", strip=True),
		)
		self.assertNotIn("неиспользованный день", soup.get_text())

	def test_single_timesheet_approval_also_explains_hours(self):
		context = self.fixture.context()
		position = self.hours_context()["rows"][0]
		context.update(
			timesheet_link=position["link"], hours=position["hours"], hours_details=position["hours_details"]
		)
		_subject, _message, soup = self.fixture.native_message("Dinext Workflow Action", context)
		self.assertIn("Часы: 8 (2 ч.", soup.get_text(" ", strip=True))

	def test_hour_details_are_localized_and_plain_text(self):
		context = self.hours_context()
		context["rows"][0]["hours_details"] = [
			dict(hours=3.5, description="<script>testing</script>"),
			dict(hours=4.5, description=""),
		]
		frappe.db.set_value("User", self.fixture.user, "language", "en")
		_subject, _message, soup = self.fixture.native_message("Dinext Timesheet Workflow Digest", context)
		self.assertIn("Hours: 8 (3.5 h — <script>testing</script>, 4.5 h)", soup.get_text(" ", strip=True))
		self.assertIsNone(soup.find("script"))

	def test_absent_details_and_manager_digest_do_not_invent_or_expose_a_breakdown(self):
		context = self.hours_context()
		_subject, _message, soup = self.fixture.native_message(
			"Dinext Timesheet Workflow Deadline Digest", context
		)
		self.assertNotIn("тестирование", soup.get_text())
		context["rows"][0]["hours_details"] = []
		_subject, _message, soup = self.fixture.native_message("Dinext Timesheet Workflow Digest", context)
		self.assertNotIn("8 ()", soup.get_text())
