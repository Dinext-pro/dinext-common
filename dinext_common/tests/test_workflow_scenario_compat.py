"""Compatibility boundaries must not retain a different document or site's routing."""

from __future__ import annotations

import json
import sys
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.model import workflow as native_workflow
from frappe.model.document import Document
from frappe.model.meta import Meta

from dinext_common.workflow_approval.scenarios import compat


class RoutingService:
	"""Small deterministic service boundary; framework compatibility remains real."""

	def is_ready(self):
		return True

	def supports_doctype(self, doctype):
		return doctype == "Issue"

	def workflow_context(self, doc):
		workflow = frappe._dict(
			name=f"{frappe.local.site}-{doc.route}",
			workflow_state_field=f"state_{doc.route}",
			states=[frappe._dict(state="Review", doc_status="0")],
			transitions=[],
		)
		return workflow.name, workflow, workflow.workflow_state_field, doc.get(workflow.workflow_state_field)


class TestWorkflowScenarioCompatibility(unittest.TestCase):
	def setUp(self):
		self.previous_local = frappe.local
		frappe.local = SimpleNamespace(
			site="alpha", flags=frappe._dict(), conf=frappe._dict(),
			valid_columns={"Issue": ["name", "creation", "docstatus", "route", "state_one", "state_two"]},
		)
		self.addCleanup(setattr, frappe, "local", self.previous_local)
		flags_patch = patch.object(frappe, "flags", frappe.local.flags)
		flags_patch.start()
		self.addCleanup(flags_patch.stop)
		self.service = RoutingService()
		self.service_patch = patch.object(compat, "_service", return_value=self.service)
		self.service_patch.start()
		self.addCleanup(self.service_patch.stop)
		session_patch = patch.object(frappe, "session", frappe._dict(user="approver@example.com"))
		session_patch.start()
		self.addCleanup(session_patch.stop)
		compat.install()
		compat.clear_context()

	def source(self, name, route):
		meta = SimpleNamespace(
			name="Issue", get_table_fields=lambda: [],
			get_workflow=lambda: Meta.get_workflow(SimpleNamespace(name="Issue")),
		)
		with patch.object(frappe, "get_meta", return_value=meta):
			return Document({"doctype": "Issue", "name": name, "route": route, f"state_{route}": "Review"})

	def test_nested_same_doctype_and_failed_operation_restore_the_caller(self):
		first, second = self.source("FIRST", "one"), self.source("SECOND", "two")
		with compat.document_scope(first):
			self.assertEqual(native_workflow.get_workflow_name("Issue"), "alpha-one")
			with self.assertRaisesRegex(RuntimeError, "failed operation"):
				with compat.document_scope(second):
					self.assertEqual(native_workflow.get_workflow_name("Issue"), "alpha-two")
					raise RuntimeError("failed operation")
			self.assertEqual(native_workflow.get_workflow_name("Issue"), "alpha-one")
		self.assertIsNone(compat.current_document("Issue"))

	def test_a_scope_cannot_be_reused_after_switching_sites(self):
		first = self.source("SAME-NAME", "one")
		with compat.document_scope(first):
			frappe.local.site = "beta"
			self.assertIsNone(compat.current_document("Issue"))
			with compat.document_scope(self.source("SAME-NAME", "two")):
				self.assertEqual(native_workflow.get_workflow_name("Issue"), "beta-two")
			frappe.local.site = "alpha"
			self.assertEqual(native_workflow.get_workflow_name("Issue"), "alpha-one")

	def test_native_validation_gets_scope_before_the_meta_lookup(self):
		source = self.source("SECOND", "two")
		source._action = "save"
		seen = []
		with patch("frappe.model.document.validate_workflow", side_effect=lambda doc: seen.append(native_workflow.get_workflow_name(doc.doctype))):
			source.validate_workflow()
		self.assertEqual(seen, ["alpha-two"])
		self.assertIsNone(compat.current_document("Issue"))

	def test_native_transition_calls_restore_context_after_permission_errors(self):
		source = self.source("FIRST", "one")
		with patch.object(Document, "check_permission", side_effect=frappe.PermissionError("denied")):
			with self.assertRaises(frappe.PermissionError):
				native_workflow.get_transitions(source)
		self.assertIsNone(compat.current_document("Issue"))

	def test_alias_replacement_retains_http_guest_and_method_authorization(self):
		def original():
			return "old"
		def replacement():
			return "new"
		alias_module = types.ModuleType("_scenario_compat_alias_test")
		alias_module.imported_before_install = original
		with patch.dict(sys.modules, {alias_module.__name__: alias_module}), patch.object(frappe, "whitelisted", [original]), patch.object(frappe, "guest_methods", [original]), patch.object(frappe, "xss_safe_methods", [original]), patch.object(frappe, "allowed_http_methods_for_whitelisted_func", {original: ["POST"]}):
			compat.replace_function(original, replacement)
			self.assertEqual(alias_module.imported_before_install(), "new")
			self.assertIn(replacement, frappe.whitelisted)
			self.assertIn(replacement, frappe.guest_methods)
			self.assertIn(replacement, frappe.xss_safe_methods)
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[replacement], ["POST"])

	def test_installer_does_not_stack_document_or_native_wrappers(self):
		first = Document.validate_workflow, native_workflow.get_workflow_name
		compat.install()
		compat.install()
		self.assertEqual((Document.validate_workflow, native_workflow.get_workflow_name), first)

	def test_finalization_authority_only_applies_to_the_scoped_source(self):
		first, second = self.source("FIRST", "one"), self.source("SECOND", "two")
		with compat.authorized_finalization(first):
			self.assertTrue(compat.is_authorized_finalization(first))
			self.assertFalse(compat.is_authorized_finalization(second))
			frappe.local.site = "beta"
			self.assertFalse(compat.is_authorized_finalization(first))
		self.assertFalse(compat.is_authorized_finalization(first))

	def test_no_match_does_not_fall_back_to_a_catalog_workflow(self):
		with patch.object(self.service, "workflow_context", return_value=None):
			with compat.document_scope(self.source("NO-MATCH", "one")):
				self.assertIsNone(native_workflow.get_workflow_name("Issue"))
				self.assertEqual(native_workflow.get_transitions(self.source("NO-MATCH", "one")), [])

	def test_explicit_other_schema_cannot_expose_transitions_for_this_source(self):
		source = self.source("FIRST", "one")
		other = SimpleNamespace(name="another-schema", workflow_state_field="state_one", transitions=[
			SimpleNamespace(state="Review", allowed="Approver", condition=None,
				as_dict=lambda: {"action": "Wrong schema action"}),
		])
		with patch.object(Document, "check_permission", return_value=None), patch.object(frappe, "get_roles", return_value=["Approver"]):
			self.assertEqual(native_workflow.get_transitions(source, workflow=other), [])
			with self.assertRaises(native_workflow.WorkflowTransitionError):
				native_workflow.get_transitions(source, workflow=other, raise_exception=True)
			with patch.object(self.service, "workflow_context", return_value=None):
				self.assertEqual(native_workflow.get_transitions(source, workflow=other), [])

	def test_unready_site_keeps_the_native_legacy_result(self):
		with patch.object(self.service, "is_ready", return_value=False), patch.dict(compat._originals, {"get_workflow_name": lambda dt: "legacy"}):
			with compat.document_scope(self.source("LEGACY", "one")):
				self.assertEqual(native_workflow.get_workflow_name("Issue"), "legacy")

	def test_unsupported_doctype_retains_native_workflow_and_action_behavior(self):
		source = self.source("LEGACY", "one")
		with patch.object(self.service, "supports_doctype", return_value=False), patch.object(self.service, "workflow_context", side_effect=AssertionError("Unsupported document must use legacy routing")), patch.object(frappe, "get_all", return_value=["Legacy definition"]):
			with compat.document_scope(source):
				self.assertEqual(native_workflow.get_workflow_name("Issue"), "Legacy definition")
			seen = []
			compat._wrap_validator(lambda doc: seen.append("legacy validation"))(source)
			with patch.object(Document, "load_from_db", return_value=source), patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True):
				result = compat._wrap_apply(lambda doc, action: (seen.append("legacy action"), doc)[1])(source, "Approve")
			self.assertIs(result, source)
			self.assertEqual(seen, ["legacy validation", "legacy action"])

	def test_parallel_worker_contexts_use_their_own_site_and_document(self):
		from werkzeug.local import Local

		frappe.local = Local()
		barrier = Barrier(2)
		def run(site, route):
			frappe.local.site = site
			with compat.document_scope(frappe._dict(doctype="Issue", name="SAME", route=route)):
				barrier.wait(timeout=5)
				result = native_workflow.get_workflow_name("Issue")
			return result, compat.current_document("Issue")
		with ThreadPoolExecutor(max_workers=2) as pool:
			first = pool.submit(run, "alpha", "one")
			second = pool.submit(run, "beta", "two")
			self.assertEqual(first.result(), ("alpha-one", None))
			self.assertEqual(second.result(), ("beta-two", None))

	def test_request_and_nested_synchronous_job_hooks_preserve_the_caller(self):
		with compat.document_scope(self.source("FIRST", "one")):
			compat.initialize(method="nested.job")
			compat.cleanup(method="nested.job")
			self.assertEqual(native_workflow.get_workflow_name("Issue"), "alpha-one")
		compat.cleanup(response=None)
		self.assertIsNone(compat.current_document())

	def test_candidate_reset_only_adjusts_the_native_predecessor_with_service_authority(self):
		source = self.source("SOURCE", "two")
		before = self.source("SOURCE", "two")
		before.state_two = "Other schema state"
		source._doc_before_save = before
		source.flags.workflow_scenario_prepared = True
		source.flags.workflow_scenario_prepared_workflow = "alpha-two"
		with patch.object(native_workflow, "_", side_effect=lambda value: value):
			native_workflow.validate_workflow(source)
		self.assertIs(source._doc_before_save, before)
		self.assertEqual(before.state_two, "Other schema state")
		self.assertFalse(source.flags.workflow_scenario_prepared)
		source.flags.workflow_scenario_prepared = True
		source.flags.workflow_scenario_prepared_workflow = "different-schema"
		def fail(message, *args, **kwargs):
			raise frappe.ValidationError(message)
		with patch.object(native_workflow, "_", side_effect=lambda value: value), patch.object(frappe, "throw", side_effect=fail):
			with self.assertRaises(frappe.ValidationError):
				native_workflow.validate_workflow(source)
		self.assertIs(source._doc_before_save, before)

	def test_finalization_does_not_authorize_an_explicit_different_user(self):
		source = self.source("SOURCE", "one")
		permission = compat._wrap_permission(lambda *args, **kwargs: False)
		with compat.authorized_finalization(source):
			self.assertTrue(permission(source, "write"))
			self.assertFalse(permission(source, "write", user="other@example.com"))
			frappe.session.user = "other@example.com"
			self.assertFalse(permission(source, "write"))

	def test_finalization_identity_accepts_equivalent_creation_formats_and_rejects_recreation(self):
		source = self.source("SOURCE", "one")
		source.creation = "2026-11-11 10:00:00.000000"
		reloaded = self.source("SOURCE", "one")
		reloaded.creation = datetime(2026, 11, 11, 10)
		with compat.authorized_finalization(source):
			self.assertTrue(compat.is_authorized_finalization(reloaded))
			reloaded.creation = datetime(2026, 11, 11, 11)
			self.assertFalse(compat.is_authorized_finalization(reloaded))

	def test_real_rpc_dispatch_retains_the_native_whitelist_and_document_scope(self):
		import frappe.handler as handler

		source = self.source("SOURCE", "two")
		workflow = self.service.workflow_context(source)[1]
		workflow.transitions = [SimpleNamespace(
			state="Review", allowed="Approver", condition=None,
			as_dict=lambda: {"action": "Approve second scenario"},
		)]
		frappe.local.request = SimpleNamespace(method="GET")
		with patch.object(self.service, "workflow_context", return_value=("alpha-two", workflow, "state_two", "Review")), patch.object(frappe, "form_dict", frappe._dict(doc=source)), patch.object(frappe, "override_whitelisted_method", side_effect=lambda value: value), patch.object(handler, "get_server_script_map", return_value={}), patch.object(handler, "get_attr", return_value=native_workflow.get_transitions), patch.object(Document, "check_permission", return_value=None), patch.object(frappe, "get_roles", return_value=["Approver"]):
			self.assertEqual(handler.execute_cmd("frappe.model.workflow.get_transitions"), [{"action": "Approve second scenario"}])
		self.assertIsNone(compat.current_document())

	def test_form_catalog_contains_both_schemas_and_deduplicates_states(self):
		from frappe.desk.form.meta import FormMeta

		workflows = {
			"ONE": frappe._dict(doctype="Workflow", name="ONE", states=[frappe._dict(state="Review")]),
			"TWO": frappe._dict(doctype="Workflow", name="TWO", states=[frappe._dict(state="Review"), frappe._dict(state="Done")]),
		}
		catalog = SimpleNamespace(name="Issue")
		catalog.set = lambda field, value: setattr(catalog, field, value)
		def load(doctype, name):
			return workflows[name] if doctype == "Workflow" else frappe._dict(doctype=doctype, name=name)
		with patch.object(frappe, "get_all", side_effect=lambda doctype, **kwargs: ["ONE", "TWO"] if doctype == "Workflow" else ["Review", "Done"]), patch.object(frappe, "get_doc", side_effect=load):
			FormMeta.load_workflows(catalog)
		self.assertEqual([(row.doctype, row.name) for row in getattr(catalog, "__workflow_docs")], [
			("Workflow", "ONE"), ("Workflow State", "Review"), ("Workflow", "TWO"), ("Workflow State", "Done"),
		])

	def test_unsupported_doctype_retains_its_native_catalog(self):
		catalog = SimpleNamespace(name="ToDo")
		catalog.set = lambda field, value: setattr(catalog, field, value)
		loader = compat._wrap_catalog(lambda meta: meta.set("__workflow_docs", ["Legacy active definition"]))
		with patch.object(frappe, "get_all", side_effect=AssertionError("Unsupported metadata must remain native")):
			loader(catalog)
		self.assertEqual(getattr(catalog, "__workflow_docs"), ["Legacy active definition"])

	def test_catalog_missing_legacy_state_does_not_block_unrelated_forms(self):
		catalog = SimpleNamespace(name="Issue")
		catalog.set = lambda field, value: setattr(catalog, field, value)
		workflow = frappe._dict(doctype="Workflow", name="LEGACY", states=[frappe._dict(state="Deleted Demo State")])
		def load(doctype, name=None):
			if isinstance(doctype, dict):
				return SimpleNamespace(**doctype, get=doctype.get, as_dict=lambda: doctype.copy())
			if doctype == "Workflow":
				return workflow
			raise frappe.DoesNotExistError("Deleted Workflow State")
		with patch.object(frappe, "get_all", side_effect=lambda doctype, **kwargs: ["LEGACY"] if doctype == "Workflow" else []), patch.object(frappe, "get_doc", side_effect=load):
			compat._wrap_catalog(lambda meta: None)(catalog)
		self.assertEqual([(row.doctype, row.name) for row in getattr(catalog, "__workflow_docs")], [
			("Workflow", "LEGACY"), ("Workflow State", "Deleted Demo State"),
		])
		self.assertIsNone(getattr(catalog, "__workflow_docs")[1].get("style"))
		self.assertEqual(getattr(catalog, "__workflow_docs")[1].as_dict()["name"], "Deleted Demo State")

	def test_timesheet_task_match_rejects_same_state_from_another_or_unlinked_process(self):
		from dinext_common.workflow_approval.scenarios import service, timesheets

		source = self.source("SOURCE", "one")
		source.creation = "2026-11-11 10:00:00"
		task = frappe._dict(
			status="Working", round_status="Open", reference_doctype="Issue", reference_name="SOURCE",
			workflow="alpha-one", workflow_process="CURRENT", workflow_state="Review",
			source_created_at=source.creation,
		)
		context = {"workflow": "alpha-one", "process_id": "CURRENT", "state": "Review"}
		with patch.object(frappe, "db", SimpleNamespace(get_value=lambda *args, **kwargs: task)), patch.object(frappe, "get_doc", return_value=source), patch.object(service, "get_context", return_value=context):
			self.assertFalse(timesheets.task_no_longer_matches_source("TASK"))
			task.workflow_process = "OLD"
			self.assertTrue(timesheets.task_no_longer_matches_source("TASK"))
			task.workflow_process = None
			self.assertTrue(timesheets.task_no_longer_matches_source("TASK"))

	def test_timesheet_legacy_status_sync_respects_another_state_field_and_no_scenario(self):
		from dinext_common.workflow_approval.scenarios import service
		try:
			from dinext_timesheets.dinext_timesheets.user_timesheet.events import workflow_tasks
		except ModuleNotFoundError as error:
			if error.name and error.name.split(".")[0] == "dinext_timesheets":
				self.skipTest("The optional Timesheets app is not on this bench")
			raise

		for state_field in ("special_workflow_state", None):
			with self.subTest(state_field=state_field):
				doc = frappe._dict(workflow_state="Stale legacy state", status="Selected domain status")
				with patch.object(service, "is_ready", return_value=True), patch.object(service, "get_context", return_value={"state_field": state_field}):
					workflow_tasks.sync_status_from_workflow_state(doc)
				self.assertEqual(doc.status, "Selected domain status")
		with patch.object(service, "is_ready", return_value=True), patch.object(service, "get_context", return_value={"state_field": "workflow_state"}):
			workflow_tasks.sync_status_from_workflow_state(doc)
		self.assertEqual(doc.status, "Stale legacy state")

	def test_timesheet_selected_field_change_rolls_up_once_without_rewriting_domain_status(self):
		from dinext_common.workflow_approval.scenarios import timesheets

		source = self.source("SOURCE", "one")
		before = self.source("SOURCE", "one")
		source._doc_before_save = before
		source.status = before.status = "Pending Approval"
		source.state_one = "Rejected"
		source.user_timesheet = "PARENT"
		self.service.get_context = lambda doc: {"state_field": "state_one"}
		events = []
		producer = SimpleNamespace(_enabled=lambda: True,
			_recalculate_parent=lambda parent, doc, old: events.append("rollup"))
		wrapped = timesheets._wrap_source_update(lambda *args: events.append("legacy"), producer)
		with patch.object(frappe, "get_doc", return_value=SimpleNamespace(name="PARENT")):
			wrapped(source)
			self.assertEqual(events, ["rollup"])
			self.assertEqual(source.status, "Pending Approval")
			events.clear()
			frappe.flags.defer_timesheet_rollup = True
			wrapped(source)
			self.assertEqual(events, [])
			frappe.flags.defer_timesheet_rollup = False
			source.status = "Rejected"
			wrapped(source)
			self.assertEqual(events, ["legacy"])

	def test_native_apply_pins_before_saving_and_finishes_only_after_success(self):
		source = self.source("SOURCE", "one")
		events = []
		self.service.ensure_context = lambda doc, **kwargs: events.append("repeat" if kwargs.get("strict") is False else "ensure")
		self.service.get_context = lambda doc: {"process_id": "PROCESS"}
		self.service.start_cascade = lambda doc, **kwargs: events.append("cascade")
		self.service.pin_process = lambda doc, **kwargs: events.append("pin")
		self.service.finish_transition = lambda doc, **kwargs: (events.append("finish"), True)[1]
		db = SimpleNamespace(
			savepoint=lambda point: events.append("savepoint"),
			rollback=lambda **kwargs: events.append("rollback"),
		)
		def apply(doc, action):
			events.append("apply")
			self.assertEqual(native_workflow.get_workflow_name("Issue"), "alpha-one")
			return doc
		with patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=False), patch.object(frappe, "db", db), patch.object(Document, "load_from_db", return_value=source), patch.dict(compat._originals, {"get_transitions": lambda *args: [frappe._dict(action="Approve", allow_self_approval=1)]}):
			result = compat._wrap_apply(apply)(source, "Approve")
			self.assertIs(result, source)
			self.assertEqual(events, ["ensure", "savepoint", "cascade", "pin", "apply", "finish", "repeat"])
			events.clear()
			def fail(doc, action):
				events.append("apply")
				raise RuntimeError("save failed")
			with self.assertRaisesRegex(RuntimeError, "save failed"):
				compat._wrap_apply(fail)(source, "Approve")
			self.assertEqual(events, ["ensure", "savepoint", "cascade", "pin", "apply", "rollback"])
		self.assertIsNone(compat.current_document())

	def test_imported_native_apply_waits_for_the_personal_vote_without_saving(self):
		from dinext_common.workflow_approval import api

		source = self.source("SOURCE", "one")
		def forbidden_native_save(doc, action):
			self.fail("Native role action bypassed personal task voting")
		with patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True), patch.object(api, "apply_workflow", return_value={"transitioned": False}), patch.object(Document, "load_from_db", return_value=source), patch.object(frappe, "get_doc", return_value=source):
			result = compat._wrap_apply(forbidden_native_save)(source, "Approve")
		self.assertIs(result, source)
		self.assertEqual(result.state_one, "Review")
		self.assertIsNone(compat.current_document())

	def test_queued_native_submission_finishes_and_prepares_repeat_after_save(self):
		source = self.source("SOURCE", "one")
		source.state_one = "Done"
		events = []
		self.service.active_process = lambda doc: frappe._dict(name="PROCESS", workflow="alpha-one", status="Running", current_state="Review")
		self.service.is_terminal = lambda workflow, state: state == "Done"
		self.service.finish_transition = lambda *args, **kwargs: (events.append("finish"), True)[1]
		self.service.ensure_context = lambda *args, **kwargs: events.append("repeat")
		with patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=False), patch.object(frappe, "get_doc", return_value=self.service.workflow_context(source)[1]):
			with compat._native_action(source):
				compat.native_submission_completed(source)
			self.assertEqual(events, [])
			compat.native_submission_completed(source)
		self.assertEqual(events, ["finish", "repeat"])

	def test_frappe_synchronous_job_executes_each_document_without_retaining_its_context(self):
		from frappe.utils.background_jobs import execute_job

		def run(doc):
			with compat.document_scope(doc):
				return native_workflow.get_workflow_name("Issue")
		def hooks(event, *args, **kwargs):
			return {"before_job": [compat.initialize], "after_job": [compat.cleanup]}.get(event, [])
		db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
		with patch.object(frappe, "db", db), patch.object(frappe, "get_hooks", side_effect=hooks):
			first = execute_job("alpha", run, None, "first", {"doc": self.source("FIRST", "one")}, is_async=False)
			second = execute_job("alpha", run, None, "second", {"doc": self.source("SECOND", "two")}, is_async=False)
		self.assertEqual((first, second), ("alpha-one", "alpha-two"))
		self.assertIsNone(compat.current_document())

	def test_parallel_engine_suppresses_native_role_actions_but_retains_trash_and_legacy(self):
		source = self.source("SOURCE", "one")
		events = []
		processor = compat._wrap_legacy_actions(lambda doc, state: events.append(state))
		with patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=True):
			processor(source, "on_update")
			self.assertEqual(events, [])
			processor(source, "on_trash")
			self.assertEqual(events, ["on_trash"])
			with patch.object(self.service, "supports_doctype", return_value=False):
				processor(source, "on_update")
			self.assertEqual(events, ["on_trash", "on_update"])
		with patch("dinext_common.workflow_approval.lifecycle.is_engine_enabled", return_value=False):
			processor(source, "on_update")
		self.assertEqual(events, ["on_trash", "on_update", "on_update"])
		self.assertIsNone(compat.current_document())


