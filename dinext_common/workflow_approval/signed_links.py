"""Preview-first signed email links bound to one Workflow Task delivery."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
from urllib.parse import unquote_plus, urlsplit

import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name
from frappe.utils import get_datetime, get_url
from frappe.utils.verified_command import get_signed_params, verify_request
from frappe.workflow.doctype.workflow_action.workflow_action import return_success_page
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from werkzeug.wrappers import Response

from dinext_common.workflow_approval import engine, localization

COMMAND_TTL_SECONDS = 15 * 60
COMMAND_CACHE_ERRORS = (RedisConnectionError, RedisTimeoutError)
EMAIL_ACTION_PAGE = "/api/method/dinext_common.workflow_approval.signed_links.open_email_action"
EMAIL_ACTION_PREVIEW = "/api/method/dinext_common.workflow_approval.signed_links.preview_email_action"
SIGNED_PREVIEW_PREFIX = "approval_preview="
SIGNED_PREVIEW_FIELDS = {
	"task_name", "transition_uuid", "user", "current_state", "last_modified", "delivery_key",
}


def _show_expired_link() -> None:
	frappe.respond_as_web_page(
		_("Link Expired"),
		_("This approval action is no longer available."),
		indicator_color="orange",
	)


def _show_confirmation_unavailable() -> None:
	frappe.respond_as_web_page(
		_("Workflow confirmation unavailable"),
		_("Please try this approval action again in a moment."),
		http_status_code=503,
		indicator_color="orange",
	)


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


def _clear_committed_command(token: str) -> None:
	try:
		_consume_command(token)
	except COMMAND_CACHE_ERRORS:
		# The completed receipt still prevents a second vote until the token expires.
		frappe.logger("workflow_approval").warning("Unable to clear a committed workflow confirmation")


def _configuration_restored(task) -> bool:
	return bool(json.loads(task.get("notification_delivery_snapshot") or "{}").get("configuration_restored"))


def _link_delivery_key(action, task) -> str:
	key = action.custom_delivery_key
	if not key or not _configuration_restored(task):
		return key
	return hashlib.sha256(f"{action.name}\0{key}".encode()).hexdigest()


def _open_action(task_name: str, delivery_key: str | None = None, *, locked_task=None) -> object | None:
	lock = locked_task is not None
	name = frappe.db.get_value(
		"Workflow Action", {"custom_workflow_task": task_name, "status": "Open"}, for_update=lock,
	)
	if not name:
		return None
	action = frappe.get_doc("Workflow Action", name, for_update=lock)
	if delivery_key:
		task = locked_task if lock else frappe.get_doc("Workflow Task", task_name)
		if delivery_key != _link_delivery_key(action, task):
			return None
	return action


def _actor_can_read_task(task: object, user: str) -> bool:
	if not frappe.db.get_value("User", user, "enabled"):
		return False
	previous_user = frappe.session.user
	try:
		frappe.session.user = user
		return bool(task.has_permission("read", user=user))
	finally:
		frappe.session.user = previous_user


def _ensure_delivery_action(task_name: str) -> object:
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
	return action


def ensure_delivery_key(task_name: str) -> str:
	return _ensure_delivery_action(task_name).custom_delivery_key


def get_task_action_url(task: object, transition: object) -> str:
	action = _ensure_delivery_action(task.name)
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
		"delivery_key": _link_delivery_key(action, task),
	}
	# The browser keeps fragments out of the request URL and Referer.
	signed = get_signed_params({"approval_preview": json.dumps(params, separators=(",", ":"))})
	return get_url(EMAIL_ACTION_PAGE + "#" + signed)


def _read_signed_email_preview(preview_token: str) -> dict[str, str] | None:
	if not preview_token or len(preview_token) > 8192:
		return None
	encoded_token, separator, _signature = preview_token.rpartition("&_signature=")
	if not separator or not encoded_token.startswith(SIGNED_PREVIEW_PREFIX):
		return None
	if not hmac.compare_digest(preview_token.encode(), get_signed_params(encoded_token).encode()):
		return None
	try:
		payload = json.loads(unquote_plus(encoded_token.removeprefix(SIGNED_PREVIEW_PREFIX), errors="strict"))
	except ValueError:
		return None
	if (
		not isinstance(payload, dict)
		or payload.keys() != SIGNED_PREVIEW_FIELDS
		or any(not isinstance(value, str) for value in payload.values())
	):
		return None
	return payload


@frappe.whitelist(allow_guest=True, methods=["GET"])
def open_email_action() -> Response:
	"""Open a minimal same-origin page without receiving signed data in its URL."""
	from frappe.sessions import get_csrf_token

	title = html.escape(_("Opening workflow action"))
	no_script = html.escape(_("Enable JavaScript to open the approval preview."))
	csrf_token = html.escape(get_csrf_token(), quote=True)
	body = f"""<!doctype html>
