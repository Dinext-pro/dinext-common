import unittest
from datetime import datetime

from dinext_common.workflow_approval.control import (
	aggregate_duration,
	aggregate_load,
	longest_open_round_days,
)


class TestApprovalControlMath(unittest.TestCase):
	def test_parallel_round_counts_one_document_and_one_task_per_person(self):
		now = datetime(2026, 10, 5, 12, 0, 0)
		created = datetime(2026, 10, 4, 12, 0, 0)
		tasks = [
			{
				"approver": "a@x",
				"approval_round_id": "R1",
				"creation": created,
				"source_title": "Doc",
				"reference_name": "D1",
			},
			{
				"approver": "b@x",
				"approval_round_id": "R1",
				"creation": created,
				"source_title": "Doc",
				"reference_name": "D1",
			},
		]

		rows = aggregate_load(tasks, {"a@x": "Анна", "b@x": "Борис"}, now)

		self.assertEqual(sum(row["open_tasks"] for row in rows), 2)
		self.assertEqual({row["open_rounds"] for row in rows}, {1})
		self.assertEqual({row["approver_name"] for row in rows}, {"Анна", "Борис"})

	def test_automatic_completion_does_not_reduce_the_average(self):
		start = datetime(2026, 10, 1, 0, 0, 0)
		tasks = [
			{
				"approver": "a@x",
				"reference_doctype": "Issue",
				"workflow": "W",
				"status": "Completed",
				"completion_source": "Manual",
				"creation": start,
				"completed_at": datetime(2026, 10, 1, 10, 0, 0),
			},
			{
				"approver": "a@x",
				"reference_doctype": "Issue",
				"workflow": "W",
				"status": "Completed",
				"completion_source": "Automatic Unchanged",
				"creation": start,
				"completed_at": datetime(2026, 10, 1, 1, 0, 0),
			},
			{
				"approver": "a@x",
				"reference_doctype": "Issue",
				"workflow": "W",
				"status": "Cancelled",
				"completion_source": "Manual",
				"creation": start,
				"completed_at": datetime(2026, 10, 1, 2, 0, 0),
			},
		]

		rows = aggregate_duration(tasks, "Document Type", {})

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["manual_count"], 1)
		self.assertEqual(rows[0]["automatic_count"], 1)
		self.assertEqual(rows[0]["avg_hours"], 10.0)
		self.assertEqual(rows[0]["max_hours"], 10.0)

	def test_longest_wait_is_the_oldest_open_round_in_days(self):
		self.assertEqual(longest_open_round_days([12, 36]), 1.5)
		self.assertEqual(longest_open_round_days([]), 0.0)
