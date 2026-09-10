"""Preview-first signed email links bound to one Workflow Task delivery."""

from __future__ import annotations

import hashlib
import html
import json

import frappe
from frappe import _
from frappe.utils import get_datetime, get_url
from frappe.utils.verified_command import get_signed_params, verify_request
from frappe.workflow.doctype.workflow_action.workflow_action import (
	return_link_expired_page,
	return_success_page,
)

from dinext_common.workflow_approval import engine

COMMAND_TTL_SECONDS = 15 * 60


def _issue_command(payload: dict[str, str]) -> str:
	token = frappe.generate_hash(length=48)
	key = frappe.cache.make_key(f"workflow-approval-command:{token}")
	frappe.cache.set(key, json.dumps(payload), ex=COMMAND_TTL_SECONDS)
	return token


def _consume_command(token: str) -> dict[str, str] | None:
	key = frappe.cache.make_key(f"workflow-approval-command:{token}")
	raw = frappe.cache.eval(
		"local v=redis.call('GET',KEYS[1]); "
		"if v then redis.call('DEL',KEYS[1]) end; return v",
		1,
		key,
	)
	if not raw:
		return None
	return json.loads(raw)


def _peek_command(token: str) -> dict[str, str] | None:
	raw = frappe.cache.get(
		frappe.cache.make_key(f"workflow-approval-command:{token}")
	)
	return json.loads(raw) if raw else None


def _open_action(task_name: str, delivery_key: str | None = None) -> object | None:
	filters = {
		"custom_workflow_task": task_name,
		"status": "Open",
	}
	if delivery_key:
		filters["custom_delivery_key"] = delivery_key
	name = frappe.db.get_value("Workflow Action", filters)
	return frappe.get_doc("Workflow Action", name) if name else None


def _actor_can_read_task(task: object, user: str) -> bool:
	if not frappe.db.get_value("User", user, "enabled"):
		return False
	previous_user = frappe.session.user
	try:
		frappe.set_user(user)
		return bool(task.has_permission("read"))
	finally:
		frappe.set_user(previous_user)


def ensure_delivery_key(task_name: str) -> str:
	action = _open_action(task_name)
	if not action:
		raise engine.WorkflowApprovalConflictError(_("Workflow Action is no longer open"))
	if not action.custom_delivery_key:
		delivery_key = hashlib.sha256(
			f"Immediate\0{action.name}\0{task_name}".encode()
		).hexdigest()
		action.db_set(
			"custom_delivery_key",
			delivery_key,
			update_modified=False,
		)
		action.custom_delivery_key = frappe.db.get_value(
			"Workflow Action",
			action.name,
			"custom_delivery_key",
		)
	return action.custom_delivery_key


def get_task_action_url(task: object, transition: object) -> str:
	delivery_key = ensure_delivery_key(task.name)
	params = {
		"task_name": task.name,
		"transition_uuid": transition.transition_uuid,
		"user": task.approver,
		"current_state": task.workflow_state,
		"last_modified": str(
			frappe.db.get_value(
				task.reference_doctype,
				task.reference_name,
				"modified",
			)
			or ""
		),
		"delivery_key": delivery_key,
	}
	method = (
		"/api/method/dinext_common.workflow_approval.signed_links.preview_action"
	)
	return get_url(method + "?" + get_signed_params(params))


