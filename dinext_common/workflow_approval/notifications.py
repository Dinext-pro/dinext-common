"""Immediate and recipient-local grouped Workflow Task email delivery."""

from __future__ import annotations

import hashlib
import html
import json
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.email.doctype.email_template.email_template import get_email_template
from frappe.translate import get_user_lang, print_language
from frappe.utils import get_datetime, get_system_timezone, get_url_to_form, now_datetime

from dinext_common.workflow_approval.email_settings import checked, profile_for_state, value

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
	send_time: time | None = None,
	send_times: tuple[time, ...] = (),
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

	times = send_times or ((send_time,) if send_time else ())
	if unit != "Days" or not times:
		return None
	zone = get_timezone(timezone_name)
	now_local = now_utc.astimezone(zone)
	anchor_date = anchor_utc.astimezone(zone).date()
	days_since_anchor = (now_local.date() - anchor_date).days
	aligned_days = days_since_anchor - (days_since_anchor % interval)
	slot_date = anchor_date + timedelta(days=aligned_days)
	candidates = [
		_daily_slot_utc(day, scheduled, zone)
		for day in (slot_date, slot_date - timedelta(days=interval))
		for scheduled in times
	]
	return max((slot for slot in candidates if max(created_utc, anchor_utc) <= slot <= now_utc), default=None)


def make_delivery_key(mode: str, workflow: str, recipient: str, identity: str, *, state: str = "") -> str:
	raw = "\0".join((mode, workflow, recipient, state, identity))
	return hashlib.sha256(raw.encode()).hexdigest()


def _state_email_enabled(task: object) -> bool:
	return profile_for_state(frappe.get_doc("Workflow", task.workflow), task.workflow_state).enabled


def notification_transitions(task: object, workflow: object) -> list:
	"""Use live delivery flags; leave the immutable voting snapshot unchanged."""
	current = {value(row, "custom_transition_uuid"): row for row in workflow.transitions}
	return [
		row for row in task.available_workflow_transitions
		if (transition := current.get(value(row, "transition_uuid"))) is not None
		and (task.approver != task.source_owner or checked(value(transition, "send_email_to_creator")))
	]


def recipient_can_read(task: object, source: object, recipient: str) -> bool:
	"""Adapters may require access to a parent used in an email link."""
	from dinext_common.workflow_approval.engine import _has_source_read_permission

	if not _has_source_read_permission(source, recipient):
		return False
	return all(
		frappe.get_attr(path)(task, source, recipient) is not False
		for path in frappe.get_hooks("workflow_approval_email_permission") or []
	)


def _delivery_context(task: object, workflow: object):
	from dinext_common.workflow_approval.email_preferences import email_allowed
	if not email_allowed(task.approver):
		return None
	profile = profile_for_state(workflow, task.workflow_state)
	if not profile.enabled or task.status != "Working" or task.round_status != "Open":
		return None
	transitions = notification_transitions(task, workflow)
	if not transitions:
		return None
	user = frappe.db.get_value("User", task.approver, ["email", "enabled"], as_dict=True)
	if not user or not user.enabled or not user.email:
		return None
	if not frappe.db.exists(task.reference_doctype, task.reference_name):
		return None
	source = frappe.get_doc(task.reference_doctype, task.reference_name)
	if task.source_created_at and get_datetime(source.creation) != get_datetime(task.source_created_at):
		return None
	if not recipient_can_read(task, source, task.approver):
		return None
	return profile, source, user.email, transitions


def _queued_delivery(key: str) -> bool:
	# Frappe adds its domain to the caller-supplied message-id.
	return bool(key and frappe.db.exists("Email Queue", {"message_id": ("like", key + "%")}))


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
	"""Decide the current mode; immediate work is dispatched after commit."""
	action = _workflow_action(task.name)
	if not action:
		return
	if getattr(frappe.flags, "suppress_workflow_mail", False):
		action.db_set({"custom_notification_suppressed": 1, "custom_notification_status": "Skipped"}, update_modified=False)
		return
	workflow = frappe.get_doc("Workflow", task.workflow)
	profile = profile_for_state(workflow, task.workflow_state)
	if (getattr(frappe.flags, "suppress_workflow_mail", False) or not profile.enabled
		or not notification_transitions(task, workflow)):
		action.db_set({"custom_notification_status": "Skipped", "custom_notification_mode": None}, update_modified=False)
		return
	if action.custom_notification_status == "Enqueued" and _queued_delivery(action.custom_delivery_key):
		return
	from dinext_common.workflow_approval.signed_links import ensure_delivery_key
	ensure_delivery_key(task.name)
	action.db_set({"custom_notification_mode": profile.mode, "custom_notification_status": "Pending"}, update_modified=False)
	if profile.mode == "Immediate":
		frappe.enqueue(send_immediate_notification, task_name=task.name, queue="short",
			enqueue_after_commit=True, now=frappe.flags.in_test)


