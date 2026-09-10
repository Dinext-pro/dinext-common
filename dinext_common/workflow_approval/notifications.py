"""Immediate and recipient-local grouped Workflow Task email delivery."""

from __future__ import annotations

import hashlib
import html
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.email.doctype.email_template.email_template import get_email_template
from frappe.translate import get_user_lang, print_language
from frappe.utils import get_datetime, get_system_timezone, get_url_to_form, now_datetime

DEFAULT_IMMEDIATE_TEMPLATE = "Dinext Workflow Action"
DEFAULT_DIGEST_TEMPLATE = "Dinext Workflow Digest"
DEFAULT_TIMESHEET_DIGEST_TEMPLATE = "Dinext Timesheet Workflow Digest"
DEFAULT_MAX_DIGEST_BYTES = 10 * 1024 * 1024


def get_timezone(name: str | None) -> ZoneInfo:
	try:
		return ZoneInfo(name or "UTC")
	except ZoneInfoNotFoundError:
		return ZoneInfo("UTC")


def _aware_utc(value: datetime | str) -> datetime:
	value = get_datetime(value) if not isinstance(value, datetime) else value
	if value.tzinfo is None:
		value = value.replace(tzinfo=get_timezone(get_system_timezone()))
	return value.astimezone(timezone.utc)


def _database_datetime(value: datetime) -> datetime:
	return value.astimezone(get_timezone(get_system_timezone())).replace(tzinfo=None)


def _daily_slot_utc(slot_date, send_time: time, zone: ZoneInfo) -> datetime:
	"""Resolve DST gaps forward and choose the first occurrence of duplicate time."""
	naive = datetime.combine(slot_date, send_time)
	for minute_offset in range(181):
		candidate_naive = naive + timedelta(minutes=minute_offset)
		candidate = candidate_naive.replace(tzinfo=zone, fold=0)
		utc = candidate.astimezone(timezone.utc)
		round_trip = utc.astimezone(zone)
		if round_trip.replace(tzinfo=None) == candidate_naive:
			return utc
	raise ValueError("Could not resolve recipient-local digest time")


