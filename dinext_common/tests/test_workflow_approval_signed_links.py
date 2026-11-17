from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from redis.exceptions import ConnectionError as RedisConnectionError

from dinext_common.workflow_approval import signed_links


class TestWorkflowApprovalSignedLinks(FrappeTestCase):
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