<html lang="{html.escape(frappe.local.lang or "en", quote=True)}">
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<title>{title}</title>
	<script src="/assets/dinext_common/js/workflow_email_link.js" defer></script>
</head>
<body>
	<main>
		<p role="status">{title}</p>
		<noscript>{no_script}</noscript>
		<form id="workflow-email-preview" method="post" action="{EMAIL_ACTION_PREVIEW}">
			<input type="hidden" name="csrf_token" value="{csrf_token}">
			<input type="hidden" name="preview_token">
		</form>
	</main>
</body>
</html>"""
	return Response(body, content_type="text/html; charset=utf-8", headers={
		"Cache-Control": "no-store",
		"Referrer-Policy": "same-origin",
		"Content-Security-Policy": "default-src 'none'; script-src 'self'; form-action 'self'; "
		"frame-ancestors 'none'; base-uri 'none'",
	})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def preview_email_action() -> None:
	preview_tokens = frappe.request.form.getlist("preview_token")
	frappe.form_dict.pop("preview_token", None)
	if len(preview_tokens) != 1 or not _is_same_origin_preview():
		_show_expired_link()
		return
	payload = _read_signed_email_preview(preview_tokens[0])
	if not payload:
		_show_expired_link()
		return
	_render_preview(**payload)


def _is_same_origin_preview() -> bool:
	"""Guest sessions do not persist Frappe's CSRF token between requests."""
	try:
		origin = urlsplit(frappe.request.headers.get("Origin", ""))
		configured = urlsplit(get_url())
		default_port = {"http": 80, "https": 443}.get(origin.scheme)
		return bool(
			default_port
			and origin.hostname
			and not (origin.username or origin.password or origin.path or origin.query or origin.fragment)
			and origin.scheme == configured.scheme
			and origin.hostname == configured.hostname
			and (origin.port or default_port) == (configured.port or default_port)
		)
	except ValueError:
		return False


