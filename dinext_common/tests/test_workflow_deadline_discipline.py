import unittest
from datetime import datetime
from unittest.mock import patch


class TestApprovalDiscipline(unittest.TestCase):
	def test_open_overdue_is_failure_and_rebuild_is_one_observation(self):
		from dinext_common.workflow_approval.deadlines.discipline import summarize

		rows = [
			dict(
				name="old",
				deadline_assignment_id="A",
				status="Cancelled",
				deadline_due_at="2026-11-08 12:00:00",
			),
			dict(
				name="current",
				deadline_assignment_id="A",
				status="Working",
				deadline_due_at="2026-11-08 12:00:00",
			),
			dict(
				name="ok",
				deadline_assignment_id="B",
				status="Completed",
				completion_source="Manual",
				deadline_due_at="2026-11-08 12:00:00",
				completed_at="2026-11-08 11:00:00",
			),
			dict(
				name="late",
				deadline_assignment_id="C",
				status="Completed",
				completion_source="Signed Link",
				deadline_due_at="2026-11-08 12:00:00",
				completed_at="2026-11-08 13:00:00",
			),
			dict(
				name="auto",
				deadline_assignment_id="D",
				status="Completed",
				completion_source="Automatic Unchanged",
				deadline_due_at="2026-11-08 12:00:00",
				completed_at="2026-11-08 11:00:00",
			),
		]
		result = summarize(rows, from_date="2026-11-01", to_date="2026-11-30", now=datetime(2026, 11, 9))
		self.assertEqual(result["observations"], 3)
		self.assertEqual(result["open_overdue"], 1)
		self.assertEqual(result["completed_late"], 1)
		self.assertAlmostEqual(result["on_time_percent"], 100 / 3)

	def test_cohort_uses_due_date_and_errors_do_not_improve_percentage(self):
		from dinext_common.workflow_approval.deadlines.discipline import summarize

		rows = [
			dict(
				name="prior",
				deadline_assignment_id="A",
				status="Completed",
				completion_source="Manual",
				deadline_due_at="2026-10-31 12:00:00",
				completed_at="2026-11-01 11:00:00",
			),
			dict(name="bad", deadline_assignment_id="B", status="Working", deadline_error="No calendar"),
			dict(
				name="pending",
				deadline_assignment_id="C",
				status="Working",
				deadline_due_at="2026-11-30 12:00:00",
			),
		]
		result = summarize(rows, from_date="2026-11-01", to_date="2026-11-30", now=datetime(2026, 11, 9))
		self.assertIsNone(result["on_time_percent"])
		self.assertEqual(result["errors"], 1)

	def test_on_time_card_uses_one_decimal_without_changing_the_numeric_value(self):
		import frappe
		from dinext_common.workflow_approval.deadlines import discipline

		with (
			patch.object(frappe, "session", frappe._dict(user="Administrator"), create=True),
			patch.object(discipline, "metrics", return_value={"on_time_percent": 30.7692}),
		):
			card = discipline._card("on_time_percent", percent=True)

		self.assertEqual(card["value"], 30.8)
		self.assertEqual(card["fieldtype"], "Percent")
		self.assertEqual(card.get("precision"), 1)
		self.assertEqual(card["route"], ["query-report", "Approval Deadline Discipline"])

	def test_on_time_card_without_observations_remains_text(self):
		import frappe
		from dinext_common.workflow_approval.deadlines import discipline

		with (
			patch.object(frappe, "session", frappe._dict(user="Administrator"), create=True),
			patch.object(frappe, "_", side_effect=lambda value: value),
			patch.object(discipline, "metrics", return_value={"on_time_percent": None}),
		):
			card = discipline._card("on_time_percent", percent=True)

		self.assertEqual(card["value"], "No observations")
		self.assertEqual(card["fieldtype"], "Data")
		self.assertNotIn("precision", card)

	def test_deadline_shortcut_upgrade_preserves_other_blocks(self):
		from dinext_common.patches.v1_0.align_approval_deadline_shortcut import DEADLINE, DURATION, align_blocks

		duration = {"type": "shortcut", "data": {"shortcut_name": DURATION}}
		deadline = {"type": "shortcut", "data": {"shortcut_name": DEADLINE}}
		other = {"type": "paragraph", "data": {"text": "Custom note"}}
		before = [duration, other, deadline]
		expected = [duration, deadline, other]

		self.assertEqual(align_blocks(before), expected)
		self.assertEqual(align_blocks(expected), expected)
		self.assertEqual(align_blocks([other, deadline]), [other, deadline])
