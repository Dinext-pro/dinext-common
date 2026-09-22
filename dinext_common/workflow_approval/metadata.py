"""Metadata definitions and validation for parallel Workflow approvals."""

from __future__ import annotations

import json
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
	for fields in custom_fields.values():
		for field in fields:
			field.setdefault("module", "Dinext Common")
	return custom_fields


def ensure_workflow_approval_custom_fields() -> None:
	"""Create or update Custom Fields before exporting fixtures."""
	create_custom_fields(
		get_workflow_approval_custom_fields(),
		ignore_validate=True,
		update=True,
	)


def ensure_workflow_approval_email_templates() -> None:
	"""Install editable defaults used when a Workflow has no custom template."""
	templates = {
		"Dinext Workflow Action": {
			"subject": "Workflow Action on {{ doc.doctype }}: {{ doc.name }}",
			"response_html": (
				"<p>A workflow action is required for "
				"<strong>{{ doc.doctype }} {{ doc.name }}</strong>.</p>"
			),
		},
		"Dinext Workflow Correction": {
			"subject": "Correction required for {{ doc.doctype }}: {{ doc.name }}",
			"response_html": (
				"<p><strong>{{ doc.doctype }} {{ doc.name }}</strong> "
				"requires correction.</p>"
			),
		},
		"Dinext Workflow Digest": {
			"subject": "Pending workflow approvals",
			"response_html": (
				"<p>Pending workflow approvals:</p><ul>"
				"{% for row in rows %}<li><a href=\"{{ row.link }}\">"
				"{{ row.title }}</a>{% if row.count > 1 %} ({{ row.count }}){% endif %}"
				"</li>{% endfor %}</ul>"
			),
		},
		"Dinext Timesheet Workflow Digest": {
			"subject": "Timesheets awaiting approval",
			"response_html": (
				"<p>Timesheets awaiting approval:</p><ul>"
				"{% for row in rows %}<li><a href=\"{{ row.link }}\">"
				"{{ row.title }}</a> — {{ row.count }} position(s)</li>{% endfor %}</ul>"
			),
		},
	}
	for name, values in templates.items():
		if frappe.db.exists("Email Template", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": name,
				"use_html": 1,
				**values,
			}
		).insert(ignore_permissions=True)


