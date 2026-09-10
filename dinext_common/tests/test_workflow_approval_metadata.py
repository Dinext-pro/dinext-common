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
		workflow.transitions.append(duplicate)
		with self.assertRaises(ValueError):
			metadata.validate_workflow_configuration(workflow)

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
