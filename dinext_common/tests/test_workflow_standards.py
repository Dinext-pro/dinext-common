"""Regressions from the full Workflow standards audit."""

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import frappe
from frappe.translate import print_language


class TestWorkflowStandards(unittest.TestCase):
	def test_healthy_round_does_not_load_every_task_or_projection(self):
		from dinext_common.workflow_approval.projections import repair_round_projections

		with (
			patch.object(frappe, "get_all", side_effect=[
				[frappe._dict(name="WT-1", approver="marina@example.com")],
				["WT-1"],
				[frappe._dict(reference_name="WT-1", allocated_to="marina@example.com")],
			]),
			patch.object(frappe, "get_doc") as load,
		):
			repair_round_projections(object(), "round")
		load.assert_not_called()

	def test_cleanup_denies_non_manager_before_reading_rules(self):
		from dinext_common.workflow_approval import retention

		with (
			patch.dict(frappe.session, {"user": "ordinary.workflow@example.com"}),
			patch.dict(frappe.flags, {"in_test": False}),
			patch.object(frappe, "get_roles", return_value=["Desk User"]),
			patch.object(frappe, "get_single") as read,
			patch.object(retention, "_delete_terminal_round") as delete,
			self.assertRaises(frappe.PermissionError),
		):
			retention.cleanup_workflow_approval_rounds()
		read.assert_not_called()
		delete.assert_not_called()

	def test_cleanup_allows_manager_directly_and_only_post_over_http(self):
		from dinext_common.workflow_approval import retention

		with patch.object(frappe.db, "table_exists", return_value=False):
			self.assertEqual(retention.cleanup_workflow_approval_rounds(), 0)
		method = retention.cleanup_workflow_approval_rounds
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ["POST"])

	def test_daily_deadline_digest_requires_time_but_hours_does_not(self):
		from dinext_common.tests.test_workflow_deadline_settings import workflow
		from dinext_common.workflow_approval.deadlines.metadata import prepare_settings

		for unit in ("Days", "Working Days"):
			with self.subTest(unit=unit), self.assertRaisesRegex(ValueError, "send time"):
				prepare_settings(
					workflow(custom_deadline_interval_unit=unit, custom_deadline_send_times="  "),
					extensions={"sending_intervals": {"Working Days": {"integer": True}}},
				)
		w = workflow(custom_deadline_interval_unit="Hours", custom_deadline_send_times="")
		prepare_settings(w, extensions={})
		self.assertEqual(w.transitions[0].custom_deadline_send_times, "")

	def test_standard_deadline_diagnostics_follow_report_language(self):
		from dinext_common.workflow_approval.deadlines.report import display_deadline_error

		with print_language("ru"):
			translated = display_deadline_error("Original assignment time is unknown")
			self.assertNotEqual(translated, "Original assignment time is unknown")
			self.assertEqual(translated, frappe._("Original assignment time is unknown"))
			self.assertEqual(
				display_deadline_error("Worker is missing for user marina@example.com"),
				frappe._("Worker is missing for user {0}").format("marina@example.com"),
			)
			self.assertEqual(
				display_deadline_error("Unknown deadline interval: Example"),
				frappe._("Unknown deadline interval: {0}").format("Example"),
			)
			self.assertNotEqual(display_deadline_error("Unknown deadline interval: Example"), "Unknown deadline interval: Example")
		with print_language("en"):
			self.assertEqual(display_deadline_error(translated), "Original assignment time is unknown")
			self.assertEqual(display_deadline_error("Custom provider: check 42"), "Custom provider: check 42")

	def test_rejected_removed_choice_does_not_commit_callers_transaction(self):
		from dinext_common.workflow_approval import engine

		task = frappe._dict(
			name="audit-task", approver="Administrator", status="Working", round_status="Open",
			workflow="Audit workflow", workflow_state="Open", approval_round_id="audit-round",
		)
		task.check_permission = MagicMock()
		task.reload = MagicMock()
		source = MagicMock()
		classification = {"void": False, "dropped": ["removed"], "add": []}
		with ExitStack() as stack:
			stack.enter_context(patch.object(frappe.db, "get_value", side_effect=[
				frappe._dict(reference_doctype="Issue", reference_name="audit-source"), 1,
			]))
			stack.enter_context(patch.object(frappe, "get_doc", side_effect=[source, task]))
			stack.enter_context(patch.object(engine, "_lock_domain_dependencies"))
			stack.enter_context(patch("dinext_common.workflow_approval.scenarios.service.validate_task"))
			stack.enter_context(patch.object(engine, "_workflow_context", return_value=(
				"Audit workflow", object(), "status", "Open",
			)))
			stack.enter_context(patch.object(engine, "_parse_manifest", return_value={}))
			stack.enter_context(patch.object(engine, "_classify_round", return_value=classification))
			stack.enter_context(patch.object(engine, "_amend_open_round", return_value=False))
			stack.enter_context(patch.object(engine, "_task_transition", side_effect=engine.WorkflowApprovalConflictError))
			stack.enter_context(patch.dict(frappe.flags, {"in_test": False}))
			commit = stack.enter_context(patch.object(frappe.db, "commit"))
			after_rollback = stack.enter_context(patch.object(frappe.db, "after_rollback"))
			with self.assertRaises(engine.WorkflowApprovalConflictError):
				engine.cast_vote(task.name, transition_uuid="removed")
			commit.assert_not_called()
			after_rollback.add.assert_called_once()
