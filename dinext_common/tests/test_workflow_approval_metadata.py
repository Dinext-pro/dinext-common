import json
import unittest
from pathlib import Path
from types import SimpleNamespace


APP_ROOT = Path(__file__).resolve().parents[1]


class TestWorkflowApprovalMetadata(unittest.TestCase):
	def metadata(self):
		try:
			from dinext_common.workflow_approval import metadata
		except (ImportError, ModuleNotFoundError) as exc:
			self.fail(f"workflow approval metadata module is missing: {exc}")
		return metadata

	def load_doctype(self, doctype_folder):
		path = (
			APP_ROOT
			/ "dinext_common"
			/ "doctype"
			/ doctype_folder
			/ f"{doctype_folder}.json"
		)
		return json.loads(path.read_text())

	def test_workflow_task_is_app_owned_with_audit_fields_and_safe_permissions(self):
		document = self.load_doctype("workflow_task")
		fields = {field["fieldname"]: field for field in document["fields"]}

		self.assertFalse(document.get("custom"))
		for fieldname in (
			"reference_doctype",
			"reference_name",
			"source_created_at",
			"source_title",
			"source_owner",
			"workflow",
			"workflow_state",
			"approval_round_id",
			"round_status",
			"round_manifest",
			"transition_uuid",
			"transition_semantic_hash",
			"approver",
			"policy",
			"threshold",
			"entry_fingerprint",
			"entry_fingerprint_version",
			"content_fingerprint",
			"content_fingerprint_version",
			"vote_comment",
			"completed_at",
			"completion_source",
			"reused_from_workflow_task",
			"cancelled_at",
			"cancellation_reason",
			"source_deleted_at",
			"finalization_status",
			"submission_queue",
			"failure_metadata",
			"correlation_id",
		):
			self.assertIn(fieldname, fields)

		self.assertEqual(fields["reference_name"]["options"], "reference_doctype")
		self.assertEqual(
			fields["round_status"]["options"],
			"Open\nStalled\nFinalizing\nTransitioned\nCancelled\nConflicted",
		)
		self.assertEqual(
			fields["completion_source"]["depends_on"],
			"eval:doc.status=='Completed'",
		)
		self.assertEqual(
			fields["reused_from_workflow_task"]["depends_on"],
			"eval:doc.completion_source=='Automatic Unchanged'",
		)
		self.assertEqual(
			fields["cancellation_reason"]["depends_on"],
			"eval:doc.status=='Cancelled'",
		)
		all_permission = next(row for row in document["permissions"] if row["role"] == "All")
		self.assertEqual(all_permission["read"], 1)
		self.assertEqual(all_permission["report"], 1)
		self.assertEqual(all_permission["select"], 1)
		self.assertFalse(all_permission.get("write", 0))
		self.assertFalse(all_permission.get("create", 0))
		self.assertFalse(all_permission.get("delete", 0))

	def test_available_transition_snapshot_is_app_owned_and_read_only(self):
		document = self.load_doctype("available_workflow_transitions")
		fields = {field["fieldname"]: field for field in document["fields"]}

		self.assertFalse(document.get("custom"))
		for fieldname in (
			"transition_uuid",
			"transition_semantic_hash",
			"transition_idx",
			"allowed_role",
			"policy",
			"threshold",
			"comment_is_required",
			"auto_complete_unchanged",
			"eligible_approvers",
		):
			self.assertIn(fieldname, fields)
			self.assertEqual(fields[fieldname].get("read_only"), 1)
		self.assertEqual(fields["threshold"]["depends_on"], "eval:doc.policy=='Minimum'")

	def test_core_custom_fields_have_conditional_visibility(self):
		metadata = self.metadata()
		by_doctype = metadata.get_workflow_approval_custom_fields()
		transition = {field["fieldname"]: field for field in by_doctype["Workflow Transition"]}
		workflow = {field["fieldname"]: field for field in by_doctype["Workflow"]}
		action = {field["fieldname"]: field for field in by_doctype["Workflow Action"]}

		self.assertEqual(
			transition["custom_minimum_approvals"]["depends_on"],
			"eval:doc.custom_parallel_approval_policy=='Minimum'",
		)
		self.assertEqual(
			transition["custom_minimum_approvals"]["mandatory_depends_on"],
			"eval:doc.custom_parallel_approval_policy=='Minimum'",
		)
		self.assertEqual(workflow["custom_group_send_time"]["depends_on"], metadata.DAILY_SEND_TIME_CONDITION)
		self.assertEqual(
			workflow["custom_group_send_time"]["mandatory_depends_on"],
			metadata.DAILY_SEND_TIME_CONDITION,
		)
		self.assertEqual(
			workflow["custom_attach_document_pdf"]["depends_on"],
			metadata.IMMEDIATE_EMAIL_CONDITION,
		)
		for fieldname in (
			"custom_workflow_task",
			"custom_approval_round_id",
			"custom_notification_mode",
			"custom_notification_status",
			"custom_last_digest_slot",
			"custom_delivery_key",
		):
			self.assertIn(fieldname, action)
			self.assertEqual(action[fieldname].get("read_only"), 1)

	def test_workflow_validation_normalizes_policy_and_rejects_duplicates(self):
		metadata = self.metadata()
		first = SimpleNamespace(
			state="Pending",
			action="Approve",
			next_state="Approved",
			allowed="Manager",
			custom_transition_uuid="transition-1",
			custom_parallel_approval_policy="",
			custom_minimum_approvals=None,
		)
		workflow = SimpleNamespace(
			transitions=[first],
			send_email_alert=0,
			custom_group_workflow_action_emails=0,
			custom_approval_monitor_roles=[],
		)

		metadata.validate_workflow_configuration(workflow)
		self.assertEqual(first.custom_parallel_approval_policy, "Any")

		duplicate = SimpleNamespace(**vars(first))
		duplicate.custom_transition_uuid = "transition-2"
		duplicate.allowed = "Other"
		workflow.transitions.append(duplicate)
		metadata.validate_workflow_configuration(workflow)
		self.assertEqual(len(workflow.transitions), 2)

		duplicate.custom_transition_uuid = first.custom_transition_uuid
		with self.assertRaises(ValueError):
			metadata.validate_workflow_configuration(workflow)

	def test_empty_policy_with_all_users_flag_becomes_all_and_uuid_is_stable(self):
		metadata = self.metadata()
		transition = SimpleNamespace(
			state="Pending",
			action="Approve",
			next_state="Approved",
			allowed="Manager",
			custom_transition_uuid="",
			custom_parallel_approval_policy="",
			custom_all_users_with_role=1,
			custom_minimum_approvals=None,
		)
		workflow = SimpleNamespace(
			transitions=[transition],
			send_email_alert=0,
			custom_group_workflow_action_emails=0,
			custom_approval_monitor_roles=[],
		)

		metadata.validate_workflow_configuration(workflow)
		self.assertEqual(transition.custom_parallel_approval_policy, "All")
		assigned = transition.custom_transition_uuid
		self.assertTrue(assigned)
		metadata.validate_workflow_configuration(workflow)
		self.assertEqual(transition.custom_transition_uuid, assigned)

	def test_timesheet_fixtures_and_desk_hooks_keep_transition_identity(self):
		from dinext_common import hooks

		fixture = (
			Path(__file__).resolve().parents[3]
			/ "dinext_timesheets"
			/ "dinext_timesheets"
			/ "fixtures"
			/ "workflow.json"
		)
		workflows = json.loads(fixture.read_text())
		for workflow in workflows:
			for transition in workflow["transitions"]:
				self.assertTrue(transition["custom_transition_uuid"])
				self.assertIn(transition["custom_parallel_approval_policy"], {"Any", "All", "Minimum"})
				if transition["action"] == "Согласовано":
					self.assertEqual(transition["custom_parallel_approval_policy"], "All")
		patch = (
			APP_ROOT / "patches" / "v1_0" / "generalize_parallel_workflow_approvals.py"
		).read_text()
		self.assertNotIn("generate_hash", patch)
		self.assertIn(
			"dinext_common.workflow_approval.metadata.ensure_transition_identity",
			hooks.after_migrate,
		)
		self.assertIn(
			"dinext_common.workflow_approval.metadata.ensure_workflow_approval_desk_records",
			hooks.after_migrate,
		)
		metadata_source = (APP_ROOT / "workflow_approval" / "metadata.py").read_text()
		self.assertIn('{"label": card_name, "number_card_name": card_name}', metadata_source)
		self.assertIn('"label": "My Approvals Dashboard"', metadata_source)
		self.assertNotIn('"Требуют решения"', metadata_source)
		form_script = (
			Path(__file__).resolve().parents[3]
			/ "dinext_timesheets"
			/ "dinext_timesheets"
			/ "public"
			/ "js"
			/ "user_timesheet_form.js"
		).read_text()
		self.assertIn('frappe.model.can_read("Holiday List")', form_script)
		banner = (APP_ROOT / "public" / "js" / "workflow_approval.js").read_text()
		self.assertIn("get_form_approval_banner", banner)
		self.assertNotIn(".catch(() => [])", banner)
		project_perm = json.loads(
			(
				Path(__file__).resolve().parents[3]
				/ "dinext_projects"
				/ "dinext_projects"
				/ "fixtures"
				/ "custom_docperm.json"
			).read_text()
		)
		approver_project = [
			row
			for row in project_perm
			if row.get("parent") == "Project" and row.get("role") == "Dinext_UTP_Appoval"
		]
		self.assertEqual(len(approver_project), 1)
		self.assertEqual(approver_project[0]["read"], 1)
		self.assertEqual(approver_project[0]["write"], 0)
		# Any Custom DocPerm on a widget DocType replaces its standard Desk User read for everyone.
		widget_perms = [
			row for row in project_perm if row.get("parent") in ("Number Card", "Custom HTML Block")
		]
		self.assertEqual(widget_perms, [])
		self.assertNotIn('"doctype": "Custom DocPerm"', metadata_source)

	def test_workflow_validation_requires_minimum_and_daily_schedule(self):
		metadata = self.metadata()
		transition = SimpleNamespace(
			state="Pending",
			action="Approve",
			next_state="Approved",
			allowed="Manager",
			custom_transition_uuid="transition-1",
			custom_parallel_approval_policy="Minimum",
			custom_minimum_approvals=0,
		)
		workflow = SimpleNamespace(
			transitions=[transition],
			send_email_alert=1,
			custom_group_workflow_action_emails=1,
			custom_group_interval_unit="Days",
			custom_group_interval_value=1,
			custom_group_send_time=None,
			custom_approval_monitor_roles=[],
		)

		with self.assertRaises(ValueError):
			metadata.validate_workflow_configuration(workflow)

		transition.custom_minimum_approvals = 1
		with self.assertRaises(ValueError):
			metadata.validate_workflow_configuration(workflow)

	def test_hooks_register_parent_validation_and_source_delete_audit(self):
		from dinext_common import hooks

		self.assertIn(
			"dinext_common.workflow_approval.metadata.validate_workflow_doc",
			hooks.doc_events["Workflow"]["validate"],
		)
		self.assertIn(
			"dinext_common.workflow_approval.lifecycle.on_source_trash",
			hooks.doc_events["*"]["on_trash"],
		)
		self.assertIn("Workflow Task", hooks.ignore_links_on_delete)

	def test_model_migration_patch_is_registered_post_sync(self):
		patches = (APP_ROOT / "patches.txt").read_text()

		self.assertIn(
			"dinext_common.patches.v1_0.generalize_parallel_workflow_approvals",
			patches,
		)