def _task_actions(task: object, *, transitions=None) -> list[dict[str, str]]:
	from dinext_common.workflow_approval.signed_links import get_task_action_url
	return [{"action_name": row.action, "action_link": get_task_action_url(task, row), "next_state": row.next_state}
		for row in (transitions if transitions is not None else task.available_workflow_transitions)]


def _message_context(task, source, transitions):
	manifest = json.loads(task.round_manifest or "{}")
	context = {**source.as_dict(), "doc": source.as_dict(), "workflow_task": task.as_dict(),
		"entry_context": manifest.get("entry_context") or {},
		"document_link": get_url_to_form(source.doctype, source.name),
		"actions": _task_actions(task, transitions=transitions)}
	for adapter_path in frappe.get_hooks("workflow_approval_email_context") or []:
		context.update(frappe.get_attr(adapter_path)(task, source) or {})
	return context


def _language_context(user: str | None):
	from dinext_common.workflow_approval.email_presentation import language_context
	return language_context(user)


def _template_message(
	template_name: str,
	context: dict,
	user: str | None = None,
) -> tuple[str, str]:
	with _language_context(user):
		from dinext_common.workflow_approval.email_presentation import prepare_context
		rendered = get_email_template(template_name, prepare_context(template_name, context, user))
	return rendered.get("subject") or "", rendered.get("message") or ""


def _sendmail_for_user(user: str, **kwargs):
	with _language_context(user):
		if kwargs.get("template") == "workflow_action" and (kwargs.get("args") or {}).get("message"):
			kwargs["message"] = kwargs.pop("args")["message"]
			kwargs.pop("template", None)
		kwargs.pop("header", None)
		from dinext_common.workflow_approval.email_presentation import inline_assets
		provided = list(kwargs.get("inline_images") or [])
		known = {item.get("filename") for item in provided}
		kwargs["inline_images"] = provided + [item for item in inline_assets(kwargs.get("message")) if item["filename"] not in known]
		if kwargs.get("message"):
			from frappe.core.utils import html_to_plain_text
			from frappe.utils import get_url
			body = kwargs.pop("message")
			kwargs["template"] = "dinext_workflow_message"
			kwargs["args"] = dict(message=body, text_message=html_to_plain_text(body), sent_label=_("Sent by"),
				settings_label=_("Notification settings"),
				settings_url=get_url("/api/method/dinext_common.workflow_approval.email_preferences.open_settings"))
		return frappe.sendmail(**kwargs)


