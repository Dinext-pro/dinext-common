from unittest import TestCase
from unittest.mock import patch

import frappe

from dinext_common import hooks


class TestWorkflowInvoiceDependencies(TestCase):
	def test_invoice_projects_are_discovered_before_the_vote_locks_the_source(self):
		adapters = getattr(hooks, "workflow_approval_lock_dependencies", [])
		self.assertIn("dinext_common.workflow_approval.invoice_projects.lock_dependencies", adapters)
		from dinext_common.workflow_approval.invoice_projects import lock_dependencies

		with (
			patch.object(frappe, "get_all", return_value=["P-2", "P-2", None]) as items,
			patch.object(frappe.db, "get_value", return_value="P-1") as header,
		):
			self.assertEqual(lock_dependencies("Sales Invoice", "SI-1"), [("Project", "P-1"), ("Project", "P-2")])
			self.assertEqual(lock_dependencies("Purchase Invoice", "PI-1"), [("Project", "P-2")])
			self.assertEqual(lock_dependencies("Project", "P-1"), [])
			header.assert_called_once_with("Sales Invoice", "SI-1", "project")
			self.assertEqual(items.call_count, 2)
