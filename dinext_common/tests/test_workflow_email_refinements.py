"""Recipient-visible mail regressions from the November acceptance screenshots."""

from copy import deepcopy
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

import frappe
from bs4 import BeautifulSoup
from frappe.tests.utils import FrappeTestCase


class TestWorkflowEmailRefinements(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.users = []
		for first, last in (("Иван", "Петров"), ("Мария", "Соколова"), ("Алексей", "Смирнов")):
			user = "email-layout-" + frappe.generate_hash(length=10) + "@example.test"
			frappe.get_doc(
				dict(
					doctype="User",
					email=user,
					first_name=first,
					last_name=last,
					language="ru",
					send_welcome_email=0,
				)
			).insert(ignore_permissions=True)
			self.users.append(user)
		self.user = self.users[0]

	def context(self):
		actions = [
			dict(
				action_name=name,
				action_link="http://localhost:8000/preview_action?choice=" + name,
				style=style,
				icon=icon,
			)
			for name, style, icon in (("Approve", "success", "check"), ("Reject", "danger", "close"))
		]
		return dict(
			doc=dict(
				doctype="Project",
				name="PRJ-2026-0042",
				owner=self.user,
				project_name="Внедрение системы управления проектами",
			),
			document_link="http://localhost:8000/app/project/PRJ-2026-0042",
			workflow_state="На согласовании",
			actions=actions,
			entry_context=dict(
				comments=[
					dict(
						actor=self.users[1],
						text="Уточните бюджет этапа внедрения и сроки обучения сотрудников.",
						at="2026-11-10 10:00:00",
					)
				]
			),
			rows=[
				dict(
					doctype="Project",
					name="PRJ-2026-0042",
					title="Внедрение системы управления проектами",
					link="http://localhost:8000/app/project/PRJ-2026-0042",
					actions=deepcopy(actions),
					due="2026-11-09 10:00:00",
					overdue_hours=24,
					approver=self.users[1],
				)
			],
		)

	def native_message(self, name, context=None):
		from frappe.email.email_body import get_email
		from frappe.utils.jinja import get_email_from_template

		from dinext_common.workflow_approval.email_presentation import language_context, render_standard
		from dinext_common.workflow_approval.notifications import _sendmail_for_user

		subject, body = render_standard(name, context or self.context(), self.user)
		# The only replaced boundary is outbound transport; native MIME, footer and CSS run.
		with patch.object(frappe, "sendmail") as transport:
			_sendmail_for_user(self.user, subject=subject, message=body, recipients=[self.user])
		kwargs = transport.call_args.kwargs
		with language_context(self.user):
			html, plain = get_email_from_template(kwargs["template"], kwargs["args"])
			message = get_email(
				recipients=[self.user],
				sender="Dinext <ikhmel@dinext.ru>",
				subject=subject,
				content=html,
				text_content=plain,
				inline_images=kwargs["inline_images"],
			)
			parsed = BytesParser(policy=policy.default).parsebytes(message.as_string().encode())
		return (
			subject,
			parsed,
			BeautifulSoup(parsed.get_body(preferencelist=("html",)).get_content(), "html.parser"),
		)

	def test_digest_subject_identifies_project_and_localized_state(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		subject, _body = render_standard("Dinext Workflow Digest", self.context(), self.user)
		self.assertIn("Проект: 1 — На согласовании", subject)
		self.assertNotIn("Документы", subject)
		self.assertNotIn("Project", subject)
		self.assertNotIn("PRJ-2026-0042", subject)

	def test_missing_business_title_never_exposes_opaque_record_id(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		context = self.context()
		context["doc"].pop("project_name")
		context["doc"]["name"] = "a4f38c01967d2e50"
		subject, body = render_standard("Dinext Workflow Action", context, self.user)
		self.assertNotIn("a4f38c01967d2e50", subject)
		self.assertNotIn("a4f38c01967d2e50", BeautifulSoup(body, "html.parser").get_text())
		self.assertIn("Проект", subject)

	def test_subject_uses_english_recipient_language_for_russian_state(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		frappe.db.set_value("User", self.user, "language", "en")
		subject, _body = render_standard("Dinext Workflow Digest", self.context(), self.user)
		self.assertIn("Project: 1", subject)
		self.assertIn("Pending Approval", subject)
		self.assertNotIn("На согласовании", subject)

	def test_native_mime_has_one_footer_logo_and_no_header_logo(self):
		_subject, message, soup = self.native_message("Dinext Workflow Action")
		self.assertFalse(soup.h1.find_parent("td").find("img"))
		logos = soup.select('[data-dinext-email-footer="1"] img[alt="Dinext"]')
		self.assertEqual(len(logos), 1)
		self.assertEqual(len(soup.select('img[alt="Dinext"]')), 1)
		self.assertTrue(logos[0]["src"].startswith("cid:"))
		self.assertTrue(
			any(
				str(part.get("Content-ID") or "").strip("<>") == logos[0]["src"].removeprefix("cid:")
				for part in message.walk()
			)
		)

	def test_native_action_buttons_have_independent_padded_cells_and_separation(self):
		_subject, _message, soup = self.native_message("Dinext Workflow Action")
		buttons = soup.select('a[href*="preview_action"]')
		self.assertEqual(len(buttons), 2)
		for link in buttons:
			cell = link.find_parent("td")
			self.assertEqual(len(cell.select('a[href*="preview_action"]')), 1)
			self.assertRegex(cell.get("style", ""), r"padding:\s*(?:8|10|12)px")
			self.assertRegex(cell.parent.parent.find_parent("td").get("style", ""), r"padding:[^;]*(?:6|8)px")

	def test_overdue_header_is_more_prominent_than_neutral_digest(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		_, normal = render_standard("Dinext Workflow Digest", self.context(), self.user)
		_, overdue = render_standard("Dinext Workflow Deadline Digest", self.context(), self.user)
		normal_header = BeautifulSoup(normal, "html.parser").h1.find_parent("td")
		overdue_header = BeautifulSoup(overdue, "html.parser").h1.find_parent("td")
		self.assertNotEqual(normal_header.get("style"), overdue_header.get("style"))
		self.assertIn("Нарушен срок", overdue_header.get_text())

	def timesheets(self):
		context = self.context()
		context["workflow_state"] = "Pending Approval"
		context["rows"] = []
		for ordinal, approver, due, overdue in (
			(2, self.users[1], "2026-11-09 10:00:00", 24),
			(5, self.users[1], "2026-11-10 10:00:00", 12),
			(5, self.users[2], "2026-11-09 15:00:00", 19),
		):
			context["rows"].append(
				dict(
					doctype="User Timesheet Position",
					name="position-" + str(ordinal),
					title="Позиция таймшита",
					actions=deepcopy(context["actions"]),
					timesheet_name="Таймшит за 2–8 ноября",
					author=self.user,
					period_from="2026-11-02",
					period_to="2026-11-08",
					position_name="position-" + str(ordinal),
					ordinal=ordinal,
					position_label=f"№ {ordinal} — Модернизация склада — Анализ требований — Архитектор решения",
					hours=8,
					link="http://localhost:8000/app/user-timesheet/november-week-45",
					approver=approver,
					due=due,
					overdue_hours=overdue,
				)
			)
		return context

	def test_timesheet_overdue_has_one_parent_with_unique_approvers_and_earliest_deadlines(self):
		from dinext_common.workflow_approval.email_presentation import (
			language_context,
			prepare_context,
			render_standard,
		)

		context = self.timesheets()
		with language_context(self.user):
			prepared = prepare_context("Dinext Timesheet Workflow Deadline Digest", context, self.user)
		self.assertEqual(len(prepared.get("overdue_timesheets", [])), 1)
		sheet = prepared["overdue_timesheets"][0]
		self.assertEqual(len(sheet["overdues"]), 2)
		maria = next(row for row in sheet["overdues"] if row["approver_name"] == "Мария Соколова")
		self.assertEqual(str(maria["due"]), "2026-11-09 10:00:00")
		self.assertEqual(float(maria["overdue_hours"]), 24)
		subject, body = render_standard("Dinext Timesheet Workflow Deadline Digest", context, self.user)
		soup = BeautifulSoup(body, "html.parser")
		self.assertEqual(len(soup.select('a[href$="/november-week-45"]')), 1)
		self.assertNotIn("№ 2", soup.get_text())
		self.assertNotIn("Архитектор решения", soup.get_text())
		self.assertNotIn("Позиции", subject)
		self.assertNotIn("preview_action", body)
		self.assertFalse(any(h.get_text(strip=True) == "Иван Петров" for h in soup.find_all("h2")))

	def test_ordinary_timesheet_digest_retains_canonical_position_labels(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		_subject, body = render_standard("Dinext Timesheet Workflow Digest", self.timesheets(), self.user)
		self.assertIn("№ 2", body)
		self.assertIn("№ 5", body)
		self.assertIn("Архитектор решения", body)
		self.assertIn("preview_action", body)

	def test_timesheet_correction_header_names_parent_type_not_internal_position(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		context = self.timesheets()
		context.update(
			doc=dict(doctype="User Timesheet Position", name="position-2", owner=self.user),
			rows=[],
			workflow_state="Rejected",
			timesheet_link=context["rows"][0]["link"],
			timesheet_period_from="2026-11-02",
			timesheet_period_to="2026-11-08",
			position_label=context["rows"][0]["position_label"],
		)
		_subject, body = render_standard("Dinext Timesheet Workflow Correction", context, self.user)
		self.assertIn("Таймшит: 1", BeautifulSoup(body, "html.parser").h1.find_parent("td").get_text())
		self.assertNotIn("position-2", BeautifulSoup(body, "html.parser").get_text())

	def test_native_footer_has_its_own_readable_surface_on_dark_background(self):
		_subject, _message, soup = self.native_message("Dinext Workflow Digest")
		footer = soup.select_one(".email-footer-container")
		self.assertIn("background-color:#f3f5f8", footer["style"].replace(" ", ""))
