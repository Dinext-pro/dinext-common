"""Recheck workflow mail authorization at the native queue's send boundary."""

import re
from contextlib import contextmanager
from email.utils import parseaddr
from smtplib import SMTPServerDisconnected
from urllib.parse import unquote

import frappe
from frappe import _
from frappe.email.doctype.email_queue.email_queue import EmailQueue

from dinext_common.workflow_approval.email_access import (
	SCOPE_HEADER,
	SENDER_ADDRESS,
	authorization_signature,
	authorized_source,
)
from dinext_common.workflow_approval.email_preferences import email_allowed

SCOPE_LINE = re.compile(rf"(?im)^{SCOPE_HEADER}:[ \t]*(.*(?:\r?\n[ \t]+[^\r\n]*)*)\r?\n")
DELIVERY_ID = re.compile(r"[0-9a-f]{64}(?:@[^\s]+)?")


@contextmanager
def _committed_permissions():
	# Email Queue.flush may have opened its read snapshot before acquiring the queue row lock.
	previous_db, previous_cache = frappe.local.db, frappe.local.cache
	frappe.connect(set_admin_as_user=False)
	authorization_db = frappe.local.db
	frappe.local.cache = {}
	try:
		yield
	finally:
		frappe.local.db, frappe.local.cache = previous_db, previous_cache
		authorization_db.close()


class DinextWorkflowEmailQueue(EmailQueue):
	def send(self, smtp_server_instance=None, force_send=False):
		message = self.message or ""
		separator = re.search(r"\r?\n\r?\n", message)
		scope = SCOPE_LINE.search(message, 0, separator.end() if separator else len(message))
		is_workflow_mail = scope or (
			DELIVERY_ID.fullmatch(self.message_id or "") and parseaddr(self.sender or "")[1] == SENDER_ADDRESS
		)
		if not is_workflow_mail:
			return super().send(smtp_server_instance=smtp_server_instance, force_send=force_send)
		if not force_send and not self.can_send_now():
			return None
		authorized = False
		if scope:
			with _committed_permissions():
				authorized = self._delivery_is_authorized(scope[1])
		if not authorized:
			self.update_status(status="Error", error=_("Workflow mail recipient authorization could not be verified."))
			return None

		# Keep the scope in the queue for subsequent attempts, outside the SMTP payload.
		self.message = message[:scope.start()] + message[scope.end():]
		try:
			return super().send(smtp_server_instance=smtp_server_instance, force_send=force_send)
		except (SMTPServerDisconnected, ConnectionError, TimeoutError):
			self.update_db(commit=True, error=_(
				"SMTP connection lost. Delivery is uncertain. A retry may deliver a duplicate with the same Message-ID."
			))
			raise
		finally:
			self.message = message

	def _delivery_is_authorized(self, scope):
		parts = scope.split()
		if len(parts) < 4 or parts[0] != "1":
			return False
		_, encoded_user, signature, *task_names = parts
		user = unquote(encoded_user)
		account = frappe.db.get_value("User", user, ["enabled", "email"], as_dict=True)
		if not (
			account and account.enabled and account.email and email_allowed(user)
			and parseaddr(self.sender or "")[1] == SENDER_ADDRESS
			and {row.recipient for row in self.recipients} == {account.email}
		):
			return False
		sources = []
		for name in task_names:
			try:
				task = frappe.get_doc("Workflow Task", unquote(name))
			except frappe.DoesNotExistError:
				return False
			source = authorized_source(task, user)
			if source is None:
				return False
			sources.append(source)
		return signature == authorization_signature(user, sources)
