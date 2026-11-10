from unittest import TestCase
from unittest.mock import patch

import frappe


class TestDeadlineWorkspaceCards(TestCase):
	def test_empty_percentage_is_explained_but_zero_count_stays_numeric(self):
		from dinext_common.workflow_approval.deadlines.discipline import _card

		with patch(
			"dinext_common.workflow_approval.deadlines.discipline.metrics",
			return_value={"on_time_percent": None, "open_overdue": 0},
		):
			self.assertEqual(_card("on_time_percent", percent=True)["value"], frappe._("No observations"))
			self.assertEqual(_card("on_time_percent", percent=True)["fieldtype"], "Data")
			self.assertEqual(_card("open_overdue")["value"], 0)
			self.assertEqual(_card("open_overdue")["fieldtype"], "Int")

	def test_unknown_rows_do_not_become_undefined_chart_labels(self):
		from dinext_common.workflow_approval.deadlines.report import execute

		result = dict(rows=[], all_rows=[], on_time_percent=None, open_overdue=0, completed_late=0, errors=0)
		with patch("dinext_common.workflow_approval.deadlines.report.metrics", return_value=result):
			_cols, _rows, _msg, chart, _summary = execute()
		self.assertEqual(chart["data"]["labels"], [])
		self.assertEqual(chart["data"]["datasets"][0]["values"], [])