def send_immediate_notification(task_name: str) -> None:
	task = frappe.get_doc("Workflow Task", task_name)
	action = _workflow_action(task_name, for_update=True)
	if not action or value(action, "custom_notification_suppressed") or task.status != "Working" or task.round_status != "Open":
		return
	if (
		action.custom_notification_mode == "Immediate"
		and action.custom_notification_status == "Enqueued"
	):
		return
	workflow = frappe.get_doc("Workflow", task.workflow)
	context = _delivery_context(task, workflow)
	if not context:
		action.db_set("custom_notification_status", "Skipped", update_modified=False)
		return
	profile, source, email, transitions = context
	if profile.mode != "Immediate":
		action.db_set({"custom_notification_mode": "Digest", "custom_notification_status": "Pending"}, update_modified=False)
		return
	if _queued_delivery(action.custom_delivery_key):
		action.db_set("custom_notification_status", "Enqueued", update_modified=False)
		return
	try:
		from dinext_common.workflow_approval.signed_links import ensure_delivery_key
		action.custom_delivery_key = ensure_delivery_key(task.name)
		action.db_set("custom_notification_mode", "Immediate", update_modified=False)
		message_context = _message_context(task, source, transitions)
		common_args = {
			"template": "workflow_action",
			"header": "Workflow Action",
		}
		template_name = profile.template
		if not frappe.db.exists("Email Template", template_name):
			template_name = DEFAULT_IMMEDIATE_TEMPLATE
		try:
			subject, message = _template_message(
				template_name,
				message_context,
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
				message_context,
				task.approver,
			)
		if subject:
			common_args["subject"] = subject
		if message:
			common_args["message"] = message
		attach_pdf = profile.attach_pdf
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
		common_args["sender"] = "Dinext <ikhmel@dinext.ru>"
		common_args["reply_to"] = "ikhmel@dinext.ru"
		common_args["args"] = {
			"actions": message_context["actions"],
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
	task = frappe.get_doc("Workflow Task", action.custom_workflow_task)
	profile = profile_for_state(workflow, task.workflow_state)
	if not profile.enabled or profile.mode != "Digest" or not profile.anchor:
		return None
	return latest_due_digest_slot(created_at=_aware_utc(action.creation), now=_aware_utc(now),
		timezone_name=_recipient_timezone(action.user), unit=profile.interval_unit,
		interval=profile.interval_value, send_times=profile.send_times, anchor=_aware_utc(profile.anchor))


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
	"""Re-read policies for open actions and deliver each state independently."""
	rows = frappe.get_all("Workflow Action", filters={"status": "Open", "custom_workflow_task": ("is", "set")},
		fields=["name", "user", "custom_workflow_task"], order_by="creation asc, name asc")
	groups = defaultdict(list)
	workflows = {}
	for row in rows:
		try:
			action = frappe.get_doc("Workflow Action", row.name)
			task = frappe.get_doc("Workflow Task", row.custom_workflow_task)
			if value(action, "custom_notification_suppressed") or task.status != "Working" or task.round_status != "Open":
				continue
			if task.workflow not in workflows:
				workflows[task.workflow] = frappe.get_doc("Workflow", task.workflow)
			workflow = workflows[task.workflow]
			profile = profile_for_state(workflow, task.workflow_state)
			if not profile.enabled or not notification_transitions(task, workflow):
				continue
			if profile.mode == "Immediate":
				if action.custom_notification_status != "Enqueued":
					send_immediate_notification(task.name)
			else:
				groups[(task.workflow, task.workflow_state, action.user)].append(action)
		except Exception:
			frappe.log_error(title=f"Workflow notification dispatch failed: {row.name}")
	current = now_datetime()
	for (workflow_name, state, recipient), actions in groups.items():
		workflow = workflows[workflow_name]
		due = [(action, slot) for action in actions if (slot := _action_needs_delivery(action, workflow, current))]
		if not due:
			continue
		try:
			send_digest(workflow, recipient, [action for action, _ in due], max(slot for _, slot in due), state=state)
		except Exception:
			for action, _ in due:
				action.db_set("custom_notification_status", "Failed", update_modified=False)
			frappe.log_error(title=f"Workflow approval digest failed: {workflow_name} / {state} / {recipient}")


def _digest_rows(tasks: list[object], *, permitted=None) -> list[dict[str, object]]:
	grouped: dict[str, dict[str, object]] = {}
	for task in tasks:
		row: dict[str, object] = {
			"group_key": f"{task.reference_doctype}:{task.reference_name}",
			"doctype": task.reference_doctype,
			"name": task.reference_name,
			"title": task.source_title,
			"link": get_url_to_form(task.reference_doctype, task.reference_name),
			"actions": _task_actions(task, transitions=permitted.get(task.name) if permitted is not None else None),
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
	*, state: str | None = None,
) -> None:
	"""Send all currently active tasks, without truncation, for one workflow."""
	active_actions = []
	tasks = []
	permitted = {}
	profile = None
	delivery_key = None
	for action in sorted(actions, key=lambda item: item.name):
		refreshed = _workflow_action(
			action.custom_workflow_task,
			for_update=True,
		)
		if not refreshed or value(refreshed, "custom_notification_suppressed"):
			continue
		task = frappe.get_doc("Workflow Task", action.custom_workflow_task)
		last_slot = (
			_aware_utc(refreshed.custom_last_digest_slot)
			if refreshed.custom_last_digest_slot
			else None
		)
		context = _delivery_context(task, workflow)
		if not context:
			continue
		current_profile, _source, _email, transitions = context
		state = state or task.workflow_state
		if task.workflow_state != state or current_profile.mode != "Digest" or (last_slot and last_slot >= _aware_utc(slot)):
			continue
		profile = current_profile
		delivery_key = make_delivery_key("Digest", workflow.name, recipient, slot.isoformat(), state=state)
		# Links must bind to this delivery, not the previous digest's key.
		refreshed.db_set("custom_delivery_key", delivery_key, update_modified=False)
		active_actions.append(refreshed)
		tasks.append(task)
		permitted[task.name] = transitions
	if not tasks:
		return
	rows = _digest_rows(tasks, permitted=permitted)
	template_name = (
		profile.digest_template
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
		"workflow_state": state,
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
	if not _queued_delivery(delivery_key):
		_sendmail_for_user(recipient, recipients=[email], sender="Dinext <ikhmel@dinext.ru>",
			reply_to="ikhmel@dinext.ru", subject=subject, message=message, header="Workflow Action",
			reference_doctype="Workflow", reference_name=workflow.name, message_id=delivery_key)
	for action in active_actions:
		action.db_set(
			{
				"custom_last_digest_slot": _database_datetime(slot),
				"custom_delivery_key": delivery_key,
				"custom_notification_status": "Enqueued",
			},
			update_modified=False,
		)
