import unittest
from datetime import datetime


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