def _render_preview(
	task_name: str,
	transition_uuid: str,
	user: str,
	current_state: str,
	last_modified: str | None,
	delivery_key: str,
) -> None:
	task = frappe.get_doc("Workflow Task", task_name)
	try:
		source = frappe.get_doc(task.reference_doctype, task.reference_name)
	except frappe.DoesNotExistError:
		frappe.respond_as_web_page(
			_("Link Expired"),
			_("The referenced document is no longer available."),
			indicator_color="orange",
		)
		return
	transition = next(
		(
			row
			for row in task.available_workflow_transitions
			if row.transition_uuid == transition_uuid
		),
		None,
	)
	if (
		not transition
		or task.approver != user
		or (
			frappe.session.user != "Guest"
			and frappe.session.user != user
		)
		or task.status != "Working"
		or task.round_status != "Open"
		or not _actor_can_read_task(task, user)
		or task.workflow_state != current_state
		or not delivery_key
		or not _open_action(task_name, delivery_key)
	):
		return_link_expired_page(source, task.workflow_state)
		return
	confirmation_method = (
		"/api/method/dinext_common.workflow_approval.signed_links.confirm_action"
	)
	command_token = _issue_command(
		{
			"task_name": task_name,
			"transition_uuid": transition_uuid,
			"user": user,
			"delivery_key": delivery_key,
		}
	)
	confirmation_url = get_url(confirmation_method)
	changed = bool(
		last_modified
		and get_datetime(source.modified) != get_datetime(last_modified)
	)
	from frappe.sessions import get_csrf_token

	comment = (
		'<label for="workflow-comment">{}</label>'
		'<textarea id="workflow-comment" name="comment" required maxlength="4000" '
		'class="form-control"></textarea>'.format(html.escape(_("Comment")))
		if transition.comment_is_required
		else ""
	)
	message = """
		<p>{prompt}</p>
		{changed}
		<form method="post" action="{action}">
			<input type="hidden" name="csrf_token" value="{csrf}">
			<input type="hidden" name="command_token" value="{token}">
			{comment}
			<button type="submit" class="btn btn-primary">{confirm}</button>
		</form>
	""".format(
		prompt=html.escape(
			_("Apply workflow action {0}?").format(transition.action)
		),
		changed=(
			f'<p class="alert alert-warning">{html.escape(_("Document was modified after the email was sent."))}</p>'
			if changed
			else ""
		),
		action=html.escape(confirmation_url, quote=True),
		csrf=html.escape(get_csrf_token(), quote=True),
		token=html.escape(command_token, quote=True),
		comment=comment,
		confirm=html.escape(_("Confirm")),
	)
	frappe.respond_as_web_page(
		_("Workflow Action"),
		message,
		indicator_color="blue",
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def preview_action(
	task_name: str,
	transition_uuid: str,
	user: str,
	current_state: str,
	delivery_key: str,
	last_modified: str | None = None,
) -> None:
	if not verify_request():
		return
	_render_preview(
		task_name,
		transition_uuid,
		user,
		current_state,
		last_modified,
		delivery_key,
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def confirm_action(
	command_token: str,
	comment: object = None,
) -> None:
	preview = _peek_command(command_token)
	if preview and frappe.session.user not in ("Guest", preview["user"]):
		raise frappe.PermissionError(_("This approval link belongs to another user"))
	command = _consume_command(command_token)
	if not command:
		frappe.respond_as_web_page(
			_("Link Expired"),
			_("This approval command is expired or was already used."),
			indicator_color="orange",
		)
		return
	task_name = command["task_name"]
	transition_uuid = command["transition_uuid"]
	user = command["user"]
	delivery_key = command["delivery_key"]
	task = frappe.get_doc("Workflow Task", task_name)
	if (
		task.status != "Working"
		or task.round_status != "Open"
		or task.approver != user
		or not _open_action(task_name, delivery_key)
	):
		try:
			source = frappe.get_doc(task.reference_doctype, task.reference_name)
			return_link_expired_page(source, task.workflow_state)
		except frappe.DoesNotExistError:
			frappe.respond_as_web_page(
				_("Link Expired"),
				_("The referenced document is no longer available."),
				indicator_color="orange",
			)
		return
	previous_user = frappe.session.user
	try:
		frappe.set_user(user)
		result = engine.cast_vote(
			task_name,
			transition_uuid=transition_uuid,
			comment=comment,
			completion_source="Signed Link",
			request_id=f"signed:{command_token}",
		)
		return_success_page(
			frappe.get_doc(result["reference_doctype"], result["reference_name"])
		)
	finally:
		frappe.set_user(previous_user)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def apply_action(
	action: str,
	doctype: str,
	docname: str,
	current_state: str,
	user: str | None = None,
	last_modified: str | None = None,
) -> None:
	"""Compatibility entry point for already-issued standard Workflow links."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.workflow.doctype.workflow_action.workflow_action import (
			apply_action as core_apply_action,
		)

		return core_apply_action(
			action,
			doctype,
			docname,
			current_state,
			user,
			last_modified,
		)
	if not verify_request() or not user:
		return
	from dinext_common.workflow_approval.api import _find_task_for_action

	task_name = _find_task_for_action(doctype, docname, action, user)
	task = frappe.get_doc("Workflow Task", task_name)
	transition = next(
		row for row in task.available_workflow_transitions if row.action == action
	)
	workflow_action = _open_action(task_name)
	delivery_key = (
		workflow_action.custom_delivery_key
		if workflow_action
		else ""
	)
	_render_preview(
		task_name,
		transition.transition_uuid,
		user,
		current_state,
		last_modified,
		delivery_key,
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def confirm_legacy_action(
	doctype: str,
	docname: str,
	user: str,
	action: str,
) -> None:
	"""Compatibility confirmation for a signed standard link after cutover."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if not is_engine_enabled():
		from frappe.workflow.doctype.workflow_action.workflow_action import (
			confirm_action as core_confirm_action,
		)

		return core_confirm_action(doctype, docname, user, action)
	if not verify_request():
		return
	from dinext_common.workflow_approval.api import _find_task_for_action

	task_name = _find_task_for_action(doctype, docname, action, user)
	task = frappe.get_doc("Workflow Task", task_name)
	transition = next(
		row for row in task.available_workflow_transitions if row.action == action
	)
	workflow_action = _open_action(task_name)
	_render_preview(
		task_name,
		transition.transition_uuid,
		user,
		task.workflow_state,
		str(
			frappe.db.get_value(
				task.reference_doctype,
				task.reference_name,
				"modified",
			)
			or ""
		),
		workflow_action.custom_delivery_key if workflow_action else "",
	)