def _render_preview(
	task_name: str,
	transition_uuid: str,
	user: str,
	current_state: str,
	last_modified: str | None,
	delivery_key: str,
) -> None:
	try:
		task = frappe.get_doc("Workflow Task", task_name)
		source = frappe.get_doc(task.reference_doctype, task.reference_name)
	except frappe.DoesNotExistError:
		_show_expired_link()
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
		or not _scenario_task_current(source, task)
		or task.status != "Working"
		or task.round_status != "Open"
		or not _actor_can_read_task(task, user)
		or task.workflow_state != localization.state_name(task.workflow, current_state)
		or not delivery_key
		or not _open_action(task_name, delivery_key)
	):
		_show_expired_link()
		return
	confirmation_method = (
		"/api/method/dinext_common.workflow_approval.signed_links.confirm_action"
	)
	try:
		command_token = _issue_command(
			{
				"task_name": task_name,
				"transition_uuid": transition_uuid,
				"user": user,
				"delivery_key": delivery_key,
				"modified": str(get_datetime(source.modified)),
				"creation": str(get_datetime(source.creation)),
				"transition_hash": transition.transition_semantic_hash,
			}
		)
	except COMMAND_CACHE_ERRORS:
		_show_confirmation_unavailable()
		return
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
		if engine.current_comment_required(task, transition_uuid)
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
	try:
		preview = _peek_command(command_token)
	except COMMAND_CACHE_ERRORS:
		_show_confirmation_unavailable()
		return
	if preview and frappe.session.user not in ("Guest", preview["user"]):
		raise frappe.PermissionError(_("This approval link belongs to another user"))
	command = preview
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
	try:
		task = frappe.get_doc("Workflow Task", task_name)
	except frappe.DoesNotExistError:
		_show_expired_link()
		return
	if (
		task.status != "Working"
		or task.round_status != "Open"
		or task.approver != user
		or not _actor_can_read_task(task, user)
		or not _open_action(task_name, delivery_key)
	):
		_show_expired_link()
		return
	from dinext_common.workflow_approval.api import _read_round_failure

	failure = _read_round_failure(task.failure_metadata)
	retry_from = failure.get("submission_queue") if failure and failure.get("task_name") == task.name else ""
	attempt = hashlib.sha256(f"{command_token}:{retry_from}".encode()).hexdigest()
	previous_user = frappe.session.user
	try:
		frappe.session.user = user
		result = engine.cast_vote(
			task_name,
			transition_uuid=transition_uuid,
			comment=comment,
			completion_source="Signed Link",
			request_id=f"signed:{attempt}",
			expected_creation=command.get("creation"),
			expected_modified=command.get("modified"),
			expected_transition_hash=command.get("transition_hash"),
			expected_delivery_key=delivery_key,
		)
		if result.get("pending_submission"):
			frappe.respond_as_web_page(
				_("Workflow action queued"),
				_("The vote will be recorded when background submission completes."),
				http_status_code=202,
			)
			return
		# Invalid input/rollback leaves the command usable; the engine request ID
		# makes a retry after commit idempotent even if Redis cleanup is delayed.
		frappe.db.after_commit.add(lambda: _clear_committed_command(command_token))
		return_success_page(
			frappe.get_doc(result["reference_doctype"], result["reference_name"])
		)
	except (engine.ExpiredWorkflowActionError, frappe.DoesNotExistError, frappe.PermissionError):
		_show_expired_link()
	except (engine.NoEligibleApproversError, engine.WorkflowDomainRollbackError, engine.WorkflowSourceChangedError) as error:
		if isinstance(error, engine.WorkflowSourceChangedError):
			frappe.db.rollback()
		frappe.respond_as_web_page(
			_("Workflow action was not applied"),
			frappe.utils.escape_html(str(error)),
			http_status_code=409,
			indicator_color="red",
		)
	finally:
		frappe.session.user = previous_user


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

	if not verify_request():
		return
	workflow = _source_workflow(doctype, docname)
	action = localization.action_name(workflow, action)
	current_state = localization.state_name(workflow, current_state)
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
	if not user:
		return
	from dinext_common.workflow_approval.api import _find_task_for_action

	task_name = _find_task_for_action(doctype, docname, action, user)
	task = frappe.get_doc("Workflow Task", task_name)
	if not _legacy_task_is_eligible(task):
		_show_expired_link()
		return
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

	if not verify_request():
		return
	action = localization.action_name(_source_workflow(doctype, docname), action)
	if not is_engine_enabled():
		from frappe.workflow.doctype.workflow_action.workflow_action import (
			confirm_action as core_confirm_action,
		)

		return core_confirm_action(doctype, docname, user, action)

	from dinext_common.workflow_approval.api import _find_task_for_action

	task_name = _find_task_for_action(doctype, docname, action, user)
	task = frappe.get_doc("Workflow Task", task_name)
	if not _legacy_task_is_eligible(task):
		_show_expired_link()
		return
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


def _source_workflow(doctype: str, name: str) -> str | None:
	from dinext_common.workflow_approval.scenarios import service
	if service.is_ready():
		return service.get_context(frappe.get_doc(doctype, name))["workflow"]
	return get_workflow_name(doctype)


def _scenario_task_current(source, task) -> bool:
	from dinext_common.workflow_approval.scenarios.service import task_is_current
	return task_is_current(source, task)


def _legacy_task_is_eligible(task) -> bool:
	"""A document/action URL predates per-task URLs; bind it to migrated task IDs."""
	if _configuration_restored(task):
		return False
	from dinext_common.workflow_approval.scenarios import service
	if not service.is_ready():
		return True
	if not task.get("workflow_process"):
		return False
	process = frappe.get_doc("Workflow Process",task.workflow_process)
	try:
		return task.name in json.loads(process.get("legacy_task_names") or "[]")
	except (TypeError,ValueError):
		return False