def ensure_workflow_approval_desk_records() -> None:
	"""Install standard cards and the source-aware Workspace dashboard block."""
	cards = {
		"My open approvals": (
			"Ожидают моего решения",
			"dinext_common.workflow_approval.api.open_approval_count",
			"#2490EF",
		),
		"Новые сегодня": (
			"Новые сегодня",
			"dinext_common.workflow_approval.api.new_approval_count",
			"#39E4A5",
		),
		"My completed approvals": (
			"Решений за 30 дней",
			"dinext_common.workflow_approval.api.completed_approval_count",
			"#29CD42",
		),
		"Автоматически выполнено за 30 дней": (
			"Автоматически выполнено за 30 дней",
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

	workspace_name = "Мои согласования"
	if frappe.db.exists("Workspace", workspace_name):
		workspace = frappe.get_doc("Workspace", workspace_name)
		workspace.content = json.dumps(
			[
				{
					"id": "approvals-header",
					"type": "header",
					"data": {
						"text": '<span class="h4">Мои согласования</span>',
						"col": 12,
					},
				},
				{
					"id": "approvals-open",
					"type": "number_card",
					"data": {"number_card_name": "My open approvals", "col": 3},
				},
				{
					"id": "approvals-new",
					"type": "number_card",
					"data": {"number_card_name": "Новые сегодня", "col": 3},
				},
				{
					"id": "approvals-completed",
					"type": "number_card",
					"data": {"number_card_name": "My completed approvals", "col": 3},
				},
				{
					"id": "approvals-automatic",
					"type": "number_card",
					"data": {
						"number_card_name": "Автоматически выполнено за 30 дней",
						"col": 3,
					},
				},
				{"id": "approvals-spacer", "type": "spacer", "data": {"col": 12}},
				{
					"id": "approvals-dashboard",
					"type": "custom_block",
					"data": {
						"custom_block_name": "My Approvals Dashboard",
						"col": 12,
					},
				},
			],
			ensure_ascii=False,
		)
		workspace.number_cards = []
		# EditorJS matches a block by child label against __(number_card_name).
		for card_name in (
			"My open approvals",
			"Новые сегодня",
			"My completed approvals",
			"Автоматически выполнено за 30 дней",
		):
			workspace.append(
				"number_cards",
				{"label": card_name, "number_card_name": card_name},
			)
		workspace.custom_blocks = []
		workspace.append(
			"custom_blocks",
			{
				"custom_block_name": "My Approvals Dashboard",
				"label": "My Approvals Dashboard",
			},
		)
		workspace.save(ignore_permissions=True)

	block_name = "My Approvals Dashboard"
	block_script = (
		'frappe.require(["/assets/dinext_common/js/my_approvals_workspace.js"], () => {\n'
		"\tdinext_common.my_approvals.mount(root_element);\n"
		"});\n"
	)
	block_html = '<div class="dinext-my-approvals"></div>'
	if frappe.db.exists("Custom HTML Block", block_name):
		block = frappe.get_doc("Custom HTML Block", block_name)
		block.html = block_html
		block.script = block_script
		block.private = 0
		block.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			{
				"doctype": "Custom HTML Block",
				"name": block_name,
				"html": block_html,
				"script": block_script,
				"style": "",
				"private": 0,
			}
		).insert(ignore_permissions=True)
	_ensure_public_widget_read()


def _ensure_public_widget_read() -> None:
	"""Let the approver role read standard cards when it has no Desk User perm."""
	role = "Dinext_UTP_Appoval"
	if not frappe.db.exists("Role", role):
		return
	for doctype in ("Number Card", "Custom HTML Block"):
		if _role_can_read(doctype, role):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"role": role,
				"permlevel": 0,
				"read": 1,
				"select": 1,
				"write": 0,
				"create": 0,
				"delete": 0,
				"submit": 0,
				"cancel": 0,
				"amend": 0,
				"report": 0,
				"export": 0,
				"print": 0,
				"email": 0,
				"share": 0,
				"if_owner": 0,
			}
		).insert(ignore_permissions=True)


def _role_can_read(doctype: str, role: str) -> bool:
	for table in ("DocPerm", "Custom DocPerm"):
		if frappe.db.exists(
			table,
			{"parent": doctype, "role": role, "permlevel": 0, "read": 1},
		):
			return True
	return False


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

	if not bool(getattr(workflow, "send_email_alert", False)):
		return
	if not bool(getattr(workflow, "custom_group_workflow_action_emails", False)):
		return
	setattr(workflow, "custom_attach_document_pdf", 0)
	if not getattr(workflow, "custom_group_schedule_anchor", None):
		setattr(workflow, "custom_group_schedule_anchor", frappe.utils.now_datetime())

	unit = str(getattr(workflow, "custom_group_interval_unit", "") or "")
	if unit not in {"Hours", "Days"}:
		raise ValueError("Digest interval unit must be Hours or Days")
	try:
		interval = int(getattr(workflow, "custom_group_interval_value", 0) or 0)
	except (TypeError, ValueError):
		raise ValueError("Digest interval must be a positive integer")
	if interval <= 0:
		raise ValueError("Digest interval must be a positive integer")
	if unit == "Days" and not getattr(workflow, "custom_group_send_time", None):
		raise ValueError("Digest send time is required for daily delivery")


def validate_workflow_doc(doc: object, method: str | None = None) -> None:
	"""Frappe hook that exposes validation failures as translated messages."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		return
	try:
		validate_workflow_configuration(doc)
	except ValueError as exc:
		frappe.throw(_(str(exc)))
