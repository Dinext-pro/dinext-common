"""Metadata definitions and validation for parallel Workflow approvals."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import uuid4

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from dinext_common.workflow_approval.policy import normalize_policy, policy_from_legacy_flag

EMAIL_ENABLED_CONDITION = "eval:doc.send_email_alert"
GROUPED_EMAIL_CONDITION = (
	"eval:doc.send_email_alert && doc.custom_group_workflow_action_emails"
)
IMMEDIATE_EMAIL_CONDITION = (
	"eval:doc.send_email_alert && !doc.custom_group_workflow_action_emails"
)
DAILY_SEND_TIME_CONDITION = (
	"eval:doc.send_email_alert && doc.custom_group_workflow_action_emails"
	" && doc.custom_group_interval_unit=='Days'"
)


def get_workflow_approval_custom_fields() -> dict[str, list[dict[str, Any]]]:
	"""Return source definitions for Custom Fields owned by this capability."""
	custom_fields = {
		"Workflow Action Master": [
			{
				"fieldname": "custom_icon",
				"fieldtype": "Data",
				"insert_after": "workflow_action_name",
				"label": "Icon",
				"description": "Frappe icon name, for example: check, close, edit",
			},
		],
		"Workflow Transition": [
			{
				"fieldname": "custom_parallel_approval_section",
				"fieldtype": "Section Break",
				"insert_after": "send_email_to_creator",
				"label": "Parallel Approval",
			},
			{
				"fieldname": "custom_transition_uuid",
				"fieldtype": "Data",
				"hidden": 1,
				"insert_after": "custom_parallel_approval_section",
				"label": "Transition UUID",
				"read_only": 1,
			},
			{
				"default": "Any",
				"fieldname": "custom_parallel_approval_policy",
				"fieldtype": "Select",
				"in_list_view": 1,
				"insert_after": "custom_transition_uuid",
				"label": "Approval Policy",
				"options": "Any\nAll\nMinimum",
			},
			{
				"depends_on": "eval:doc.custom_parallel_approval_policy=='Minimum'",
				"fieldname": "custom_minimum_approvals",
				"fieldtype": "Int",
				"insert_after": "custom_parallel_approval_policy",
				"label": "Minimum Approvals",
				"mandatory_depends_on": "eval:doc.custom_parallel_approval_policy=='Minimum'",
				"non_negative": 1,
			},
			{
				"default": "0",
				"fieldname": "custom_comment_is_required",
				"fieldtype": "Check",
				"insert_after": "custom_minimum_approvals",
				"label": "Comment Is Required",
			},
			{
				"default": "0",
				"fieldname": "custom_reset_on_change",
				"fieldtype": "Check",
				"insert_after": "custom_comment_is_required",
				"label": "Reset Approvals On Change",
			},
			{
				"default": "0",
				"fieldname": "custom_auto_complete_unchanged",
				"fieldtype": "Check",
				"insert_after": "custom_reset_on_change",
				"label": "Auto Complete Unchanged",
			},
			{
				"fieldname": "custom_all_users_with_role",
				"fieldtype": "Check",
				"hidden": 1,
				"insert_after": "custom_auto_complete_unchanged",
				"label": "All Users",
				"read_only": 1,
			},
		],
		"Workflow": [
			{
				"fieldname": "custom_approval_fingerprint_section",
				"fieldtype": "Section Break",
				"insert_after": "workflow_state_field",
				"label": "Approval Content Snapshot",
			},
			{
				"fieldname": "custom_fingerprint_excluded_fields",
				"fieldtype": "Table",
				"insert_after": "custom_approval_fingerprint_section",
				"label": "Fields Excluded from Snapshot",
				"options": "Workflow Fingerprint Exclusion",
				"description": "These fields are excluded for all transitions of this Workflow, in addition to application hooks and system fields.",
			},
			{
				"depends_on": EMAIL_ENABLED_CONDITION,
				"fieldname": "custom_workflow_approval_email_section",
				"fieldtype": "Section Break",
				"insert_after": "send_email_alert",
				"label": "Workflow Approval Email",
			},
			{
				"default": "0",
				"depends_on": EMAIL_ENABLED_CONDITION,
				"fieldname": "custom_group_workflow_action_emails",
				"fieldtype": "Check",
				"insert_after": "custom_workflow_approval_email_section",
				"label": "Group Workflow Action Emails",
			},
			{
				"depends_on": IMMEDIATE_EMAIL_CONDITION,
				"fieldname": "custom_workflow_action_email_template",
				"fieldtype": "Link",
				"insert_after": "custom_group_workflow_action_emails",
				"label": "Workflow Action Email Template",
				"options": "Email Template",
			},
			{
				"default": "0",
				"depends_on": IMMEDIATE_EMAIL_CONDITION,
				"fieldname": "custom_attach_document_pdf",
				"fieldtype": "Check",
				"insert_after": "custom_workflow_action_email_template",
				"label": "Attach Document PDF",
			},
			{
				"depends_on": GROUPED_EMAIL_CONDITION,
				"fieldname": "custom_group_interval_unit",
				"fieldtype": "Select",
				"insert_after": "custom_attach_document_pdf",
				"label": "Digest Interval Unit",
				"mandatory_depends_on": GROUPED_EMAIL_CONDITION,
				"options": "Hours\nDays",
			},
			{
				"depends_on": GROUPED_EMAIL_CONDITION,
				"fieldname": "custom_group_interval_value",
				"fieldtype": "Int",
				"insert_after": "custom_group_interval_unit",
				"label": "Digest Interval",
				"mandatory_depends_on": GROUPED_EMAIL_CONDITION,
				"non_negative": 1,
			},
			{
				"depends_on": DAILY_SEND_TIME_CONDITION,
				"fieldname": "custom_group_send_time",
				"fieldtype": "Time",
				"insert_after": "custom_group_interval_value",
				"label": "Digest Send Time",
				"mandatory_depends_on": DAILY_SEND_TIME_CONDITION,
			},
			{
				"depends_on": GROUPED_EMAIL_CONDITION,
				"fieldname": "custom_group_email_template",
				"fieldtype": "Link",
				"insert_after": "custom_group_send_time",
				"label": "Digest Email Template",
				"options": "Email Template",
			},
			{
				"depends_on": GROUPED_EMAIL_CONDITION,
				"fieldname": "custom_group_schedule_anchor",
				"fieldtype": "Datetime",
				"insert_after": "custom_group_email_template",
				"label": "Digest Schedule Anchor",
				"read_only": 1,
			},
			{
				"fieldname": "custom_approval_monitoring_section",
				"fieldtype": "Section Break",
				"insert_after": "custom_group_schedule_anchor",
				"label": "Approval Monitoring",
			},
			{
				"fieldname": "custom_approval_monitor_roles",
				"fieldtype": "Table",
				"insert_after": "custom_approval_monitoring_section",
				"label": "Approval Monitor Roles",
				"options": "Has Role",
			},
		],
		"Workflow Action": [
			{
				"fieldname": "custom_workflow_task",
				"fieldtype": "Link",
				"hidden": 1,
				"insert_after": "user",
				"label": "Workflow Task",
				"options": "Workflow Task",
				"read_only": 1,
			},
			{
				"fieldname": "custom_approval_round_id",
				"fieldtype": "Data",
				"hidden": 1,
				"insert_after": "custom_workflow_task",
				"label": "Approval Round ID",
				"read_only": 1,
			},
			{
				"fieldname": "custom_notification_mode",
				"fieldtype": "Select",
				"hidden": 1,
				"insert_after": "custom_approval_round_id",
				"label": "Notification Mode",
				"options": "Immediate\nDigest",
				"read_only": 1,
			},
			{
				"fieldname": "custom_notification_status",
				"fieldtype": "Select",
				"hidden": 1,
				"insert_after": "custom_notification_mode",
				"label": "Notification Status",
				"options": "Pending\nEnqueued\nSkipped\nFailed",
				"read_only": 1,
			},
			{
				"fieldname": "custom_last_digest_slot",
				"fieldtype": "Datetime",
				"hidden": 1,
				"insert_after": "custom_notification_status",
				"label": "Last Digest Slot",
				"read_only": 1,
			},
			{
				"fieldname": "custom_delivery_key",
				"fieldtype": "Data",
				"hidden": 1,
				"insert_after": "custom_last_digest_slot",
				"label": "Delivery Key",
				"read_only": 1,
			},
		],
	}
	from dinext_common.workflow_approval.email_metadata import extend_email_fields

	extend_email_fields(custom_fields)
	for fields in custom_fields.values():
		for field in fields:
			field.setdefault("module", "Dinext Common")
	return custom_fields


def ensure_workflow_fingerprint_fields() -> None:
	"""Install only the Workflow snapshot editor fields without changing its rows."""
	fields = [
		field
		for field in get_workflow_approval_custom_fields()["Workflow"]
		if field["fieldname"] in {
			"custom_approval_fingerprint_section", "custom_fingerprint_excluded_fields",
		}
	]
	create_custom_fields({"Workflow": fields}, ignore_validate=True, update=True)


def ensure_workflow_approval_custom_fields() -> None:
	"""Create or update Custom Fields before exporting fixtures."""
	create_custom_fields(
		get_workflow_approval_custom_fields(),
		ignore_validate=True,
		update=True,
	)
	from dinext_common.workflow_approval.email_metadata import ensure_state_email_properties

	ensure_state_email_properties()


def ensure_workflow_approval_email_templates() -> None:
	"""Install editable defaults used when a Workflow has no custom template."""
	from dinext_common.workflow_approval.email_templates import default_email_templates, is_known_default_template

	for name, values in default_email_templates().items():
		if frappe.db.exists("Email Template", name):
			existing = frappe.get_doc("Email Template", name)
			if is_known_default_template(name, existing):
				existing.update(values)
				existing.save(ignore_permissions=True)
			continue
		frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": name,
				"use_html": 1,
				**values,
			}
		).insert(ignore_permissions=True)


CHART_NAME = "Pending approvals by document type"
QUEUE_SHORTCUT = "My Approvals"
HISTORY_SHORTCUT = "My Approval History"
MONITORING_SHORTCUT = "Approval Monitoring"
OBSOLETE_APPROVALS_BLOCK = "My Approvals Dashboard"
OPEN_ROUNDS_CARD = "Открытые раунды"
ATTENTION_CARD = "Сбои"
LONGEST_WAIT_CARD = "Самое долгое ожидание"
CONTROL_DECISIONS_CARD = "Решений за 30 дней"
LOAD_COUNT_CHART = "Open tasks by approver"
LOAD_AGE_CHART = "Open task age by approver"
OPEN_ROUNDS_CHART = "Open rounds by document type"
DURATION_CHART = "Approval duration by document type"
LOAD_SHORTCUT = "Approval Load"
DURATION_SHORTCUT = "Approval Duration"
CONTROL_CARDS = (
	(
		OPEN_ROUNDS_CARD,
		"Open Approval Rounds",
		"dinext_common.workflow_approval.api.open_control_round_count",
		"#ECAD4B",
	),
	(
		ATTENTION_CARD,
		"Approval Issues",
		"dinext_common.workflow_approval.api.attention_control_round_count",
		"#CB2929",
	),
	(
		LONGEST_WAIT_CARD,
		"Longest Approval Wait",
		"dinext_common.workflow_approval.api.longest_control_wait",
		"#ED6396",
	),
	(
		CONTROL_DECISIONS_CARD,
		"Decisions in the Last 30 Days",
		"dinext_common.workflow_approval.api.control_decision_count",
		"#449CF0",
	),
)
CONTROL_CHARTS = (
	(LOAD_COUNT_CHART, LOAD_SHORTCUT, '{"chart": "Open count"}'),
	(LOAD_AGE_CHART, LOAD_SHORTCUT, '{"chart": "Open age"}'),
	(
		OPEN_ROUNDS_CHART,
		DURATION_SHORTCUT,
		'{"chart": "Open rounds", "group_by": "Document Type"}',
	),
	(
		DURATION_CHART,
		DURATION_SHORTCUT,
		'{"chart": "Completed duration", "group_by": "Document Type"}',
	),
)


def ensure_workflow_approval_desk_records() -> None:
	"""Install personal cards, the queue chart, and report shortcuts."""
	cards = {
		"My open approvals": (
			"Awaiting My Decision",
			"dinext_common.workflow_approval.api.open_approval_count",
			"#2490EF",
		),
		"Новые сегодня": (
			"New Approvals Today",
			"dinext_common.workflow_approval.api.new_approval_count",
			"#39E4A5",
		),
		"My completed approvals": (
			"My Decisions in the Last 30 Days",
			"dinext_common.workflow_approval.api.completed_approval_count",
			"#29CD42",
		),
		"Автоматически выполнено за 30 дней": (
			"Automatic Decisions in the Last 30 Days",
			"dinext_common.workflow_approval.api.automatic_approval_count",
			"#7C5CFC",
		),
	}
	for name, (label, method, color) in cards.items():
		values = {
			"label": label,
			"method": method,
			"color": color,
			"type": "Custom",
			"document_type": "User Timesheet Position",
			"currency": "",
			"show_percentage_stats": 0,
			"show_full_number": 1,
		}
		if frappe.db.exists("Number Card", name):
			card = frappe.get_doc("Number Card", name)
			card.update(values)
			card.save(ignore_permissions=True)
		else:
			frappe.get_doc(
				{
					"doctype": "Number Card",
					"name": name,
					"is_public": 1,
					"is_standard": 1,
					"module": "Dinext Common",
					**values,
				}
			).insert(ignore_permissions=True)
	for obsolete in (
		"My approvals requiring attention",
		"My Approvals Requiring Attention",
	):
		if frappe.db.exists("Number Card", obsolete):
			frappe.delete_doc("Number Card", obsolete, ignore_permissions=True)

	for name, label, method, color in CONTROL_CARDS:
		_ensure_number_card(name, label, method, color)
	_ensure_pending_approvals_chart()
	_ensure_control_charts()
	_ensure_personal_report_filters()

	if frappe.db.exists("Custom HTML Block", OBSOLETE_APPROVALS_BLOCK):
		frappe.delete_doc(
			"Custom HTML Block",
			OBSOLETE_APPROVALS_BLOCK,
			ignore_permissions=True,
			force=True,
		)


def _ensure_personal_report_filters() -> None:
	"""Upgrade existing reports whose metadata is newer than the shipped export."""
	for name, fieldname, label, fieldtype in (
		(QUEUE_SHORTCUT, "created_on", "Created On", "Date"),
		(HISTORY_SHORTCUT, "completed_since", "Completed Since", "Data"),
		(DURATION_SHORTCUT, "completed_since", "Completed Since", "Data"),
	):
		if not frappe.db.exists("Report", name):
			continue
		report = frappe.get_doc("Report", name)
		if report.prepared_report or not report.disable_prepared_report_automation:
			frappe.db.set_value(
				"Report", name, {"prepared_report": 0, "disable_prepared_report_automation": 1}
			)
		if any(row.fieldname == fieldname for row in report.filters):
			continue
		report.append(
			"filters", {"fieldname": fieldname, "label": label, "fieldtype": fieldtype}
		).db_insert()
		frappe.clear_document_cache("Report", name)

	_ensure_queue_action_filter()


def _ensure_queue_action_filter() -> None:
	"""The personal queue filter must not require workflow setup read access."""
	if not frappe.db.exists("Report", QUEUE_SHORTCUT):
		return
	report = frappe.get_doc("Report", QUEUE_SHORTCUT)
	action = next((row for row in report.filters if row.fieldname == "action"), None)
	if action is None:
		report.append("filters", {"fieldname": "action", "label": "Action", "fieldtype": "Data"}).db_insert()
	elif action.fieldtype != "Data" or action.options:
		frappe.db.set_value("Report Filter", action.name, {"fieldtype": "Data", "options": ""})
	else:
		return
	frappe.clear_document_cache("Report", QUEUE_SHORTCUT)


def _ensure_number_card(name: str, label: str, method: str, color: str) -> None:
	values = {
		"label": label,
		"method": method,
		"color": color,
		"type": "Custom",
		"document_type": "User Timesheet Position",
		"currency": "",
		"show_percentage_stats": 0,
		"show_full_number": 0 if name == LONGEST_WAIT_CARD else 1,
	}
	if frappe.db.exists("Number Card", name):
		card = frappe.get_doc("Number Card", name)
		card.update(values)
		card.save(ignore_permissions=True)
		return
	card = frappe.get_doc(
		{
			"doctype": "Number Card",
			"name": name,
			"is_public": 1,
			"is_standard": 1,
			"module": "Dinext Common",
			**values,
		}
	)
	card.insert(ignore_permissions=True)


def _ensure_control_charts() -> None:
	for chart_name, report_name, filters_json in CONTROL_CHARTS:
		_ensure_report_chart(chart_name, report_name, filters_json)


def _ensure_report_chart(chart_name: str, report_name: str, filters_json: str) -> None:
	values = {
		"chart_name": chart_name,
		"chart_type": "Report",
		"report_name": report_name,
		"use_report_chart": 1,
		"type": "Bar",
		"filters_json": filters_json,
		"is_public": 1,
		"is_standard": 1,
		"module": "Dinext Common",
		"timeseries": 0,
	}
	if frappe.db.exists("Dashboard Chart", chart_name):
		frappe.db.set_value("Dashboard Chart", chart_name, values, update_modified=False)
		return
	chart = frappe.get_doc({"doctype": "Dashboard Chart", "name": chart_name, **values})
	chart.flags.ignore_validate = True
	chart.insert(ignore_permissions=True)


def _ensure_pending_approvals_chart() -> None:
	values = {
		"chart_name": CHART_NAME,
		"chart_type": "Report",
		"report_name": QUEUE_SHORTCUT,
		"use_report_chart": 1,
		"type": "Bar",
		"filters_json": "{}",
		"is_public": 1,
		"is_standard": 1,
		"module": "Dinext Common",
		"timeseries": 0,
	}
	if frappe.db.exists("Dashboard Chart", CHART_NAME):
		frappe.db.set_value("Dashboard Chart", CHART_NAME, values, update_modified=False)
		return
	chart = frappe.get_doc({"doctype": "Dashboard Chart", "name": CHART_NAME, **values})
	chart.flags.ignore_validate = True
	chart.insert(ignore_permissions=True)


def ensure_transition_identity() -> None:
	"""Fill an empty policy or UUID after fixture sync without replacing a UUID."""
	if not frappe.db.table_exists("Workflow Transition"):
		return
	if not frappe.db.has_column("Workflow Transition", "custom_transition_uuid"):
		return
	for row in frappe.db.get_all(
		"Workflow Transition",
		fields=[
			"name",
			"custom_all_users_with_role",
			"custom_parallel_approval_policy",
			"custom_transition_uuid",
		],
	):
		updates = {}
		if not row.custom_parallel_approval_policy:
			updates["custom_parallel_approval_policy"] = policy_from_legacy_flag(
				row.custom_all_users_with_role
			)
		if not row.custom_transition_uuid:
			updates["custom_transition_uuid"] = str(uuid4())
		if updates:
			frappe.db.set_value(
				"Workflow Transition",
				row.name,
				updates,
				update_modified=False,
			)


def _roles(rows: Iterable[object]) -> list[str]:
	return [
		str(row.get("role") if isinstance(row, dict) else getattr(row, "role", "") or "").strip()
		for row in rows
	]


def validate_workflow_configuration(workflow: object) -> None:
	"""Validate and normalize parallel transition and notification settings."""
	uuids: set[str] = set()
	for transition in getattr(workflow, "transitions", []) or []:
		raw_policy = getattr(transition, "custom_parallel_approval_policy", None)
		if raw_policy is None or str(raw_policy).strip() == "":
			policy = policy_from_legacy_flag(
				getattr(transition, "custom_all_users_with_role", None)
			)
		else:
			policy = normalize_policy(raw_policy)
		setattr(transition, "custom_parallel_approval_policy", policy)
		if not getattr(transition, "custom_transition_uuid", None):
			setattr(transition, "custom_transition_uuid", str(uuid4()))

		transition_uuid = str(getattr(transition, "custom_transition_uuid", ""))
		if transition_uuid in uuids:
			raise ValueError("Workflow transition UUIDs must be unique")
		uuids.add(transition_uuid)

		minimum = getattr(transition, "custom_minimum_approvals", None)
		if policy == "Minimum":
			try:
				minimum = int(minimum)
			except (TypeError, ValueError):
				raise ValueError("Minimum approvals must be a positive integer")
			if minimum <= 0:
				raise ValueError("Minimum approvals must be a positive integer")
			setattr(transition, "custom_minimum_approvals", minimum)

	monitor_roles = _roles(getattr(workflow, "custom_approval_monitor_roles", []) or [])
	if any(not role for role in monitor_roles) or len(monitor_roles) != len(set(monitor_roles)):
		raise ValueError("Approval monitor roles must be non-empty and unique")

	from dinext_common.workflow_approval.email_settings import prepare_email_profiles

	previous = workflow.get_doc_before_save() if hasattr(workflow, "get_doc_before_save") else None
	prepare_email_profiles(workflow, previous, now=frappe.utils.now_datetime)
	if getattr(workflow, "custom_group_workflow_action_emails", False):
		workflow.custom_attach_document_pdf = 0


def validate_workflow_doc(doc: object, method: str | None = None) -> None:
	"""Frappe hook that exposes validation failures as translated messages."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	from dinext_common.workflow_approval.exclusions import validate_exclusions

	try:
		validate_exclusions(doc)
		if is_engine_enabled():
			validate_workflow_configuration(doc)
	except ValueError as exc:
		frappe.throw(_(str(exc)))
