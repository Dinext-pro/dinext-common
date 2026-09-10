import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestWorkflowApprovalPermissions(unittest.TestCase):
	def permissions(self):
		try:
			from dinext_common.workflow_approval import permissions
		except (ImportError, ModuleNotFoundError) as exc:
			self.fail(f"workflow approval permissions module is missing: {exc}")
		return permissions

	def task(self, **overrides):
		values = {
			"name": "WT-001",
			"approver": "alice@example.com",
			"user": "alice@example.com",
			"workflow": "Example Workflow",
			"reference_doctype": "Example",
			"reference_name": "EX-001",
			"source_deleted_at": None,
		}
		values.update(overrides)
		return SimpleNamespace(**values)

	def test_standard_list_is_denied_except_system_manager(self):
		permissions = self.permissions()

		with patch.object(permissions.frappe, "get_roles", return_value=["Desk User"]):
			self.assertEqual(
				permissions.get_workflow_task_query_conditions("alice@example.com"),
				"1=0",
			)
		with patch.object(permissions.frappe, "get_roles", return_value=["System Manager"]):
			self.assertEqual(
				permissions.get_workflow_task_query_conditions("manager@example.com"),
				"",
			)
		self.assertEqual(permissions.get_workflow_task_query_conditions("Administrator"), "")

	def test_approver_can_read_task_only_with_source_permission(self):
		permissions = self.permissions()
		task = self.task()

		with patch.object(permissions, "_has_source_read_permission", return_value=True):
			self.assertTrue(
				permissions.has_workflow_task_permission(task, "read", "alice@example.com")
			)
		with patch.object(permissions, "_has_source_read_permission", return_value=False):
			self.assertFalse(
				permissions.has_workflow_task_permission(task, "read", "alice@example.com")
			)

	def test_direct_task_mutations_are_denied(self):
		permissions = self.permissions()

		for permission_type in ("create", "write", "delete", "share", "submit", "cancel"):
			self.assertFalse(
				permissions.has_workflow_task_permission(
					self.task(),
					permission_type,
					"Administrator",
				)
			)

	def test_deleted_source_history_is_visible_only_to_approver_or_system_manager(self):
		permissions = self.permissions()
		task = self.task(source_deleted_at="2026-01-02")

		self.assertTrue(permissions.has_workflow_task_permission(task, "read", "alice@example.com"))
		with patch.object(permissions.frappe, "get_roles", return_value=["Approval Monitor"]):
			self.assertFalse(
				permissions.has_workflow_task_permission(task, "read", "monitor@example.com")
			)
		with patch.object(permissions.frappe, "get_roles", return_value=["System Manager"]):
			self.assertTrue(
				permissions.has_workflow_task_permission(task, "read", "manager@example.com")
			)

	def test_monitor_requires_workflow_role_and_source_permission(self):
		permissions = self.permissions()
		task = self.task()

		with (
			patch.object(permissions, "_is_workflow_monitor", return_value=True),
			patch.object(permissions, "_has_source_read_permission", return_value=True),
		):
			self.assertTrue(
				permissions.has_workflow_task_permission(task, "read", "monitor@example.com")
			)
		with (
			patch.object(permissions, "_is_workflow_monitor", return_value=True),
			patch.object(permissions, "_has_source_read_permission", return_value=False),
		):
			self.assertFalse(
				permissions.has_workflow_task_permission(task, "read", "monitor@example.com")
			)

	def test_workflow_action_requires_core_access_and_linked_task_access(self):
		permissions = self.permissions()
		action = SimpleNamespace(
			user="alice@example.com",
			permitted_roles=[],
			custom_workflow_task="WT-001",
		)
		linked_task = self.task()
		mock_frappe = MagicMock()
		mock_frappe.get_doc.return_value = linked_task
		mock_frappe.get_roles.return_value = ["Desk User"]

		with (
			patch.object(permissions, "frappe", mock_frappe),
			patch.object(permissions, "has_workflow_task_permission", return_value=True),
		):
			self.assertTrue(
				permissions.has_workflow_action_permission(action, "read", "alice@example.com")
			)

	def test_role_holder_without_task_is_denied_when_engine_enabled(self):
		permissions = self.permissions()
		action = SimpleNamespace(
			user=None,
			permitted_roles=[SimpleNamespace(role="Manager")],
			custom_workflow_task=None,
		)

		with (
			patch.object(permissions.frappe, "get_roles", return_value=["Manager"]),
			patch(
				"dinext_common.workflow_approval.lifecycle.is_engine_enabled",
				return_value=True,
			),
		):
			self.assertFalse(
				permissions.has_workflow_action_permission(action, "read", "manager@example.com")
			)
