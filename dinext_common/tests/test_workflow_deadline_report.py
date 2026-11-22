from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from dinext_common.workflow_approval.deadlines import report


class TestWorkflowDeadlineReport(TestCase):
	def setUp(self):
		due = date(2026, 11, 22)
		self.rows = [
			dict(approver="approver-a", workflow_state="Review", discipline_status="On Time", due_date=due),
			dict(approver="approver-a", workflow_state="Review", discipline_status="Overdue", due_date=due),
			dict(approver="approver-b", workflow_state="Review", discipline_status="Overdue", due_date=due),
		]
		for name, value in (
			(
				"metrics",
				Mock(return_value=dict(rows=self.rows, all_rows=self.rows, on_time_percent=100 / 3,
					open_overdue=2, completed_late=0, errors=0)),
			),
			("full_name", str),
			("display_deadline_error", str),
			("_", str),
		):
			patcher = patch.object(report, name, value)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_report_uses_first_nonempty_group_for_each_authorized_approver(self):
		first = Mock(return_value={"approver-a": "Team A", "approver-b": "", "hidden-user": "Hidden Group"})
		second = Mock(return_value={"approver-a": "Different Group", "approver-b": "Team B"})
		with (
			patch.object(report.frappe, "get_hooks", return_value=["first", "second"]) as hooks,
			patch.object(report.frappe, "get_attr", side_effect={"first": first, "second": second}.__getitem__),
			patch.object(report.frappe, "db", Mock(exists=Mock(return_value=False))),
		):
			_, grouped, _, _, summary = report.execute({"group_by": "user_group"})

		hooks.assert_called_once_with("workflow_approval_approver_group_providers")
		first.assert_called_once_with(("approver-a", "approver-b"))
		second.assert_called_once_with(("approver-a", "approver-b"))
		self.assertEqual(
			[(row["group"], row["count"], row["overdue"]) for row in grouped],
			[("Team A", 2, 1), ("Team B", 1, 1)],
		)
		self.assertEqual(summary[0]["value"], 100 / 3)

	def test_report_works_without_a_group_provider(self):
		with (
			patch.object(report.frappe, "get_hooks", return_value=[]),
			patch.object(report.frappe, "db", Mock(exists=Mock(return_value=False))) as db,
		):
			columns, rows, _, _, _ = report.execute()
		self.assertEqual([row["user_group"] for row in rows], [None, None, None])
		db.exists.assert_not_called()
		column_types = {col["fieldname"]: col["fieldtype"] for col in columns}
		self.assertEqual(column_types["reference_doctype"], "Data")
		self.assertEqual(column_types["workflow"], "Data")
		self.assertEqual(column_types["user_group"], "Data")
		self.assertEqual(column_types["reference_name"], "Dynamic Link")