def latest_due_digest_slot(
	*,
	created_at: datetime,
	now: datetime,
	timezone_name: str,
	unit: str,
	interval: int,
	send_time: time | None,
	anchor: datetime,
) -> datetime | None:
	"""Return one latest due slot, naturally coalescing scheduler downtime."""
	if interval <= 0:
		return None
	created_utc = _aware_utc(created_at)
	now_utc = _aware_utc(now)
	anchor_utc = _aware_utc(anchor)
	if unit == "Hours":
		if now_utc < anchor_utc:
			return None
		elapsed_hours = (now_utc - anchor_utc).total_seconds() / 3600
		index = int(elapsed_hours // interval)
		slot = anchor_utc + timedelta(hours=index * interval)
		if slot < created_utc:
			return None
		return slot if slot <= now_utc else None

	if unit != "Days" or send_time is None:
		return None
	zone = get_timezone(timezone_name)
	now_local = now_utc.astimezone(zone)
	anchor_date = anchor_utc.astimezone(zone).date()
	days_since_anchor = (now_local.date() - anchor_date).days
	aligned_days = days_since_anchor - (days_since_anchor % interval)
	slot_date = anchor_date + timedelta(days=aligned_days)
	slot = _daily_slot_utc(slot_date, send_time, zone)
	if slot > now_utc:
		slot_date -= timedelta(days=interval)
		slot = _daily_slot_utc(slot_date, send_time, zone)
	if slot < created_utc:
		return None
	return slot


def make_delivery_key(mode: str, workflow: str, recipient: str, identity: str) -> str:
	raw = "\0".join((mode, workflow, recipient, identity))
	return hashlib.sha256(raw.encode()).hexdigest()


def _state_email_enabled(task: object) -> bool:
	workflow = frappe.get_cached_doc("Workflow", task.workflow)
	if not workflow.send_email_alert:
		return False
	return bool(
		frappe.db.get_value(
			"Workflow Document State",
			{"parent": task.workflow, "state": task.workflow_state},
			"send_email",
		)
	)


def _workflow_action(task_name: str, *, for_update: bool = False) -> object | None:
	name = frappe.db.get_value(
		"Workflow Action",
		{"custom_workflow_task": task_name, "status": "Open"},
	)
	return (
		frappe.get_doc("Workflow Action", name, for_update=for_update)
		if name
		else None
	)


def schedule_task_notification(task: object) -> None:
	"""Persist notification mode immediately; enqueue only immediate delivery."""
	action = _workflow_action(task.name)
	if not action:
		return
	if not _state_email_enabled(task):
		action.db_set(
			{
				"custom_notification_status": "Skipped",
				"custom_notification_mode": None,
			},
			update_modified=False,
		)
		return
	if (
		task.approver == task.source_owner
		and not any(
			transition.send_email_to_creator
			for transition in task.available_workflow_transitions
		)
	):
		action.db_set(
			{
				"custom_notification_status": "Skipped",
				"custom_notification_mode": None,
			},
			update_modified=False,
		)
		return
	from dinext_common.workflow_approval.signed_links import ensure_delivery_key

	ensure_delivery_key(task.name)
	workflow = frappe.get_cached_doc("Workflow", task.workflow)
	if workflow.custom_group_workflow_action_emails:
		action.db_set(
			{
				"custom_notification_mode": "Digest",
				"custom_notification_status": "Pending",
			},
			update_modified=False,
		)
		return
	if (
		action.custom_notification_mode == "Immediate"
		and action.custom_notification_status == "Enqueued"
	):
		return
	action.db_set(
		{
			"custom_notification_mode": "Immediate",
			"custom_notification_status": "Pending",
		},
		update_modified=False,
	)
	frappe.enqueue(
		send_immediate_notification,
		task_name=task.name,
		queue="short",
		enqueue_after_commit=True,
		now=frappe.flags.in_test,
	)


def _task_actions(task: object) -> list[dict[str, str]]:
	from dinext_common.workflow_approval.signed_links import get_task_action_url

	actions = []
	for transition in task.available_workflow_transitions:
		link = get_task_action_url(task, transition)
		actions.append({"action_name": transition.action, "action_link": link})
	return actions


def _language_context(user: str | None):
	return print_language(get_user_lang(user)) if user else nullcontext()


def _template_message(
	template_name: str,
	context: dict,
	user: str | None = None,
) -> tuple[str, str]:
	with _language_context(user):
		rendered = get_email_template(template_name, context)
	return rendered.get("subject") or "", rendered.get("message") or ""


def _sendmail_for_user(user: str, **kwargs):
	with _language_context(user):
		return frappe.sendmail(**kwargs)


def send_immediate_notification(task_name: str) -> None:
	task = frappe.get_doc("Workflow Task", task_name)
	action = _workflow_action(task_name, for_update=True)
	if not action or task.status != "Working" or task.round_status != "Open":
		return
	if (
		action.custom_notification_mode == "Immediate"
		and action.custom_notification_status == "Enqueued"
	):
		return
	workflow = frappe.get_cached_doc("Workflow", task.workflow)
	source = frappe.get_doc(task.reference_doctype, task.reference_name)
	user = frappe.db.get_value(
		"User",
		task.approver,
		["email", "enabled"],
		as_dict=True,
	)
	email = user.email if user and user.enabled else None
	if not email:
		action.db_set("custom_notification_status", "Skipped", update_modified=False)
		return
	try:
		common_args = {
			"template": "workflow_action",
			"header": "Workflow Action",
		}
		transition_templates = {
			row.email_template
			for row in task.available_workflow_transitions
			if row.email_template
		}
		state_template = next(
			(
				row.next_action_email_template
				for row in workflow.states
				if row.state == task.workflow_state and row.next_action_email_template
			),
			None,
		)
		template_name = (
			workflow.custom_workflow_action_email_template
			or state_template
			or (
				next(iter(transition_templates))
				if len(transition_templates) == 1
				else None
			)
			or DEFAULT_IMMEDIATE_TEMPLATE
		)
		if not frappe.db.exists("Email Template", template_name):
			template_name = DEFAULT_IMMEDIATE_TEMPLATE
		try:
			subject, message = _template_message(
				template_name,
				{
					**source.as_dict(),
					"doc": source.as_dict(),
					"workflow_task": task.as_dict(),
				},
				task.approver,
			)
		except Exception:
			if template_name == DEFAULT_IMMEDIATE_TEMPLATE:
				raise
			frappe.log_error(
				title=f"Workflow email template fallback: {template_name}",
				reference_doctype="Workflow Task",
				reference_name=task.name,
			)
			subject, message = _template_message(
				DEFAULT_IMMEDIATE_TEMPLATE,
				{
					**source.as_dict(),
					"doc": source.as_dict(),
					"workflow_task": task.as_dict(),
				},
				task.approver,
			)
		if subject:
			common_args["subject"] = subject
		if message:
			common_args["message"] = message
		attach_pdf = bool(workflow.custom_attach_document_pdf)
		common_args["attachments"] = (
			[
				frappe.attach_print(
					source.doctype,
					source.name,
					file_name=source.name,
					doc=source,
					print_format=source.meta.default_print_format,
				)
			]
			if attach_pdf
			else []
		)
		common_args["recipients"] = [email]
		common_args["sender"] = "Dinext <erpnext@dinord.ru>"
		common_args["args"] = {
			"actions": _task_actions(task),
			"message": common_args.pop("message", None),
		}
		common_args["reference_doctype"] = task.reference_doctype
		common_args["reference_name"] = task.reference_name
		common_args["message_id"] = action.custom_delivery_key
		_sendmail_for_user(task.approver, **common_args)
		action.db_set("custom_notification_status", "Enqueued", update_modified=False)
	except Exception:
		action.db_set("custom_notification_status", "Failed", update_modified=False)
		frappe.log_error(
			title=f"Workflow approval email failed: {task.name}",
			reference_doctype="Workflow Task",
			reference_name=task.name,
		)
		raise


def _recipient_timezone(user: str) -> str:
	return (
		frappe.db.get_value("User", user, "time_zone")
		or frappe.db.get_single_value("System Settings", "time_zone")
		or "UTC"
	)


def _slot_for_action(action: object, workflow: object, now: datetime) -> datetime | None:
	anchor = workflow.custom_group_schedule_anchor or workflow.modified
	send_time = (
		get_datetime(f"2000-01-01 {workflow.custom_group_send_time}").time()
		if workflow.custom_group_send_time
		else None
	)
	return latest_due_digest_slot(
		created_at=_aware_utc(action.creation),
		now=_aware_utc(now),
		timezone_name=_recipient_timezone(action.user),
		unit=workflow.custom_group_interval_unit,
		interval=int(workflow.custom_group_interval_value or 0),
		send_time=send_time,
		anchor=_aware_utc(anchor),
	)


def _action_needs_delivery(action: object, workflow: object, now: datetime) -> datetime | None:
	slot = _slot_for_action(action, workflow, now)
	if not slot:
		return None
	last = (
		_aware_utc(action.custom_last_digest_slot)
		if action.custom_last_digest_slot
		else None
	)
	return slot if not last or slot > last else None


def dispatch_due_notifications() -> None:
	"""Send at most one catch-up digest per recipient/workflow scheduler run."""
	immediate = frappe.get_all(
		"Workflow Action",
		filters={
			"status": "Open",
			"custom_notification_mode": "Immediate",
			"custom_notification_status": ("in", ("Pending", "Failed")),
			"custom_workflow_task": ("is", "set"),
		},
		pluck="custom_workflow_task",
		order_by="creation asc, name asc",
	)
	for task_name in immediate:
		try:
			send_immediate_notification(task_name)
		except Exception:
			# The sender persists/logs a repairable Failed projection.
			continue

	rows = frappe.get_all(
		"Workflow Action",
		filters={
			"status": "Open",
			"custom_notification_mode": "Digest",
			"custom_workflow_task": ("is", "set"),
		},
		fields=["name", "user", "custom_workflow_task"],
		order_by="creation asc, name asc",
	)
	groups: dict[tuple[str, str], list[object]] = defaultdict(list)
	for row in rows:
		action = frappe.get_doc("Workflow Action", row.name)
		task = frappe.get_doc("Workflow Task", action.custom_workflow_task)
		if task.status == "Working" and task.round_status == "Open":
			groups[(task.workflow, action.user)].append(action)

	current = now_datetime()
	for (workflow_name, recipient), actions in groups.items():
		workflow = frappe.get_cached_doc("Workflow", workflow_name)
		due_actions = [
			(action, slot)
			for action in actions
			if (slot := _action_needs_delivery(action, workflow, current))
		]
		if not due_actions:
			continue
		slot = max(due for _action, due in due_actions)
		actions_for_slot = [action for action, _due in due_actions]
		try:
			send_digest(workflow, recipient, actions_for_slot, slot)
		except Exception:
			for action in actions_for_slot:
				action.db_set("custom_notification_status", "Failed", update_modified=False)
			frappe.log_error(title=f"Workflow approval digest failed: {workflow_name} / {recipient}")


def _digest_rows(tasks: list[object]) -> list[dict[str, object]]:
	grouped: dict[str, dict[str, object]] = {}
	for task in tasks:
		row: dict[str, object] = {
			"group_key": f"{task.reference_doctype}:{task.reference_name}",
			"doctype": task.reference_doctype,
			"name": task.reference_name,
			"title": task.source_title,
			"link": get_url_to_form(task.reference_doctype, task.reference_name),
			"actions": _task_actions(task),
			"count": 1,
			"tasks": [task.name],
		}
		for adapter_path in frappe.get_hooks("workflow_approval_digest_item") or []:
			override = frappe.get_attr(adapter_path)(task)
			if override is not None:
				row.update(override)
		key = str(row.pop("group_key"))
		if key in grouped:
			grouped[key]["count"] = int(grouped[key]["count"]) + 1
			grouped[key]["tasks"].append(task.name)
		else:
			grouped[key] = row
	return [grouped[key] for key in sorted(grouped)]


def _default_digest_html(rows: list[dict[str, object]]) -> str:
	items = "".join(
		"<li><a href='{link}'>{title}</a>{count}</li>".format(
			link=html.escape(str(row["link"]), quote=True),
			title=html.escape(str(row["title"])),
			count=f" ({row['count']})" if int(row["count"]) > 1 else "",
		)
		for row in rows
	)
	return f"<p>{html.escape(_('Pending workflow approvals'))}</p><ul>{items}</ul>"


def send_digest(
	workflow: object,
	recipient: str,
	actions: list[object],
	slot: datetime,
) -> None:
	"""Send all currently active tasks, without truncation, for one workflow."""
	active_actions = []
	tasks = []
	for action in sorted(actions, key=lambda item: item.name):
		refreshed = _workflow_action(
			action.custom_workflow_task,
			for_update=True,
		)
		if not refreshed:
			continue
		task = frappe.get_doc("Workflow Task", action.custom_workflow_task)
		last_slot = (
			_aware_utc(refreshed.custom_last_digest_slot)
			if refreshed.custom_last_digest_slot
			else None
		)
		if (
			task.status == "Working"
			and task.round_status == "Open"
			and _state_email_enabled(task)
			and workflow.custom_group_workflow_action_emails
			and (not last_slot or last_slot < _aware_utc(slot))
		):
			active_actions.append(refreshed)
			tasks.append(task)
	if not tasks:
		return
	rows = _digest_rows(tasks)
	template_name = (
		workflow.custom_group_email_template
		or (
			DEFAULT_TIMESHEET_DIGEST_TEMPLATE
			if any(task.reference_doctype == "User Timesheet Position" for task in tasks)
			else DEFAULT_DIGEST_TEMPLATE
		)
	)
	context = {
		"workflow": workflow.as_dict(),
		"recipient": recipient,
		"tasks": [task.as_dict() for task in tasks],
		"rows": rows,
		"slot": slot,
	}
	if not frappe.db.exists("Email Template", template_name):
		template_name = DEFAULT_DIGEST_TEMPLATE
	try:
		subject, message = _template_message(template_name, context, recipient)
	except Exception:
		if template_name == DEFAULT_DIGEST_TEMPLATE:
			raise
		frappe.log_error(
			title=f"Workflow digest template fallback: {template_name}",
			reference_doctype="Workflow",
			reference_name=workflow.name,
		)
		if frappe.db.exists("Email Template", DEFAULT_DIGEST_TEMPLATE):
			subject, message = _template_message(
				DEFAULT_DIGEST_TEMPLATE,
				context,
				recipient,
			)
		else:
			subject = _("Pending workflow approvals")
			message = _default_digest_html(rows)
	if not subject and not message:
		subject = _("Pending workflow approvals")
		message = _default_digest_html(rows)
	max_bytes = int(
		frappe.conf.get(
			"workflow_approval_max_digest_bytes",
			DEFAULT_MAX_DIGEST_BYTES,
		)
	)
	rendered_bytes = len(subject.encode("utf-8")) + len(message.encode("utf-8"))
	if rendered_bytes > max_bytes:
		raise frappe.ValidationError(
			_("Workflow digest is {0} bytes; configured maximum is {1}").format(
				rendered_bytes,
				max_bytes,
			)
		)
	user = frappe.db.get_value(
		"User",
		recipient,
		["email", "enabled"],
		as_dict=True,
	)
	email = user.email if user and user.enabled else None
	if not email:
		return
	delivery_key = make_delivery_key(
		"Digest",
		workflow.name,
		recipient,
		slot.isoformat(),
	)
	_sendmail_for_user(
		recipient,
		recipients=[email],
		sender="Dinext <erpnext@dinord.ru>",
		subject=subject,
		message=message,
		header="Workflow Action",
		reference_doctype="Workflow",
		reference_name=workflow.name,
		message_id=delivery_key,
	)
	for action in active_actions:
		action.db_set(
			{
				"custom_last_digest_slot": _database_datetime(slot),
				"custom_delivery_key": delivery_key,
				"custom_notification_status": "Enqueued",
			},
			update_modified=False,
		)
