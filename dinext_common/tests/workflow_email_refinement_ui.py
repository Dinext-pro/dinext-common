"""Native-MIME browser previews with representative business names, no mail transport."""

import base64
from datetime import timedelta

import frappe

from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_user

USERS = (
	("cy.email.layout.author@example.com", "Иван Петров"),
	("cy.email.layout.reviewer@example.com", "Мария Соколова"),
	("cy.email.layout.finance@example.com", "Алексей Смирнов"),
)


def guard():
	frappe.only_for("System Manager")
	if frappe.local.site != "localhost" and not frappe.conf.get("workflow_email_test_site"):
		raise frappe.PermissionError


TIMESHEETS = ("CY-TS-WORKSPACE-01", "CY-TS-WORKSPACE-02")


def seed():
	guard()
	cleanup()
	for index, (user, name) in enumerate(USERS):
		roles = ["Desk User", "Dinext_User", "Dinext_Worker"]
		if index < 2:
			roles += ["System Manager", "Dinext_UT_Full_Access"]
		_ensure_user(user, name, roles)
		frappe.db.set_value("User", user, "language", "en" if index == 1 else "ru")
	# Representative overdue drafts make native bar/tooltip acceptance deterministic.
	today = frappe.utils.getdate(frappe.utils.nowdate())
	start = today - timedelta(days=today.weekday() + 7)
	options = frappe.get_meta("User Timesheet").get_field("ut_status").options.splitlines()
	for name, (user, full_name) in zip(TIMESHEETS, USERS):
		frappe.get_doc(
			dict(
				doctype="User Timesheet",
				creation=frappe.utils.now_datetime(),
				name=name,
				owner=user,
				timesheet_from=user,
				timesheet_from_name=full_name,
				ts_valid_from=start,
				ts_valid_for=start + timedelta(days=6),
				ts_date_of_dispatch=today - timedelta(days=1),
				ut_status="Draft" if "Draft" in options else "Черновик",
			)
		).db_insert()

	return dict(
		editor=USERS[0][0],
		password=PASSWORD,
		locales=[dict(user=USERS[0][0], language="ru"), dict(user=USERS[1][0], language="en")],
		ordinary_user=USERS[2][0],
	)


def cleanup():
	guard()
	for name, (user, _full_name) in zip(TIMESHEETS, USERS):
		if frappe.db.exists("User Timesheet", {"name": name, "timesheet_from": user}):
			frappe.delete_doc("User Timesheet", name, force=True, ignore_permissions=True)
	for user, _name in USERS:
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	return dict(cleaned=True)


def previews():
	guard()
	from unittest.mock import patch

	from dinext_common.tests.test_workflow_email_refinements import TestWorkflowEmailRefinements
	from dinext_common.tests.test_workflow_mail_outlook import TestWorkflowMailOutlook
	from dinext_common.workflow_approval.email_templates import default_email_templates
	from dinext_common.workflow_approval.notifications import _task_actions

	fixture = TestWorkflowEmailRefinements()
	fixture.users = [user for user, _name in USERS]
	fixture.user = fixture.users[0]
	old_language = frappe.db.get_value("User", fixture.user, "language")
	result = []
	try:
		for language in ("ru", "en", ""):
			frappe.db.set_value("User", fixture.user, "language", language)
			for name in default_email_templates():
				context = fixture.timesheets() if "Timesheet" in name else fixture.context()
				if "Timesheet" in name:
					comments = (
						("testing", "development", "documentation")
						if language == "en"
						else ("тестирование", "доработка", "документация")
					)
					for row in context["rows"]:
						row["hours_details"] = [
							dict(hours=hours, description=text)
							for hours, text in zip((2, 3.5, 2.5), comments, strict=True)
						]
				else:
					# The production projector receives three role options and emits two choices.
					task, workflow = TestWorkflowMailOutlook.choices()
					with patch(
						"dinext_common.workflow_approval.signed_links.get_task_action_url",
						side_effect=lambda task, row: (
							"http://localhost:8000/preview_action?choice=" + row.transition_uuid
						),
					):
						actions = _task_actions(task, workflow=workflow)
					context["actions"] = actions
					for row in context["rows"]:
						row["actions"] = actions
				if "Correction" in name:
					context["workflow_state"] = "Rejected"
				if "Timesheet" in name:
					context.update(
						doc=dict(doctype="User Timesheet Position", name="position-2", owner=fixture.user),
						timesheet_link=context["rows"][0]["link"],
						timesheet_period_from="2026-11-02",
						timesheet_period_to="2026-11-08",
						position_label=context["rows"][0]["position_label"],
					)
					source_context = dict(
						context["entry_context"]["comments"][0],
						text="Уточните часы анализа требований: часть встречи относится к другому проекту.",
					)
					context["entry_context"] = dict(comments=[source_context])
				subject, message, soup = fixture.native_message(name, context)
				for part in message.walk():
					if part.get("Content-ID"):
						cid = str(part["Content-ID"]).strip("<>")
						data = (
							"data:"
							+ part.get_content_type()
							+ ";base64,"
							+ base64.b64encode(part.get_payload(decode=True)).decode()
						)
						for image in soup.find_all("img", src="cid:" + cid):
							image["src"] = data
				result.append(dict(name=name, language=language or "system", subject=subject, html=str(soup)))
	finally:
		frappe.db.set_value("User", fixture.user, "language", old_language)
	return result
