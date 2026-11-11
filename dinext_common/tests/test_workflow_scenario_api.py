import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe


class TestWorkflowScenarioAPI(unittest.TestCase):
	def setUp(self):
		self.flags = patch.object(frappe.local, "flags", frappe._dict(in_test=True), create=True)
		self.flags.start()
		self.addCleanup(self.flags.stop)

	def api(self):
		try:
			return importlib.import_module("dinext_common.workflow_approval.scenarios.api")
		except ImportError as error:
			self.fail(f"Document context API is missing: {error}")

	def test_context_metadata_does_not_expose_routing_or_transition_conditions(self):
		api = self.api()
		doc = SimpleNamespace(doctype="Issue", name="A", check_permission=lambda permission: None)
		definition = frappe._dict(name="Alpha", document_type="Issue", workflow_state_field="approval_a",
			custom_activation_condition="private routing expression", states=[],
			transitions=[frappe._dict(state="Waiting", action="Approve", next_state="Done",
				allowed="Approver", condition="private transition expression", custom_transition_uuid="UUID-A")])
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(api.service, "get_context", return_value={"workflow": "Alpha", "state_field": "approval_a"}),
			patch.object(frappe, "get_cached_doc", return_value=definition),
		):
			response = api.get_workflow_context("Issue", "A")
		self.assertEqual(response["context"]["state_field"], "approval_a")
		self.assertNotIn("custom_activation_condition", response["definition"])
		self.assertNotIn("condition", response["definition"]["transitions"][0])
		self.assertEqual(response["definition"]["transitions"][0]["custom_transition_uuid"], "UUID-A")

	def test_batch_does_not_disclose_unreadable_document_context(self):
		api = self.api()
		def load(doctype, name):
			def check(permission):
				if name == "SECRET":
					raise frappe.PermissionError
			return SimpleNamespace(doctype=doctype, name=name, check_permission=check)
		with (
			patch.object(frappe, "get_doc", side_effect=load),
			patch.object(api.service, "get_context", return_value={"workflow": None}),
		):
			response = api.get_workflow_contexts("Issue", '["A", "SECRET", "A"]')
		self.assertEqual(set(response), {"A"})
		self.assertEqual(response["A"]["context"], {"workflow": None})

	def test_malformed_batch_is_rejected_before_loading_documents(self):
		api = self.api()
		with patch.object(api, "_", side_effect=lambda text: text):
			for names in ('{}', '["A", null]', '[""]'):
				with self.subTest(names=names), self.assertRaises(frappe.ValidationError):
					api.get_workflow_contexts("Issue", names)

	def test_recorded_routing_error_is_preloaded_without_changing_the_context_contract(self):
		api = self.api()
		values = {}
		doc = SimpleNamespace(set_onload=lambda key, value: values.__setitem__(key, value))
		context = {"workflow": None, "state_field": None, "state": None,
			"process_id": None, "process_status": None, "definition_revision": None}
		with (
			patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True),
			patch.object(api.service, "get_context", return_value=context),
			patch.object(api.service, "get_routing_error", return_value="The selected entry has incompatible docstatus"),
			patch.object(api.service, "supports_doctype", return_value=True),
		):
			api.onload(doc)
		self.assertEqual(values.get("dinext_workflow_error"), "The selected entry has incompatible docstatus")
		self.assertEqual(set(values["dinext_workflow_context"]), set(context))

	def test_unsupported_onload_preserves_native_workflow_behavior(self):
		api = self.api()
		values = {}
		doc = SimpleNamespace(doctype="ToDo", set_onload=lambda key, value: values.__setitem__(key, value))
		with (
			patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True),
			patch.object(api.service, "supports_doctype", return_value=False),
		):
			api.onload(doc)
		self.assertEqual(values, {})
