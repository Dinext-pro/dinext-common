import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe


class TestWorkflowScenarioAPI(unittest.TestCase):
	def setUp(self):
		previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict(in_test=True)
		self.addCleanup(setattr, frappe.local, "flags", previous_flags)

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
			patch.object(api.service, "get_routing_error", return_value=None),
			patch.object(api.service, "supports_doctype", return_value=True),
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
			patch.object(frappe, "get_meta", return_value=SimpleNamespace(is_virtual=True)),
			patch.object(api.service, "supports_doctype", return_value=False),
		):
			response = api.get_workflow_contexts("Issue", '["A", "SECRET", "A"]')
		self.assertEqual(set(response), {"A"})
		self.assertIsNone(response["A"]["context"]["workflow"])
		self.assertFalse(response["A"]["managed"])

	def test_batch_routes_many_readable_sources_without_individual_context_lookups(self):
		api = self.api()
		names = [f"Issue {index}" for index in range(500)]
		sources = [frappe._dict(doctype="Issue", name=name, creation="2026-11-15 10:00:00",
			state_a="Pending Alpha", state_b="Pending Beta",
			check_permission=lambda permission: None) for name in names]
		alpha = frappe._dict(name="Alpha", document_type="Issue", workflow_state_field="state_a",
			modified="2026-11-15 11:00:00", is_active=1, custom_selection_order=1)
		beta = frappe._dict(name="Beta", document_type="Issue", workflow_state_field="state_b",
			modified="2026-11-15 11:00:00", is_active=0, custom_selection_order=2)

		def lookup(doctype, **options):
			if doctype == api.service.CONTEXT:
				keys = options["filters"]["name"][1]
				return [frappe._dict(name=key, active_process=f"p-{index}", routing_error=None)
					for index, key in enumerate(keys[:2])]
			if doctype == api.service.PROCESS:
				return [frappe._dict(name=f"p-{index}", status="Running", workflow="Beta",
					source_key=api.service.source_key(sources[index]))
					for index in range(len(options["filters"]["name"][1]))]
			if doctype == "Workflow Task":
				return [
					frappe._dict(reference_name=names[2], source_created_at="2020-01-01 10:00:00", workflow="Beta"),
					frappe._dict(reference_name=names[3], source_created_at=sources[3].creation, workflow="Beta"),
				]
			if doctype == "Workflow":
				return ["Alpha", "Beta"]
			raise AssertionError(doctype)

		documents = {source.name: source for source in sources}
		workflows = {"Alpha": alpha, "Beta": beta}
		def load(doctype, name):
			return (workflows if doctype == "Workflow" else documents)[name]

		with (
			patch.object(frappe, "get_doc", side_effect=load),
			patch.object(frappe, "get_meta", return_value=SimpleNamespace(is_virtual=True)),
			patch.object(api.service, "is_ready", return_value=True),
			patch.object(api.service, "supports_doctype", return_value=True),
			patch.object(api.service, "_selected", side_effect=AssertionError("per-document routing lookup")),
			patch.object(frappe, "get_all", side_effect=lookup) as queries,
		):
			response = api.get_workflow_contexts("Issue", names)
		self.assertEqual(len(response), 500)
		self.assertEqual(response[names[0]]["context"]["process_status"], "Running")
		self.assertEqual(response[names[0]]["definition"]["name"], "Beta")
		self.assertEqual(response[names[0]]["context"]["state"], "Pending Beta")
		self.assertEqual(response[names[2]]["definition"]["name"], "Alpha")
		self.assertEqual(response[names[3]]["definition"]["name"], "Beta")
		self.assertIsNone(response[names[3]]["context"]["process_id"])
		self.assertEqual(response[names[-1]]["context"]["state"], "Pending Alpha")
		self.assertLessEqual(queries.call_count, 4)

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
