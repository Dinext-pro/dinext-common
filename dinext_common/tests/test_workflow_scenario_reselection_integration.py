"""A rejected stale vote must not trap a read-only approver in the old candidate."""

import unittest

import frappe

from dinext_common.tests import test_workflow_scenario_lifecycle as lifecycle_fixtures
from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.scenarios import service


class TestWorkflowScenarioReselectionIntegration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not frappe.conf.get("workflow_scenarios_test_site"):
			raise unittest.SkipTest("Requires an explicitly disposable scenario test site")
		lifecycle_fixtures.TestWorkflowScenarioLifecycle.setUpClass()

	def setUp(self):
		self.fixture = lifecycle_fixtures.TestWorkflowScenarioLifecycle()
		self.fixture.setUp()
		self.source = self.fixture.source("A stale settings")
		self.initial = service.get_context(self.source)
		self.task = next(
			row for row in self.fixture.tasks(self.source) if row.approver == self.fixture.first_user
		)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")
		task_names = frappe.get_all(
			"Workflow Task",
			filters={"reference_doctype": "Note", "reference_name": self.source.name},
			pluck="name",
		)
		frappe.delete_doc("Note", self.source.name, force=True, ignore_permissions=True)
		for dt in (service.CONTEXT, service.PROCESS):
			frappe.db.delete(dt, {"reference_doctype": "Note", "reference_name": self.source.name})
		if task_names:
			frappe.db.delete("Workflow Action", {"custom_workflow_task": ("in", task_names)})
			frappe.db.delete(
				"ToDo", {"reference_type": "Workflow Task", "reference_name": ("in", task_names)}
			)
			frappe.db.delete("Available Workflow Transitions", {"parent": ("in", task_names)})
			frappe.db.delete("Workflow Task", {"name": ("in", task_names)})
		for workflow in (self.fixture.a, self.fixture.b):
			frappe.delete_doc("Workflow", workflow.name, force=True, ignore_permissions=True)
		frappe.conf.enable_parallel_workflow_approval = self.fixture.old_flag
		frappe.db.commit()
		frappe.clear_cache()

	def test_changed_routing_is_reconciled_after_stale_vote_rollback(self):
		frappe.db.set_value("Workflow", self.fixture.a.name, "custom_activation_condition", "False")
		frappe.db.set_value("Workflow", self.fixture.b.name, "custom_activation_condition", "True")
		frappe.db.commit()
		frappe.set_user(self.fixture.first_user)
		with self.assertRaises(engine.WorkflowApprovalConflictError):
			engine.cast_vote(self.task.name, transition_uuid="scenario-A")
		frappe.db.rollback()
		source = frappe.get_doc("Note", self.source.name)
		context = service.get_context(source)
		self.assertEqual(context["workflow"], self.fixture.b.name)
		self.assertNotEqual(context["process_id"], self.initial["process_id"])
		self.assertEqual(context["process_status"], "Prepared")
		self.assertEqual(frappe.db.get_value("Workflow Task", self.task.name, "status"), "Cancelled")
		self.assertTrue(self.fixture.tasks(source))

	def test_broken_condition_is_recorded_without_choosing_lower_schema(self):
		frappe.db.set_value("Workflow", self.fixture.a.name, "custom_activation_condition", "1 / 0")
		frappe.db.set_value("Workflow", self.fixture.b.name, "custom_activation_condition", "True")
		frappe.db.commit()
		frappe.set_user(self.fixture.first_user)
		with self.assertRaises(service.WorkflowScenarioError):
			engine.cast_vote(self.task.name, transition_uuid="scenario-A")
		frappe.db.rollback()
		source = frappe.get_doc("Note", self.source.name)
		self.assertIsNone(service.get_context(source)["workflow"])
		self.assertIn(self.fixture.a.name, service.get_routing_error(source))
