from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
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


class TestLegacySignedActionAliases(TestCase):
	def setUp(self):
		self.workflow = "Synthetic position approval"
		self.user = "reviewer@example.test"
		self.row = frappe._dict(state="Review", action="Edit", next_state="Draft", transition_uuid="edit-id")
		self.task = frappe._dict(name="old-task", workflow=self.workflow, workflow_state="Review",
			workflow_process="process", approver=self.user, available_workflow_transitions=[self.row])
		self.process = frappe._dict(legacy_task_names='["old-task"]')
		stack = ExitStack()
		self.addCleanup(stack.close)
		def mock(*args, **kwargs):
			return stack.enter_context(patch(*args, **kwargs))

		mock("frappe.local", SimpleNamespace(flags=frappe._dict(in_test=False), lang="en"))
		mock("frappe.translate.get_all_translations", return_value={})
		self.signature = mock(
			"dinext_common.workflow_approval.signed_links.verify_request", return_value=True
		)
		mock("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True)
		self.scenarios_ready = mock("dinext_common.workflow_approval.scenarios.service.is_ready", return_value=True)
		mock("dinext_common.workflow_approval.signed_links._source_workflow", return_value=self.workflow)
		mock("dinext_common.workflow_approval.localization._localization_hooks",
			return_value={self.workflow: ["example.rules"]})
		mock("frappe.get_attr", return_value=lambda: {
			"states": {"Old Review": "Review"},
			"legacy_signed_action_aliases": (("Review", "Stop Workflow", "Edit", "Draft"),),
		})
		mock("frappe.get_doc", side_effect=lambda dt, name: {
			("Workflow Task", self.task.name): self.task, ("Workflow Process", "process"): self.process,
		}[(dt, name)])
		self.task_names = [self.task.name]
		mock("frappe.get_all", side_effect=lambda dt, filters, **kwargs:
			self.task_names if filters["approver"] == self.task.approver else [])
		db = Mock()
		db.exists.side_effect = lambda dt, filters: any(
			row.action == filters.get("action") for row in self.task.available_workflow_transitions)
		db.get_value.return_value = "2026-01-01"
		mock("frappe.db", db)
		mock("dinext_common.workflow_approval.signed_links._open_action",
			return_value=frappe._dict(custom_delivery_key="key"))
		self.preview = mock("dinext_common.workflow_approval.signed_links._render_preview")
		self.expired = mock("dinext_common.workflow_approval.signed_links._show_expired_link")

	def apply(self):
		signed_links.apply_action("Остановить Воркфлоу", "Note", "sample", "Old Review", self.user)

	def confirm(self):
		signed_links.confirm_legacy_action("Note", "sample", self.user, "Остановить Воркфлоу")

	def test_both_signed_entry_points_resolve_the_adopted_transition(self):
		self.apply()
		self.preview.assert_called_once_with("old-task", "edit-id", self.user, "Review", None, "key")
		self.preview.reset_mock()
		self.confirm()
		self.preview.assert_called_once_with("old-task", "edit-id", self.user, "Review", "2026-01-01", "key")

	def test_exact_action_takes_precedence(self):
		self.task.available_workflow_transitions.append(frappe._dict(
			state="Review", action="Stop Workflow", next_state="Stopped", transition_uuid="stop-id"))
		self.apply()
		self.assertEqual(self.preview.call_args.args[1], "stop-id")

	def test_alias_requires_unique_child_matching_registered_route(self):
		for field, value in (("state", "Other"), ("next_state", "Other"), ("action", "Other")):
			with self.subTest(field=field), patch.dict(self.row, {field: value}):
				with self.assertRaises(signed_links.engine.WorkflowApprovalConflictError):
					self.confirm()
		self.task.available_workflow_transitions.append(self.row.copy())
		with self.assertRaises(signed_links.engine.WorkflowApprovalConflictError):
			self.confirm()
		self.preview.assert_not_called()

	def test_alias_is_confined_to_signed_actor_and_workflow(self):
		for key, value in (("approver", "other@example.test"), ("workflow", "Other"), ("workflow_state", "Other")):
			with self.subTest(key=key), patch.dict(self.task, {key: value}):
				with self.assertRaises(signed_links.engine.WorkflowApprovalConflictError):
					self.confirm()
		self.preview.assert_not_called()

	def test_alias_rejects_a_different_signed_state_or_multiple_tasks(self):
		with self.assertRaises(signed_links.engine.WorkflowApprovalConflictError):
			signed_links.apply_action("Stop Workflow", "Note", "sample", "Other", self.user)
		self.task_names.append("second-task")
		with self.assertRaises(signed_links.engine.WorkflowApprovalConflictError):
			self.confirm()
		self.preview.assert_not_called()

	def test_alias_requires_adoption_metadata(self):
		self.scenarios_ready.return_value = False
		self.confirm()
		self.expired.assert_called_once()
		self.preview.assert_not_called()

	def test_new_task_and_invalid_signature_cannot_use_alias(self):
		self.signature.return_value = False
		self.apply()
		self.confirm()
		self.signature.return_value = True
		self.process.legacy_task_names = "[]"
		self.confirm()
		self.expired.assert_called_once()
		self.preview.assert_not_called()
