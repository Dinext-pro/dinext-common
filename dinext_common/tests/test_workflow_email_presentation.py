from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkflowEmailPresentation(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.user = "mail-design-" + frappe.generate_hash(length=8) + "@example.test"
		frappe.get_doc(
			dict(
				doctype="User",
				email=self.user,
				first_name="Иван",
				last_name="Иванов",
				language="ru",
				send_welcome_email=0,
			)
		).insert(ignore_permissions=True)

	def context(self):
		return dict(
			doc=dict(doctype="Project", name="PROJ-001", project_name="Проект <проверка>"),
			document_link="http://localhost:8000/app/project/PROJ-001",
			workflow_state="Pending Approval",
			entry_context=dict(
				comments=[dict(actor=self.user, text="Исправьте <сумму>", at="2026-11-09 10:00:00")]
			),
			actions=[
				dict(
					action_name="Approve",
					action_link="http://localhost:8000/preview_action",
					style="success",
					icon="check",
				)
			],
			rows=[
				dict(
					doctype="Project",
					name="PROJ-001",
					title="Проект <проверка>",
					link="http://localhost:8000/app/project/PROJ-001",
					count=1,
					actions=[
						dict(
							action_name="Approve",
							action_link="http://localhost:8000/preview_action",
							style="success",
							icon="check",
						)
					],
					due="2026-11-08 10:00:00",
					overdue_hours=24,
					approver_name="Иван Иванов",
				)
			],
		)

	def test_approval_has_branded_layout_and_styled_individual_action(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		subject, body = render_standard("Dinext Workflow Digest", self.context(), self.user)
		self.assertIn("Ожидающие согласования", body)
		self.assertIn("preview_action", body)
		self.assertIn("#18794e", body)
		self.assertIn("Проект &lt;проверка&gt;", body)
		self.assertNotIn("Pending workflow approvals", body)

	def test_blank_recipient_language_uses_system_setting_despite_ambient_and_legacy_language(self):
		from frappe.translate import print_language
		from dinext_common.workflow_approval.email_presentation import render_standard

		frappe.db.set_value("User", self.user, "language", "")
		frappe.db.set_single_value("System Settings", "language", "ru")
		original = frappe.db.get_default
		with patch.object(frappe.db, "get_default", side_effect=lambda key, *args, **kwargs:
			"en" if key == "lang" else original(key, *args, **kwargs)), print_language("en"):
			subject, body = render_standard("Dinext Workflow Action", self.context(), self.user)
		self.assertIn("Требуется согласование", subject)
		self.assertIn("Документ ожидает вашего решения.", body)

	def test_correction_has_full_name_comment_and_no_transition_action(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		subject, body = render_standard("Dinext Workflow Correction", self.context(), self.user)
		self.assertIn("Иван Иванов", body)
		self.assertIn("Исправьте &lt;сумму&gt;", body)
		self.assertNotIn("preview_action", body)

	def test_manager_overdue_digest_never_has_actions_even_if_supplied(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		subject, body = render_standard("Dinext Workflow Deadline Digest", self.context(), self.user)
		self.assertNotIn("preview_action", body)
		self.assertIn("Иван Иванов", body)

	def test_footer_keeps_signature_and_localizes_once(self):
		from dinext_common.workflow_approval.email_presentation import language_context

		with language_context(self.user):
			body = frappe.render_template(
				"templates/emails/email_footer.html",
				dict(
					email_account_footer="Account signature",
					default_mail_footer=[
						'<span>Sent via <a href="https://frappe.io/erpnext?source=via_email_footer">ERPNext</a></span>'
					],
				),
			)
		self.assertIn("Account signature", body)
		self.assertEqual(body.count('href="https://dinext.ru"'), 1)
		self.assertIn("Настройки уведомлений", body)
		self.assertNotIn("Sent via", body)

	def test_timesheets_group_by_author_parent_and_deduplicate_positions_and_hours(self):
		from dinext_common.workflow_approval.email_presentation import (
			language_context,
			prepare_context,
			render_standard,
		)

		context = self.context()
		rows = []
		for number, hours in [(2, 8), (5, 4), (5, 4)]:
			rows.append(
				dict(
					context["rows"][0],
					timesheet_name="TS-1",
					author=self.user,
					period_from="2026-11-01",
					period_to="2026-11-30",
					position_name="POS-" + str(number),
					ordinal=number,
					position_label=f"№ {number} — Проект — Задача — Роль",
					hours=hours,
					link="http://localhost:8000/app/user-timesheet/TS-1",
				)
			)
		context["rows"] = rows
		with language_context(self.user):
			prepared = prepare_context("Dinext Timesheet Workflow Digest", context, self.user)
		sheet = prepared["author_groups"][0]["sheets"][0]
		self.assertEqual(sheet["count"], 2)
		self.assertEqual(sheet["hours"], 12)
		subject, body = render_standard("Dinext Timesheet Workflow Deadline Digest", context, self.user)
		self.assertNotIn("№ 2", body)
		self.assertNotIn("№ 5", body)
		self.assertIn("app/user-timesheet/TS-1", body)
		self.assertNotIn("preview_action", body)

	def test_transport_receives_inline_logo_and_web_ui_icon_bytes(self):
		from dinext_common.workflow_approval.email_presentation import render_standard
		from dinext_common.workflow_approval.notifications import _sendmail_for_user

		subject, body = render_standard("Dinext Workflow Action", self.context(), self.user)
		with patch.object(frappe, "sendmail") as boundary:
			_sendmail_for_user(self.user, subject=subject, message=body, recipients=[self.user])
		assets = boundary.call_args.kwargs["inline_images"]
		self.assertEqual({item["filename"].split("/")[-1] for item in assets}, {"dinext.png", "check.png"})
		self.assertTrue(all(item["filecontent"].startswith(b"\x89PNG") for item in assets))
		from frappe.utils.jinja import get_email_from_template

		kwargs = boundary.call_args.kwargs
		html, text = get_email_from_template(kwargs["template"], kwargs["args"])
		self.assertIn("https://dinext.ru", text)
		self.assertIn("open_settings", text)

	def test_english_recipient_gets_english_labels_for_russian_stored_states_and_actions(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		frappe.db.set_value("User", self.user, "language", "en")
		context = self.context()
		context["workflow_state"] = "На согласовании"
		context["rows"][0]["actions"][0]["action_name"] = "Согласовано"
		subject, body = render_standard("Dinext Workflow Digest", context, self.user)
		self.assertIn("Pending Approval", body)
		self.assertIn("Approve", body)
		self.assertNotIn("На согласовании", body)
		self.assertNotIn("Согласовано", body)
