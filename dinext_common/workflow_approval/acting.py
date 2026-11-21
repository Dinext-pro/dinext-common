"""Server-side identities for a Workflow decision, independent of task ownership."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import NamedTuple

import frappe
from frappe import _


class Performer(NamedTuple):
	performed_by: str | None
	performed_as: str

	@property
	def deputy(self) -> str | None:
		return self.performed_by if self.performed_by != self.performed_as else None


_request_performer: ContextVar[Performer | None] = ContextVar("workflow_request_performer", default=None)


def current() -> Performer:
	user = frappe.session.user
	performer = _request_performer.get()
	if performer is not None and performer.performed_as == user:
		return performer
	session_data = getattr(frappe.session, "data", None) or {}
	return Performer(session_data.get("impersonated_by") or user, user)


@contextmanager
def use(performer: Performer):
	token = _request_performer.set(performer)
	try:
		yield
	finally:
		_request_performer.reset(token)


def log_vote(source, task, action: str, comment: str) -> None:
	actor = task.get("performed_by")
	effective = task.get("performed_as")
	action_label = frappe.bold(frappe.utils.escape_html(_(action)))
	suffix = f": {frappe.utils.escape_html(comment)}" if comment else ""

	if actor and effective and actor != effective:
		message = _("{0} voted {1} on behalf of {2}{3}").format(
			_user_label(actor), action_label, _user_label(effective), suffix,
		)
	elif effective and not actor and task.completion_source == "Signed Link":
		message = _("{0} was recorded for {1} via an email link{2}").format(
			action_label, _user_label(effective), suffix,
		)
	else:
		message = _("{0} voted {1}{2}").format(
			frappe.bold(frappe.utils.escape_html(actor or task.approver)), action_label, suffix,
		)
	source.add_comment("Workflow", message)


def _user_label(user: str) -> str:
	return frappe.bold(frappe.utils.escape_html(frappe.get_cached_value("User", user, "full_name") or user))
