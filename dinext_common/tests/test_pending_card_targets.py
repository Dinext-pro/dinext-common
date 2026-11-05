import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval import api


class TestPendingCardTargets(unittest.TestCase):
	def test_pending_cards_include_a_source_if_any_personal_task_has_a_required_target(self):
		with (
			patch.object(frappe, "get_all", side_effect=self.candidates),
			patch.object(api, "has_workflow_task_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=self.sources),
			patch.object(
				api, "frappe",
				SimpleNamespace(
					get_all=self.candidates,
					get_list=self.sources,
					get_meta=lambda _doctype: SimpleNamespace(has_field=lambda _field: False),
					session=frappe._dict(user="reader@example.invalid"),
					form_dict=frappe._dict(),
				),
			),
		):
			result = api.get_legacy_number_card_result(
				{"doc": "User Timesheet Position", "state": "Pending Approval", "route": "user-timesheet-position"}
			)
		self.assertEqual(result["value"], 2)
		self.assertEqual(result["route_options"], {"name": ["in", ["MIXED", "OWN"]]})

	def candidates(self, doctype, **_kwargs):
		rows = {
			"Workflow Task": [
				{"name": "TASK-OWN", "workflow": "WF", "reference_name": "OWN"},
				{"name": "TASK-MIXED", "workflow": "WF", "reference_name": "MIXED"},
				{"name": "TASK-MIXED-2", "workflow": "WF", "reference_name": "MIXED"},
				{"name": "TASK-OPTIONAL", "workflow": "WF", "reference_name": "OPTIONAL"},
			],
			"Workflow Document State": [{"parent": "WF", "state": "Required"}],
			"Available Workflow Transitions": [
				{"parent": "TASK-OWN", "next_state": "Required"},
				{"parent": "TASK-MIXED", "next_state": "Required"},
				{"parent": "TASK-MIXED", "next_state": "Optional"},
				{"parent": "TASK-MIXED-2", "next_state": "Optional"},
				{"parent": "TASK-OPTIONAL", "next_state": "Optional"},
			],
		}
		return [frappe._dict(row) for row in rows[doctype]]

	def sources(self, _doctype, *, filters, **_kwargs):
		return [
			name for name in filters["name"][1]
			if name != "OWN" or "user" not in filters
		]