class TestWorkflowScenarioCompatibilityIntegration(unittest.TestCase):
	"""Real RPC and worker connections use separate fixtures on an explicitly disposable site."""

	@classmethod
	def setUpClass(cls):
		if not getattr(frappe.local, "db", None) or not frappe.conf.get("workflow_scenarios_test_site"):
			raise unittest.SkipTest("Requires an explicitly disposable Workflow scenario test site")
		from frappe import app as _app
		from frappe.core.doctype.user.user import generate_keys
		from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
		from frappe.desk.form import load as form_load

		from dinext_common.workflow_approval.scenarios.metadata import next_selection_order

		cls.site = frappe.local.site
		cls.sites_path = str(Path(frappe.local.sites_path).resolve())
		cls.marker = "Compat-" + frappe.generate_hash(length=8)
		cls.role = "_Test Native " + cls.marker
		cls.fields = ("custom_native_compat_a", "custom_native_compat_b")
		cls.sources = []
		cls.users, cls.tokens, cls.workflows = [], {}, {}
		frappe.set_user("Administrator")
		if form_load.add_comments.__module__.startswith("frappe_comment_xt"):
			fixture = Path(frappe.get_app_path("frappe_comment_xt", "fixtures", "custom_field.json"))
			comment_fields = [row for row in json.loads(fixture.read_text()) if row.get("dt") == "Comment"]
			create_custom_fields({"Comment": comment_fields}, update=True)
			frappe.db.updatedb("Comment")
		create_custom_fields({"Task": [{"fieldname": field, "fieldtype": "Data", "label": field,
			"module": "Dinext Common"} for field in cls.fields]}, update=True)
		frappe.get_doc({"doctype": "Role", "role_name": cls.role}).insert(ignore_permissions=True)
		for index in (1, 2):
			user = f"{cls.marker.lower()}-{index}@example.com"
			with patch("frappe.core.doctype.user.user.ask_pass_update"):
				frappe.get_doc({"doctype": "User", "email": user, "first_name": "Native compatibility voter",
					"send_welcome_email": 0, "roles": [{"role": cls.role}, {"role": "Projects User"}, {"role": "System Manager"}]}).insert(ignore_permissions=True)
				keys = generate_keys(user)
			cls.users.append(user)
			cls.tokens[user] = f"token {keys['api_key']}:{keys['api_secret']}"
		cls.action = cls.marker + " Approve"
		frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": cls.action}).insert(ignore_permissions=True)
		for suffix, field in zip(("A", "B"), cls.fields, strict=True):
			states = [cls.marker + " " + suffix + " Review", cls.marker + " " + suffix + " Done"]
			for state in states:
				frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": "Primary"}).insert(ignore_permissions=True)
			cls.workflows[suffix] = frappe.get_doc({"doctype": "Workflow", "workflow_name": cls.marker + " " + suffix,
				"document_type": "Task", "workflow_state_field": field, "is_active": 1, "send_email_alert": 0,
				"custom_selection_order": next_selection_order("Task"),
				"custom_activation_condition": f"doc.subject.startswith('{cls.marker}-{suffix}')",
				"states": [{"state": state, "doc_status": "0", "allow_edit": "Projects User"} for state in states],
				"transitions": [{"state": states[0], "action": cls.action, "next_state": states[1],
					"allowed": cls.role, "allow_self_approval": 1,
					"custom_parallel_approval_policy": "All", "custom_transition_uuid": cls.marker + "-" + suffix}],
			}).insert(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		self.reconnect()
		self.addCleanup(self._restore_schema_activation)
		self._restore_schema_activation()

	def _restore_schema_activation(self):
		self.reconnect()
		for workflow in self.workflows.values():
			frappe.db.set_value("Workflow", workflow.name, "is_active", 1, update_modified=False)
		frappe.db.commit()
		frappe.clear_cache(doctype="Task")

	@classmethod
	def reconnect(cls):
		if not getattr(frappe.local, "db", None):
			frappe.init(site=cls.site, sites_path=cls.sites_path)
			frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

	@classmethod
	def tearDownClass(cls):
		cls.reconnect()
		for name in cls.sources:
			if frappe.db.exists("Task", name):
				frappe.delete_doc("Task", name, force=True, ignore_permissions=True)
		for workflow in cls.workflows.values():
			frappe.db.set_value("Workflow", workflow.name, "is_active", 0, update_modified=False)
		for user in cls.users:
			frappe.db.set_value("User", user, {"enabled": 0, "api_key": None}, update_modified=False)
		cls.tokens.clear()
		frappe.db.commit()
		frappe.clear_cache(doctype="Task")

	def source(self, suffix):
		self.reconnect()
		doc = frappe.get_doc({"doctype": "Task", "subject": self.marker + "-" + suffix + " " + frappe.generate_hash(length=8)})
		try:
			doc.insert(ignore_permissions=True)
		except Exception:
			frappe.db.rollback()
			raise
		self.sources.append(doc.name)
		frappe.db.commit()
		return doc

	def request(self, user, method, args, *, http_method="POST"):
		import frappe.app
		from werkzeug.test import Client
		from werkzeug.wrappers import Response

		frappe.db.commit()
		frappe.destroy()
		try:
			with patch.object(frappe.app, "_site", self.site), patch.object(frappe.app, "_sites_path", self.sites_path):
				response = Client(frappe.app.application, Response).open(
					"/api/method/" + method, method=http_method,
					data=frappe.as_json(args), content_type="application/json",
					headers={"Authorization": self.tokens[user]}, buffered=True,
				)
				payload = response.get_json()
				self.assertEqual(response.status_code, 200, payload)
				return payload
		finally:
			self.reconnect()

	def test_http_catalog_serializes_missing_historical_state_master(self):
		state = self.workflows["B"].states[-1].state
		master = frappe.get_doc("Workflow State", state).as_dict()
		frappe.db.delete("Workflow State", {"name": state})
		frappe.clear_cache(doctype="Task")
		try:
			catalog = self.request(self.users[0], "frappe.desk.form.load.getdoctype", {"doctype": "Task"}, http_method="GET")
			states = [row for row in catalog["docs"][0]["__workflow_docs"] if row["doctype"] == "Workflow State"]
			self.assertTrue(any(row["name"] == state for row in states))
			self.assertFalse(frappe.db.exists("Workflow State", state))
		finally:
			frappe.get_doc(master).insert(ignore_permissions=True)
			frappe.clear_cache(doctype="Task")
			frappe.db.commit()

	def test_http_keeps_schema_fields_and_requires_both_personal_votes(self):
		from dinext_common.workflow_approval.scenarios import service

		a, b = self.source("A"), self.source("B")
		first_process = service.get_context(a)["process_id"]
		first = self.request(self.users[0], "frappe.model.workflow.apply_workflow", {"doc": a.as_dict(), "action": self.action})
		self.assertFalse(first["message"]["transitioned"])
		a.reload()
		self.assertEqual(service.get_context(a)["process_status"], "Running")
		frappe.db.set_value("Workflow", self.workflows["A"].name, "is_active", 0)
		frappe.clear_cache(doctype="Task")
		catalog = self.request(self.users[0], "frappe.desk.form.load.getdoctype", {"doctype": "Task"}, http_method="GET")
		workflow_docs = catalog["docs"][0].get("__workflow_docs") or []
		self.assertIn(self.workflows["A"].name, [row["name"] for row in workflow_docs if row["doctype"] == "Workflow"])
		self.assertTrue(any(row["doctype"] == "Workflow State" and row.get("style") == "Primary" for row in workflow_docs))
		for source, field in ((b, self.fields[1]), (a, self.fields[0])):
			loaded = self.request(self.users[0], "frappe.desk.form.load.getdoc", {"doctype": "Task", "name": source.name}, http_method="GET")
			doc = next(row for row in loaded["docs"] if row.get("doctype") == "Task")
			self.assertEqual(doc["__onload"]["dinext_workflow_context"]["state_field"], field)
		frappe.db.set_value("Workflow", self.workflows["A"].name, "is_active", 1)
		second = self.request(self.users[1], "frappe.model.workflow.apply_workflow", {"doc": a.as_dict(), "action": self.action})
		self.assertTrue(second["message"]["transitioned"])
		a.reload()
		self.assertNotEqual(service.get_context(a)["process_id"], first_process)
		self.assertEqual(service.get_context(a)["process_status"], "Prepared")
		self.assertEqual(frappe.db.get_value(service.PROCESS, first_process, "status"), "Completed")

	def test_imported_native_call_and_worker_keep_other_document_waiting(self):
		from frappe.model.workflow import apply_workflow
		from frappe.utils.background_jobs import execute_job

		from dinext_common.workflow_approval.scenarios import service

		a, b = self.source("A"), self.source("B")
		first_a, first_b = service.get_context(a)["process_id"], service.get_context(b)["process_id"]
		frappe.set_user(self.users[0])
		for source in (a, b):
			result = apply_workflow(source, self.action)
			self.assertEqual(result.get(service.get_context(source)["state_field"]), self.workflows["A" if source.name == a.name else "B"].states[0].state)
		frappe.db.commit()
		frappe.destroy()
		try:
			execute_job(self.site, "frappe.model.workflow.apply_workflow", None, self.marker,
				{"doc": {"doctype": "Task", "name": a.name}, "action": self.action}, user=self.users[1], is_async=True)
		finally:
			self.reconnect()
		a.reload()
		b.reload()
		self.assertEqual(frappe.db.get_value(service.PROCESS, first_a, "status"), "Completed")
		self.assertNotEqual(service.get_context(a)["process_id"], first_a)
		self.assertEqual(service.get_context(b)["process_id"], first_b)
		self.assertEqual(service.get_context(b)["process_status"], "Running")
		self.assertIsNone(compat.current_document())


if __name__ == "__main__":
	unittest.main()
