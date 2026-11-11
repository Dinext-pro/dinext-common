"""Process audit records follow source permissions and exact source identity."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe


class TestWorkflowScenarioRecords(unittest.TestCase):
	def source_record(self, **values):
		return frappe._dict(
			reference_doctype="Issue", reference_name="ISS-1", source_created_at="2026-01-02 03:04:05",
			**values,
		)

	def test_recreated_source_cannot_authorize_earlier_process(self):
		from dinext_common.workflow_approval.scenarios import records
		with patch.object(records.frappe, "db", Mock(get_value=Mock(return_value="2026-02-02 03:04:05"))), patch("dinext_common.workflow_approval.permissions._has_source_read_permission") as source_permission:
			self.assertFalse(records.has_record_permission(self.source_record(), user="reader@example.com"))
		source_permission.assert_not_called()

	def test_existing_source_must_grant_read_permission(self):
		from dinext_common.workflow_approval.scenarios import records
		source = self.source_record()
		with patch.object(records.frappe, "db", Mock(get_value=Mock(return_value="2026-01-02 03:04:05"))), patch("dinext_common.workflow_approval.permissions._has_source_read_permission", return_value=False) as source_permission:
			self.assertFalse(records.has_record_permission(source, user="reader@example.com"))
		source_permission.assert_called_once_with(source, "reader@example.com")

	def test_user_cannot_mutate_a_process_even_if_source_is_writable(self):
		from dinext_common.workflow_approval.scenarios import records
		for permission in ("write", "create", "delete", "submit", "cancel", "share"):
			self.assertFalse(records.has_record_permission(self.source_record(), ptype=permission, user="reader@example.com"))

	def test_unflagged_controller_write_is_rejected(self):
		from dinext_common.workflow_approval.scenarios import records
		with patch.object(records, "_", side_effect=lambda text: text), patch.object(records.frappe, "throw", side_effect=frappe.PermissionError), self.assertRaises(frappe.PermissionError):
			records.require_service_write(SimpleNamespace(flags=frappe._dict()))
		records.require_service_write(SimpleNamespace(flags=frappe._dict(in_workflow_scenario_service=True)))

	def test_list_query_excludes_unreadable_and_recreated_instances(self):
		from dinext_common.workflow_approval.scenarios import records
		rows = [
			self.source_record(name="current"),
			frappe._dict(name="previous", reference_doctype="Issue", reference_name="ISS-1", source_created_at="2025-01-02 03:04:05"),
			frappe._dict(name="unreadable", reference_doctype="Issue", reference_name="ISS-2", source_created_at="2026-01-02 03:04:05"),
		]
		readable_sources = [frappe._dict(name="ISS-1", creation="2026-01-02 03:04:05")]
		qb = Mock()
		qb.DocType.return_value.name.isin.return_value.get_sql.return_value = "safe-source-filter"
		with patch.object(records.frappe, "get_all", return_value=rows), patch.object(records.frappe, "get_list", return_value=readable_sources), patch.object(records.frappe, "session", frappe._dict(user="reader@example.com")), patch.object(records.frappe, "qb", qb):
			self.assertEqual(records.process_query_conditions("reader@example.com"), "safe-source-filter")
		qb.DocType.return_value.name.isin.assert_called_once_with(["current"])

	def test_explicit_reader_context_is_restored_after_failed_source_query(self):
		from dinext_common.workflow_approval.scenarios import records
		local = SimpleNamespace(user_perms={"prior": True}, role_permissions={"prior": "role"})
		session = frappe._dict(user="Administrator")
		with patch.object(records.frappe, "session", session), patch.object(records.frappe, "local", local):
			with self.assertRaises(RuntimeError):
				with records._read_as_user("reader@example.com"):
					self.assertEqual(session.user, "reader@example.com")
					self.assertIsNone(local.user_perms)
					raise RuntimeError("Source query failed")
		self.assertEqual(session.user, "Administrator")
		self.assertEqual(local.user_perms, {"prior": True})
		self.assertEqual(local.role_permissions, {"prior": "role"})
