from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

import frappe
from frappe.tests.utils import FrappeTestCase
from redis.exceptions import ConnectionError as RedisConnectionError
from werkzeug.datastructures import MultiDict

from dinext_common.workflow_approval import signed_links


class TestWorkflowApprovalSignedLinks(FrappeTestCase):
	def test_new_link_places_signed_preview_in_fragment(self):
		task = frappe._dict(
			name="WT-synthetic", approver="test@example.com", workflow_state="Pending",
			reference_doctype="Note", reference_name="sample",
		)
		transition = frappe._dict(transition_uuid="synthetic-transition")
		with (
			patch.object(signed_links, "_ensure_delivery_action", return_value=frappe._dict()),
			patch.object(signed_links, "_link_delivery_key", return_value="synthetic-delivery-key"),
			patch.object(signed_links, "get_url", side_effect=lambda path: "http://localhost" + path),
			patch.object(frappe.db, "get_value", return_value="2026-11-19 00:00:00"),
			patch("frappe.utils.verified_command.get_secret", return_value="synthetic-test-key"),
		):
			url = urlsplit(signed_links.get_task_action_url(task, transition))
			self.assertFalse(bool(url.query), "Email link exposed signed data in its query")
			self.assertNotIn("synthetic-delivery-key", url.path)
			body = signed_links._read_signed_email_preview(url.fragment)
			self.assertEqual(body["delivery_key"], "synthetic-delivery-key")
			self.assertEqual(body["task_name"], task.name)
			self.assertIsNone(signed_links._read_signed_email_preview(url.fragment + "changed"))

	def test_email_preview_only_accepts_one_signed_ticket_in_post_body(self):
		ticket = "test-ticket"
		payload = {"task_name": "test-task"}
		request = SimpleNamespace(
			form=MultiDict({"preview_token": ticket}), args=MultiDict({"preview_token": ticket}),
			headers={"Origin": "https://example.test"},
		)
		form_dict = frappe._dict(preview_token=ticket)
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe.local, "form_dict", form_dict, create=True),
			patch.object(signed_links, "get_url", return_value="https://example.test:443"),
			patch.object(signed_links, "_read_signed_email_preview", return_value=payload) as sign,
			patch.object(signed_links, "_render_preview") as preview,
			patch.object(signed_links, "_show_expired_link") as expired,
		):
			signed_links.preview_email_action()
			sign.assert_called_once_with(ticket)
			preview.assert_called_once_with(**payload)
			self.assertNotIn("preview_token", form_dict)
			request.form = MultiDict()
			signed_links.preview_email_action()
			expired.assert_called_once()
			request.form = MultiDict([("preview_token", ticket), ("preview_token", ticket)])
			signed_links.preview_email_action()
			self.assertEqual(expired.call_count, 2)
			request.form = MultiDict({"preview_token": ticket})
			request.headers["Origin"] = "https://other.test"
			signed_links.preview_email_action()
			del request.headers["Origin"]
			signed_links.preview_email_action()
			self.assertEqual(expired.call_count, 4)
			self.assertEqual(preview.call_count, 1)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[signed_links.open_email_action], ["GET"]
		)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[signed_links.preview_email_action], ["POST"]
		)

	def test_command_is_consumed_atomically_once(self):
		payload = {
			"task_name": "WT-test",
			"transition_uuid": "transition-test",
			"user": "test@example.com",
			"delivery_key": "delivery-test",
		}
		token = signed_links._issue_command(payload)

		self.assertEqual(signed_links._peek_command(token), payload)
		self.assertEqual(signed_links._consume_command(token), payload)
		self.assertIsNone(signed_links._consume_command(token))

	def test_preview_and_confirmation_http_methods_are_separated(self):
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[signed_links.preview_action],
			["GET"],
		)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[signed_links.confirm_action],
			["POST"],
		)

	def test_confirmation_is_retryable_while_redis_is_unavailable(self):
		with (
			patch.object(signed_links, "_peek_command", side_effect=RedisConnectionError),
			patch.object(frappe, "respond_as_web_page") as page,
			patch.object(signed_links.engine, "cast_vote") as cast_vote,
		):
			signed_links.confirm_action("test-command")
		self.assertEqual(page.call_args.kwargs["http_status_code"], 503)
		cast_vote.assert_not_called()
