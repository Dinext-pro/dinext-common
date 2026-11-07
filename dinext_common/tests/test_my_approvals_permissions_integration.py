"""Exercise standard Frappe endpoints against synthetic private source records."""
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.client import get, get_list
from frappe.tests.utils import FrappeTestCase

from dinext_common.workflow_approval import permissions
from dinext_common.tests.ui_test_helpers import _ensure_user, _ensure_role

PREFIX = "_Test Approval Audit "


class TestMyApprovalsStandardPermissions(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.alice = "audit.alice@example.invalid"
		self.bob = "audit.bob@example.invalid"
		self.monitor = "audit.monitor@example.invalid"
		self.manager = "audit.manager@example.invalid"
		self.role = PREFIX + "Monitor"
		_ensure_role(self.role)
		for user, roles in [(self.alice, []), (self.bob, []), (self.monitor, [self.role]), (self.manager, ["System Manager"])]:
			_ensure_user(user, user.split("@")[0], ["Desk User", *roles])
		self._cleanup_rows()
		self.workflow = PREFIX + "Workflow"
		frappe.get_doc({"doctype": "Workflow", "name": self.workflow, "workflow_name": self.workflow, "document_type": "Note"}).db_insert()
		frappe.get_doc({"doctype": "Has Role", "parent": self.workflow, "parenttype": "Workflow",
			"parentfield": "custom_approval_monitor_roles", "role": self.role}).db_insert()
		self.source = frappe.get_doc({"doctype": "Note", "name": PREFIX + "Private",
			"title": PREFIX + "Private", "owner": self.alice, "public": 0, "content": "Private source"})
		self.source.db_insert()
		frappe.db.set_value("Note", self.source.name, "owner", self.alice)
		self.task = frappe.get_doc({"doctype": "Workflow Task", "name": PREFIX + "Task",
			"approver": self.alice, "user": self.alice, "owner": self.alice,
			"doc": "Note", "wt_docname": self.source.name,
			"reference_doctype": "Note", "reference_name": self.source.name, "workflow": self.workflow,
			"round_manifest": json.dumps({"transitions": []}), "vote_comment": "Private decision",
			"source_title": "Private source snapshot", "approval_round_id": PREFIX + "Round",
			"status": "Working", "round_status": "Open"})
		self.task.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		self._cleanup_rows()
		super().tearDown()

	def _cleanup_rows(self):
		frappe.db.delete("User Permission", {"user": ["in", [self.alice, self.bob, self.monitor, self.manager]]})
		for user in (self.alice, self.bob, self.monitor, self.manager):
			frappe.cache.hdel("user_permissions", user)
		frappe.db.delete("DocShare", {"share_name": ["like", PREFIX + "%"]})
		frappe.db.delete("Workflow Task", {"name": ["like", PREFIX + "%"]})
		frappe.db.delete("Note", {"name": PREFIX + "Private"})
		frappe.db.delete("Has Role", {"parent": PREFIX + "Workflow", "parenttype": "Workflow"})
		frappe.db.delete("Workflow", {"name": ["like", PREFIX + "%"]})

	def _visible(self, user):
		frappe.set_user(user)
		return get_list("Workflow Task", filters={"name": self.task.name}, fields=["name", "vote_comment"])

	def _assert_denied(self, user):
		self.assertEqual(self._visible(user), [])
		with self.assertRaises(frappe.PermissionError):
			get("Workflow Task", self.task.name)

	def test_standard_direct_and_list_deny_foreign_source_and_assignment(self):
		self.assertEqual([row.name for row in self._visible(self.alice)], [self.task.name])
		self.assertEqual(get("Workflow Task", self.task.name)["vote_comment"], "Private decision")
		self._assert_denied(self.bob)
		self._assert_denied(self.monitor)
		self._assert_denied(self.manager)

	def test_source_share_grants_monitor_read_but_task_share_does_not_bypass_policy(self):
		frappe.share.add("Workflow Task", self.task.name, self.bob, read=1, write=1,
			flags={"ignore_share_permission": True})
		self._assert_denied(self.bob)
		frappe.set_user("Administrator")
		frappe.share.add("Note", self.source.name, self.monitor, read=1)
		self.assertEqual([row.name for row in self._visible(self.monitor)], [self.task.name])
		self.assertEqual(get("Workflow Task", self.task.name)["name"], self.task.name)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Workflow Task", self.task.name).check_permission("write")
		frappe.set_user("Administrator")
		frappe.share.remove("Note", self.source.name, self.monitor)
		self._assert_denied(self.monitor)

	def test_monitor_role_is_specific_to_workflow_and_archive_is_specific_to_approver(self):
		frappe.db.set_value("Note", self.source.name, "public", 1)
		self.assertEqual(len(self._visible(self.monitor)), 1)
		frappe.set_user("Administrator")
		frappe.db.set_value("Workflow Task", self.task.name, "workflow", PREFIX + "Other")
		self._assert_denied(self.monitor)
		frappe.set_user("Administrator")
		frappe.db.set_value("Workflow Task", self.task.name, "source_deleted_at", frappe.utils.now_datetime())
		self.assertEqual(len(self._visible(self.alice)), 1)
		self.assertEqual(len(self._visible(self.manager)), 1)
		self._assert_denied(self.bob)
		self._assert_denied(self.monitor)

	def test_explicit_user_source_check_preserves_active_session(self):
		frappe.set_user(self.bob)
		sid = frappe.session.sid
		self.assertTrue(permissions._has_source_read_permission(self.task, self.alice))
		self.assertEqual(frappe.session.user, self.bob)
		self.assertEqual(frappe.session.sid, sid)

	def test_control_card_and_drilldown_share_rolling_timestamp_boundary(self):
		from dinext_common.workflow_approval import api
		from dinext_common.dinext_common.report.approval_duration import approval_duration

		frappe.share.add("Note", self.source.name, self.monitor, read=1)
		now = datetime(2026, 11, 7, 13, 15, 42)
		cutoff = now - timedelta(days=30)
		for index, stamp in enumerate([cutoff - timedelta(seconds=1), cutoff, cutoff + timedelta(seconds=1)]):
			name = PREFIX + f"Boundary-{index}"
			frappe.db.delete("Workflow Task", {"name": name})
			frappe.get_doc({"doctype": "Workflow Task", "name": name,
				"doc": "Note", "wt_docname": self.source.name, "reference_doctype": "Note",
				"reference_name": self.source.name, "workflow": self.workflow,
				"approver": self.alice, "user": self.alice, "status": "Completed",
				"completion_source": "Manual", "completed_at": stamp, "creation": stamp,
				"round_status": "Transitioned", "approval_round_id": name, "round_manifest": "{}"}).db_insert()
		frappe.set_user(self.monitor)
		with patch.object(api, "now_datetime", return_value=now), patch.object(approval_duration, "now_datetime", return_value=now):
			card = api.control_decision_count()
			rows = approval_duration.execute(card["route_options"])[1]
		self.assertEqual(card["value"], 2)
		self.assertEqual(sum(row["manual_count"] for row in rows), 2)

	def test_linked_user_permission_and_task_share_cannot_restore_denied_list_row(self):
		frappe.get_doc({"doctype": "User Permission", "user": self.bob,
			"allow": "Workflow", "for_value": self.workflow,
			"apply_to_all_doctypes": 0, "applicable_for": "Workflow Task"}).insert(ignore_permissions=True)
		frappe.share.add("Workflow Task", self.task.name, self.bob, read=1,
			flags={"ignore_share_permission": True})
		self._assert_denied(self.bob)
		# Explicit trusted queries remain available to internal audit services.
		self.assertEqual([row.name for row in frappe.get_all("Workflow Task",
			filters={"name": self.task.name}, fields=["name"])], [self.task.name])

	def test_task_policy_preserves_standard_linked_user_constraints(self):
		other = PREFIX + "Other Workflow"
		frappe.db.delete("Workflow", {"name": other})
		frappe.get_doc({"doctype": "Workflow", "name": other,
			"workflow_name": other, "document_type": "Note"}).db_insert()
		frappe.get_doc({"doctype": "User Permission", "user": self.alice,
			"allow": "Workflow", "for_value": other,
			"apply_to_all_doctypes": 0, "applicable_for": "Workflow Task"}).insert(ignore_permissions=True)
		self._assert_denied(self.alice)

	def test_unrelated_note_sharing_still_works(self):
		frappe.share.add("Note", self.source.name, self.bob, read=1)
		frappe.set_user(self.bob)
		self.assertEqual([row.name for row in get_list("Note",
			filters={"name": self.source.name}, fields=["name"])], [self.source.name])
		self.assertEqual(get("Note", self.source.name)["name"], self.source.name)

	@contextmanager
	def _task_role_constraint(self, *, owner_only=False):
		created = []
		try:
			roles = [("System Manager", False)]
			if owner_only:
				roles.append(("All", True))
			for role, if_owner in roles:
				permission = frappe.get_doc({"doctype": "Custom DocPerm", "parent": "Workflow Task",
					"parenttype": "DocType", "parentfield": "permissions", "role": role,
					"read": 1, "if_owner": int(if_owner), "permlevel": 0})
				permission.db_insert()
				created.append(permission.name)
			frappe.clear_cache(doctype="Workflow Task")
			yield
		finally:
			frappe.db.delete("Custom DocPerm", {"name": ["in", created]})
			frappe.clear_cache(doctype="Workflow Task")

	def test_owner_constraint_and_task_share_do_not_restore_denied_row(self):
		frappe.share.add("Workflow Task", self.task.name, self.bob, read=1,
			flags={"ignore_share_permission": True})
		with self._task_role_constraint(owner_only=True):
			self._assert_denied(self.bob)

	def test_only_shared_task_still_requires_approval_policy(self):
		frappe.share.add("Workflow Task", self.task.name, self.bob, read=1,
			flags={"ignore_share_permission": True})
		with self._task_role_constraint():
			self._assert_denied(self.bob)

	def test_standard_task_list_fails_closed_without_final_platform_capability(self):
		from frappe.model.db_query import DatabaseQuery

		with patch.object(DatabaseQuery, "final_permission_query_conditions_version", 0, create=True):
			with self.assertRaises(frappe.PermissionError):
				self._visible(self.alice)
			self.assertEqual([row.name for row in frappe.get_all("Workflow Task",
				filters={"name": self.task.name}, fields=["name"])], [self.task.name])
