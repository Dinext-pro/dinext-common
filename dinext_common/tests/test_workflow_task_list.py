from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.desk import reportview

from dinext_common import hooks


class TestWorkflowTaskList(TestCase):
	def test_native_page_checks_access_before_offset_and_stops_after_filling_page(self):
		method = hooks.override_whitelisted_methods.get("frappe.desk.reportview.get")
		self.assertIsNotNone(method, "Workflow Task list still checks the entire permission catalog")
		from dinext_common.workflow_approval import task_list

		request = frappe._dict(
			doctype="Workflow Task", fields=["name"], start=1, page_length=2,
			order_by="creation desc, name asc", filters=[["Workflow Task", "status", "=", "Working"]],
		)
		candidates = [frappe._dict(name=f"task-{i}") for i in range(8)]

		def permission_filtered_query(*unused, **args):
			names = args["filters"][-1][-1]
			return [frappe._dict(name=name) for name in names if name not in {"task-0", "task-2"}]

		with (
			patch.object(frappe, "session", frappe._dict(user="reviewer")),
			patch.object(frappe.local, "form_dict", frappe._dict(doctype="Workflow Task")),
			patch.object(reportview, "get_form_params", return_value=request),
			patch.object(reportview, "execute", side_effect=permission_filtered_query),
			patch.object(task_list, "CANDIDATE_PAGE_SIZE", 4),
			patch.object(task_list, "prepare_source_permissions"),
			patch.object(task_list, "task_principal_filters", return_value=[]),
			patch.object(task_list, "task_read_candidates"),
			patch.object(frappe, "get_all", side_effect=[candidates[:4], candidates[4:]]) as scan,
		):
			self.assertEqual(task_list.get()["values"], [["task-3"], ["task-4"]])
			self.assertEqual(scan.call_count, 2)
			self.assertEqual(scan.call_args_list[1].kwargs["limit_start"], 4)
			self.assertEqual(scan.call_args_list[0].kwargs["filters"], request.filters)

	def test_joins_and_report_groups_use_the_native_path(self):
		from dinext_common.workflow_approval import task_list

		base = frappe._dict(doctype="Workflow Task", fields=["name"], start=0, page_length=20,
			order_by="name asc", filters=[])
		unsupported = [
			{"fields": ["available_workflow_transitions.action"]},
			{"filters": [["Available Workflow Transitions", "action", "=", "Approve"]]},
			{"group_by": "status"},
			{"order_by": "owner.full_name asc"},
			{"page_length": 0},
		]
		for changes in unsupported:
			with (
				self.subTest(changes=changes),
				patch.object(frappe.local, "form_dict", frappe._dict(doctype="Workflow Task")),
				patch.object(reportview, "get_form_params", return_value=frappe._dict(base, **changes)),
				patch.object(reportview, "get", return_value="native") as native,
			):
				self.assertEqual(task_list.get(), "native")
				native.assert_called_once_with()
