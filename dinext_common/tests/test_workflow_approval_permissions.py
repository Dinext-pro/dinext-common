import unittest
from types import SimpleNamespace
from unittest.mock import patch


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

	def test_generic_approval_cards_do_not_grant_edit_access_from_workflow_task(self):
		permissions = self.permissions()
		card = {
			"name": "My open approvals",
			"module": "Dinext Common",
			"document_type": "Workflow Task",
			"is_standard": 1,
			"is_public": 1,
		}
		user = "manager@example.com"
		with patch.object(permissions.frappe, "get_roles", return_value=["Dashboard Manager"]):
			self.assertTrue(permissions.has_public_number_card_permission(card, "read", user))
			self.assertIs(permissions.has_public_number_card_permission(card, "write", user), False)
			self.assertIsNone(permissions.has_public_number_card_permission({**card, "is_standard": 0}, "write", user))
		with patch.object(permissions.frappe, "get_roles", return_value=["System Manager"]):
			self.assertIs(permissions.has_public_number_card_permission(card, "write", user), True)

	def test_monitoring_card_list_scope_matches_individual_card_read(self):
		permissions = self.permissions()
		user = "approver@example.com"
		with (
			patch.object(permissions.frappe, "get_roles", return_value=["Desk User"]),
			patch.object(permissions, "get_monitorable_workflows", return_value=[]) as monitored,
		):
			condition = permissions.get_approval_number_card_query_conditions(user)
			self.assertIn("NOT IN", condition)
			for name in permissions.MONITORING_APPROVAL_NUMBER_CARDS:
				self.assertIn(name, condition)
			self.assertNotIn("My open approvals", condition)
			monitored.return_value = ["Example Workflow"]
			self.assertIsNone(permissions.get_approval_number_card_query_conditions(user))

	def test_workflow_documents_use_standard_permission_hooks(self):
		from dinext_common import hooks

		for doctype in ("Workflow Action",):
			self.assertNotIn(doctype, hooks.has_permission)
			self.assertNotIn(doctype, getattr(hooks, "permission_query_conditions", {}))

		self.assertIn("Workflow Task", hooks.has_permission)
		self.assertIn("Workflow Task", hooks.permission_query_conditions)
		self.assertIn("Workflow Task", hooks.final_permission_query_conditions)

	def test_loading_app_hooks_preserves_core_workflow_action_filter(self):
		from importlib import reload

		from frappe.workflow.doctype.workflow_action import workflow_action

		from dinext_common import hooks

		core_filter = workflow_action.get_permission_query_conditions
		reload(hooks)
		self.assertIs(workflow_action.get_permission_query_conditions, core_filter)
		self.assertFalse(getattr(core_filter, "_dinext_relaxed", False))

	def test_core_workflow_action_filter_keeps_open_role_or_user_rules(self):
		from frappe.workflow.doctype.workflow_action import workflow_action

		with (
			patch.object(workflow_action.frappe, "get_roles", return_value=["Desk User"]),
			patch.object(workflow_action.frappe.db, "escape", return_value="'alice@example.com'"),
		):
			condition = workflow_action.get_permission_query_conditions("alice@example.com")

		self.assertIn("Workflow Action Permitted Role", condition)
		self.assertIn("Desk User", condition)
		self.assertIn("`tabWorkflow Action`.`user`='alice@example.com'", condition)
		self.assertIn("`tabWorkflow Action`.`status`='Open'", condition)
		self.assertEqual(workflow_action.get_permission_query_conditions("Administrator"), "")

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

	def test_timesheet_role_overrides_restore_read_only_base_once(self):
		permissions = self.permissions()
		frappe = permissions.frappe
		with (
			patch.dict(frappe.conf, {"enable_parallel_workflow_approval": 1}),
			patch.object(permissions, "supports_final_task_permission_queries", return_value=True),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", side_effect=[None, frappe._dict(name="base", read=1, report=1)]),
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(frappe, "clear_cache") as clear_cache,
		):
			permissions.restore_workflow_task_base_read()
			permissions.restore_workflow_task_base_read()

		get_doc.assert_called_once_with({
			"doctype": "Custom DocPerm", "parenttype": "DocType", "parentfield": "permissions",
			"parent": "Workflow Task", "role": "All", "permlevel": 0, "if_owner": 0, "read": 1, "report": 1,
		})
		get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
		clear_cache.assert_called_once_with(doctype="Workflow Task")

	def test_existing_timesheet_base_read_recovers_standard_report_right(self):
		permissions = self.permissions()
		frappe = permissions.frappe
		with (
			patch.object(permissions, "supports_final_task_permission_queries", return_value=True),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", return_value=frappe._dict(name="base", read=1, report=0)),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(frappe, "clear_cache") as clear_cache,
		):
			permissions.restore_workflow_task_base_read(during_cutover=True)

		set_value.assert_called_once_with("Custom DocPerm", "base", {"report": 1})
		clear_cache.assert_called_once_with(doctype="Workflow Task")

	def test_timesheet_role_overrides_are_retained_with_legacy_platform_or_engine(self):
		permissions = self.permissions()
		frappe = permissions.frappe
		with (
			patch.dict(frappe.conf, {"enable_parallel_workflow_approval": 0}),
			patch.object(permissions, "supports_final_task_permission_queries", return_value=False),
			patch.object(frappe.db, "exists") as exists,
		):
			permissions.restore_workflow_task_base_read()
			permissions.restore_workflow_task_base_read(during_cutover=True)
		exists.assert_not_called()

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

	def test_system_manager_controls_still_require_source_permission(self):
		permissions = self.permissions()
		visible = {"workflow": "Workflow A", "reference_doctype": "Issue", "reference_name": "VISIBLE"}
		hidden = {"workflow": "Workflow B", "reference_doctype": "Issue", "reference_name": "HIDDEN"}
		with (
			patch.object(permissions.frappe, "get_roles", return_value=["System Manager"]),
			patch.object(permissions, "_is_workflow_monitor", return_value=False),
			patch.object(
				permissions, "_has_source_read_permission",
				side_effect=lambda task, _user: task["reference_name"] == "VISIBLE",
			),
		):
			can_read = permissions.get_task_read_checker("manager@example.invalid", monitored_only=True)
			self.assertTrue(can_read(visible))
			self.assertFalse(can_read(hidden))
