"""Local-only fixture for deadline and branded-email browser acceptance."""

from copy import deepcopy

import frappe

from dinext_common.tests import workflow_email_ui as base

ORDINARY_USER = "cy.workflow.deadline.worker@example.com"

LOCALE_USERS = (
	("cy.workflow.deadline.en@example.com", "en"),
	("cy.workflow.deadline.system@example.com", ""),
)


def seed():
	cleanup()
	result = base.seed()
	from dinext_common.tests.ui_test_helpers import _ensure_user

	roles = ["System Manager", "Desk User", "Dinext_User", "Dinext_UT_Full_Access", base.ROLE]
	_ensure_user(base.EDITOR, "Workflow Email Editor", roles)
	frappe.db.set_value("User", base.EDITOR, "language", "ru", update_modified=False)
	for user, language in LOCALE_USERS:
		_ensure_user(user, "Workflow Language Preview", roles)
		frappe.db.set_value("User", user, "language", language)
	_ensure_user(
		ORDINARY_USER, "Workflow Ordinary Approver", ["Desk User", "Dinext_User", "Dinext_Worker", base.ROLE]
	)
	frappe.db.set_value("User", ORDINARY_USER, "language", "ru")
	result["ordinary_user"] = ORDINARY_USER
	result["locale_users"] = [
		dict(user=user, language=language or "system") for user, language in LOCALE_USERS
	]
	result["system_ui_language"] = frappe.db.get_default("lang") or "en"
	workflow = frappe.get_doc("Workflow", result["workflow"])
	workflow.append("states", {"state": "Approved", "doc_status": "0", "allow_edit": "All"})
	workflow.append(
		"states", {"state": "Draft", "doc_status": "0", "allow_edit": "All", "is_optional_state": 1}
	)
	workflow.append(
		"transitions",
		{
			"state": "Editing",
			"next_state": "Approved",
			"action": "Approve",
			"allowed": "System Manager",
			"custom_deadline_enabled": 1,
			"custom_deadline_value": 3,
			"custom_deadline_unit": "Working Days",
			"custom_deadline_recipient_type": "Worker Group Manager",
			"custom_deadline_email_mode": "Digest",
			"custom_deadline_interval_unit": "Days",
			"custom_deadline_interval_value": 1,
			"custom_deadline_send_times": "17:00, 08:00, 08:00",
			"custom_deadline_email_template": "Dinext Timesheet Workflow Deadline Digest",
		},
	)
	workflow.append(
		"transitions",
		{
			"state": "Rejected",
			"next_state": "Draft",
			"action": "Edit",
			"allowed": "System Manager",
		},
	)
	workflow.save(ignore_permissions=True)
	return result


def cleanup():
	base._guard()
	for user in [ORDINARY_USER, *(user for user, _language in LOCALE_USERS)]:
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	return base.cleanup()


def diagnostics():
	"""Real report formatting over a controlled diagnostic dataset; no source writes."""
	from copy import deepcopy
	from unittest.mock import patch

	from frappe.translate import print_language

	from dinext_common.workflow_approval.deadlines import report

	base._guard()
	rows = [dict(
		reference_doctype="Application For Leave", reference_name=f"AFL-2026-00{11 + i}",
		source_title=title, workflow="AFL Workflow", workflow_state="Pending Approval",
		approver=base.EDITOR, discipline_status="Error", deadline_error=error,
	) for i, (title, error) in enumerate([
		("Плановый отпуск: 23-27 ноября", "Original assignment time is unknown"),
		("Плановое отсутствие — 30 ноября", "Worker is missing for user marina.sokolova@example.com"),
	])]
	result = {}
	for language in ("ru", "en"):
		with print_language(language), patch.object(report, "metrics", return_value=dict(
			rows=[], all_rows=deepcopy(rows), on_time_percent=None, open_overdue=0, completed_late=0, errors=2,
		)), patch.object(report, "full_name", return_value="Елена Морозова"):
			columns, data, message, chart, summary = report.execute()
			result[language] = dict(columns=columns, result=data, message=message, chart=chart,
				report_summary=summary, add_total_row=0)
	return result


def previews():
	base._guard()
	from unittest.mock import patch

	from frappe.email.email_body import get_formatted_html
	from frappe.utils.jinja import get_email_from_template

	from dinext_common.tests.test_workflow_email_presentation import TestWorkflowEmailPresentation
	from dinext_common.workflow_approval.email_presentation import language_context, render_standard
	from dinext_common.workflow_approval.email_templates import default_email_templates
	from dinext_common.workflow_approval.notifications import _sendmail_for_user

	fixture = TestWorkflowEmailPresentation()
	fixture.user = base.EDITOR
	context = fixture.context()
	context["doc"]["project_name"] = (
		"Развитие корпоративной системы планирования и управления проектами / Enterprise planning and project management"
	)
	generic = deepcopy(context)
	for row in context["rows"]:
		row.update(
			title=context["doc"]["project_name"],
			author=base.EDITOR,
			timesheet_name="TS-PREVIEW",
			period_from="2026-11-01",
			period_to="2026-11-30",
			position_name="POS-5",
			ordinal=5,
			position_label="№ 5 — Корпоративная система — Проектирование и согласование архитектуры решения — Руководитель проекта",
			hours=12,
			link="http://localhost:8000/app/user-timesheet/TS-PREVIEW",
		)
	context.update(
		timesheet_link=context["rows"][0]["link"],
		timesheet_title="Таймшит за ноябрь",
		position_label=context["rows"][0]["position_label"],
	)
	result = []
	previous = frappe.db.get_value("User", base.EDITOR, "language")
	try:
		for language in ("ru", "en", ""):
			frappe.db.set_value("User", base.EDITOR, "language", language, update_modified=False)
			for name in default_email_templates():
				subject, body = render_standard(
					name, context if "Timesheet" in name else generic, base.EDITOR
				)
				with patch.object(frappe, "sendmail") as send:
					_sendmail_for_user(base.EDITOR, recipients=[base.EDITOR], subject=subject, message=body)
				kwargs = send.call_args.kwargs
				with language_context(base.EDITOR):
					html, text = get_email_from_template(kwargs["template"], kwargs["args"])
					html = get_formatted_html(subject, html, sender="ikhmel@dinext.ru", with_container=False)
				# Browser uses the same bytes as CID images in the actual MIME transport.
				html = html.replace('embed="assets/', 'src="/assets/')
				result.append(dict(name=name, language=language or "system", html=html, subject=subject))
	finally:
		frappe.db.set_value("User", base.EDITOR, "language", previous, update_modified=False)
	return result
