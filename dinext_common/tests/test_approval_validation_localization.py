"""Real approval API validation against isolated synthetic workflows."""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.wrappers import Request

from dinext_common.tests import approval_audit_ui as fixture
from dinext_common.workflow_approval import api, policy


class TestApprovalValidationLocalization(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.fixture = fixture.seed()
		self.task = self.fixture["tasks"]["Main"]
		self.round_id = frappe.db.get_value("Workflow Task", self.task, "approval_round_id")
		self.request = patch.object(frappe.local, "request", Request.from_values(method="POST"), create=True)
		self.request.start()
		self.previous_language = frappe.local.lang
		frappe.local.message_log = []

	def tearDown(self):
		self.request.stop()
		frappe.local.lang = self.previous_language
		frappe.set_user("Administrator")
		fixture.cleanup()
		frappe.local.message_log = []

	def _snapshot(self):
		return frappe.get_all("Workflow Task", filters={"workflow": fixture.WORKFLOW},
			fields=["name", "status", "round_status", "modified", "vote_comment", "cancellation_reason"], order_by="name")

	def _cases(self, language):
		return [("<p>&nbsp;</p>", "Для этого действия процесса требуется комментарий" if language == "ru"
			else "A comment is required for this workflow action"),
			("x" * 4001, "Комментарий процесса не может превышать 4000 символов" if language == "ru"
			else "Workflow comments cannot exceed 4000 characters")]

	def test_single_and_bulk_validation_is_localized_without_task_writes(self):
		before = self._snapshot()
		for language in ("ru", "en"):
			frappe.set_user(fixture.ALICE)
			frappe.local.lang = language
			for comment, message in self._cases(language):
				for method, args in [(api.vote, {"task_name": self.task}),
					(api.apply_workflow, {"doc": {"doctype": "Note", "name": fixture.PREFIX + "Main"}, "action": "Approve"})]:
					frappe.local.message_log = []
					with self.subTest(language=language, method=method.__name__, size=len(comment)):
						with self.assertRaises(frappe.ValidationError) as caught:
							method(**args, transition_uuid=self.fixture["transition_uuid"], comment=comment)
						self.assertEqual(str(caught.exception), message)
						self.assertEqual(frappe.local.message_log[-1]["message"], message)
						self.assertEqual(self._snapshot(), before)
				frappe.local.message_log = [frappe._dict(message="Earlier message")]
				result = api.bulk_task_vote([{"task_name": self.task, "transition_uuid": self.fixture["transition_uuid"]}], comment=comment)
				self.assertEqual(result["succeeded"], [])
				self.assertEqual(result["failed"][0]["error"], message)
				self.assertEqual(frappe.local.message_log, [{"message": "Earlier message"}])
				self.assertEqual(self._snapshot(), before)

	def test_invalid_reset_reasons_are_localized_before_any_task_write(self):
		before = self._snapshot()
		for language in ("ru", "en"):
			frappe.set_user("Administrator")
			frappe.local.lang = language
			for reason, message in self._cases(language):
				for method, identifier in [(api.reset_round, self.round_id), (api.reset_rounds, [self.round_id])]:
					frappe.local.message_log = []
					with self.subTest(language=language, method=method.__name__, size=len(reason)):
						with self.assertRaises(frappe.ValidationError) as caught:
							method(identifier, reason)
						self.assertEqual(str(caught.exception), message)
						self.assertEqual(frappe.local.message_log[-1]["message"], message)
						self.assertEqual(self._snapshot(), before)

	def _mixed_bulk(self, language):
		frappe.share.add("Note", fixture.PREFIX + "Denied", fixture.ALICE, read=1)
		frappe.db.commit()
		frappe.set_user(fixture.ALICE)
		frappe.local.lang = language
		raw = "&amp;lt;b&amp;gt;&amp;lt;/b&amp;gt;"
		before = frappe.get_doc("Workflow Task", self.fixture["tasks"]["Denied"]).as_dict()
		result = api.bulk_task_vote([
			{"task_name": self.task, "transition_uuid": self.fixture["transition_uuid"], "comment": raw},
			{"task_name": self.fixture["tasks"]["Denied"], "transition_uuid": self.fixture["transition_uuid"], "comment": " "},
		])
		self.assertEqual(len(result["succeeded"]), 1)
		self.assertEqual(result["failed"][0]["error"], self._cases(language)[0][1])
		self.assertFalse(frappe.local.message_log)
		self.assertEqual(frappe.db.get_value("Workflow Task", self.task, "vote_comment"), policy.normalize_comment(raw))
		self.assertEqual(frappe.get_doc("Workflow Task", before.name).as_dict(), before)

	def test_mixed_bulk_russian_preserves_success_and_has_no_duplicate_messages(self):
		self._mixed_bulk("ru")

	def test_mixed_bulk_english_preserves_success_and_has_no_duplicate_messages(self):
		self._mixed_bulk("en")

	def test_batch_reset_normalizes_nested_entities_once(self):
		raw = "&amp;lt;b&amp;gt;&amp;lt;/b&amp;gt;"
		result = api.reset_rounds([self.round_id], raw)
		self.assertEqual(result, {"succeeded": [self.round_id], "failed": []})
		reason = frappe.db.get_value("Workflow Task", self.task, "cancellation_reason")
		self.assertTrue(reason.endswith(policy.normalize_comment(raw)), reason)
