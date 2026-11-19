import unittest
from unittest.mock import patch


class TestWorkflowApprovalMigration(unittest.TestCase):
	def migration(self):
		try:
			from dinext_common.workflow_approval import migration
		except (ImportError, ModuleNotFoundError) as exc:
			self.fail(f"workflow approval migration module is missing: {exc}")
		return migration

	def test_deletion_manifest_contains_exact_classified_records(self):
		migration = self.migration()
		manifest = migration.cutover_records("remove")
		if "Custom DocPerm" not in manifest:
			self.assertIn("Workflow Task Processing", manifest["Server Script"])
			return

		self.assertEqual(len(manifest["Server Script"]), 14)
		self.assertEqual(len(manifest["Client Script"]), 8)
		self.assertEqual(len(manifest["Notification"]), 3)
		self.assertEqual(len(manifest["Custom DocPerm"]), 3)
		self.assertEqual(len(manifest["Legacy API"]), 5)
		self.assertIn("UTP_UT_Status_V3", manifest["Server Script"])
		self.assertIn("Task Limit Exceeded_V4", manifest["Server Script"])
		self.assertIn("UTP_comm_2_UT_transfer", migration.cutover_records("retain")["Server Script"])

	def test_content_hash_ignores_runtime_noise_but_detects_behavior_changes(self):
		migration = self.migration()
		base = {"name": "Script", "script": "result = 1", "modified": "old", "owner": "A"}
		noise = {"name": "Script", "script": "result = 1", "modified": "new", "owner": "B"}
		changed = {"name": "Script", "script": "result = 2", "modified": "new", "owner": "B"}

		self.assertEqual(migration.system_record_hash(base), migration.system_record_hash(noise))
		self.assertNotEqual(migration.system_record_hash(base), migration.system_record_hash(changed))

	def test_single_blank_legacy_cohort_is_unambiguous(self):
		migration = self.migration()
		tasks = [
			{
				"name": "WT-1",
				"status": "Working",
				"doc": "Example",
				"wt_docname": "EX-1",
				"state": "Pending",
				"user": "alice@example.com",
				"approval_round_id": None,
			},
			{
				"name": "WT-2",
				"status": "Working",
				"doc": "Example",
				"wt_docname": "EX-1",
				"state": "Pending",
				"user": "bob@example.com",
				"approval_round_id": None,
			},
		]

		self.assertEqual(migration.detect_ambiguous_open_rounds(tasks), [])

	def test_duplicate_approver_or_mixed_round_identity_is_ambiguous(self):
		migration = self.migration()
		base = {
			"status": "Working",
			"doc": "Example",
			"wt_docname": "EX-1",
			"state": "Pending",
			"user": "alice@example.com",
		}

		duplicate_user = [
			{**base, "name": "WT-1", "approval_round_id": None},
			{**base, "name": "WT-2", "approval_round_id": None},
		]
		mixed_round = [
			{**base, "name": "WT-1", "approval_round_id": None},
			{
				**base,
				"name": "WT-2",
				"user": "bob@example.com",
				"approval_round_id": "round-2",
			},
		]

		self.assertEqual(len(migration.detect_ambiguous_open_rounds(duplicate_user)), 1)
		self.assertEqual(len(migration.detect_ambiguous_open_rounds(mixed_round)), 1)

	def test_preflight_blocks_unclassified_or_ambiguous_inventory(self):
		migration = self.migration()
		report = {
			"ambiguous_open_rounds": [{"source": "EX-1"}],
			"unclassified": [],
			"missing_schema": [],
		}
		with self.assertRaises(migration.CutoverBlockedError):
			migration.assert_cutover_ready(report)

		report["ambiguous_open_rounds"] = []
		report["unclassified"] = ["Unknown Script"]
		with self.assertRaises(migration.CutoverBlockedError):
			migration.assert_cutover_ready(report)

		report["unclassified"] = []
		migration.assert_cutover_ready(report)

	def test_lossless_matrix_covers_every_classified_record(self):
		migration = self.migration()
		rows = { (row["doctype"], row["name"]): row["decision"] for row in migration.lossless_matrix() }
		for doctype, names in migration.cutover_records("remove").items():
			for name in names:
				self.assertEqual(rows[(doctype, name)], "remove")
		for doctype, names in migration.cutover_records("retain").items():
			for name in names:
				self.assertEqual(rows[(doctype, name)], "retain")

	def test_repository_leftovers_detect_fixture_and_standard_files(self):
		from pathlib import Path
		from tempfile import TemporaryDirectory

		migration = self.migration()
		with TemporaryDirectory() as tmp:
			root = Path(tmp)
			projects = root / "dinext_projects"
			timesheets = root / "dinext_timesheets"
			(projects / "fixtures").mkdir(parents=True)
			(timesheets / "fixtures").mkdir(parents=True)
			(projects / "dinext_projects/notification/требуется_согласование").mkdir(parents=True)
			(projects / "fixtures" / "server_script.json").write_text(
				'[{"name": "Workflow Task Assign"}]',
				encoding="utf-8",
			)
			(projects / "fixtures" / "client_script.json").write_text("[]", encoding="utf-8")
			(projects / "fixtures" / "custom_docperm.json").write_text("[]", encoding="utf-8")
			(timesheets / "fixtures" / "server_script.json").write_text("[]", encoding="utf-8")
			(timesheets / "fixtures" / "client_script.json").write_text(
				'[{"name": "UT_Accept_WF"}]',
				encoding="utf-8",
			)
			(timesheets / "fixtures" / "custom_docperm.json").write_text("[]", encoding="utf-8")
			(
				projects
				/ "dinext_projects/notification/требуется_согласование"
				/ "требуется_согласование.json"
			).write_text("{}", encoding="utf-8")

			def resolver(app: str) -> Path:
				return root / app

			migration_rules = [
				{"remove": {"Server Script": ("Workflow Task Assign",), "Client Script": ("UT_Accept_WF",)},
					"fixture_files": (("dinext_projects", "fixtures/server_script.json", "Server Script"),
						("dinext_timesheets", "fixtures/client_script.json", "Client Script")),
					"notification_files": (("dinext_projects", "dinext_projects/notification/требуется_согласование",
						"Требуется согласование"),)},
			]
			providers = patch.object(migration, "_cutover_providers", return_value=migration_rules)
			providers.start()
			self.addCleanup(providers.stop)
			leftovers = {
				(row["doctype"], row["name"])
				for row in migration.collect_repository_leftovers(resolver)
			}
			self.assertIn(("Server Script", "Workflow Task Assign"), leftovers)
			self.assertIn(("Client Script", "UT_Accept_WF"), leftovers)
			self.assertIn(("Notification", "Требуется согласование"), leftovers)

	def test_cutover_restarts_after_injected_phase_fault(self):
		from unittest.mock import patch

		migration = self.migration()
		state = {"completed": [], "receipt": {}}

		def store(value):
			state.clear()
			state.update(value)

		with (
			patch.object(migration, "_require_cutover_operator"),
			patch.object(migration, "_cutover_state", return_value=state),
			patch.object(migration, "_store_cutover_state", side_effect=store),
			patch.object(migration, "_phase_preflight", return_value={"ok": 1}),
			patch.object(migration.frappe.db, "commit"),
		):
			with self.assertRaises(migration.CutoverBlockedError):
				migration.execute_cutover("backup-1", inject_fault="drain_queues")
			self.assertEqual(state["completed"], ["preflight"])
			with (
				patch.object(migration, "_phase_drain_queues", return_value={"ok": 1}),
				patch.object(migration, "_phase_migrate_settings", return_value={"ok": 1}),
				patch.object(
					migration,
					"_phase_disable_retained_consumers",
					return_value={"disabled": []},
				),
				patch.object(migration, "_phase_delete_records", return_value={"Server Script": 0}),
				patch.object(
					migration,
					"_phase_enable_engine",
					return_value={"backup": "backup-1"},
				),
				patch.object(migration, "_phase_smoke", return_value={"remaining": {}}),
			):
				receipt = migration.execute_cutover("backup-1")
			self.assertIn("smoke", receipt)
			self.assertEqual(set(state["completed"]), set(migration.CUTOVER_PHASES))

	def test_failed_smoke_does_not_publish_completion_receipt(self):
		from unittest.mock import patch

		migration = self.migration()
		conf = migration.frappe._dict()
		state = {
			"version": 1,
			"completed": ["preflight", "drain_queues", "migrate_settings",
				"disable_retained_consumers", "delete_records"],
			"receipt": {"delete_records": {}},
		}

		def store(value):
			state.update(value)

		with (
			patch.object(migration.frappe.local, "conf", conf),
			patch("frappe.installer.update_site_config", side_effect=conf.__setitem__),
			patch.object(migration, "_require_cutover_operator"),
			patch.object(migration, "_cutover_state", return_value=state),
			patch.object(migration, "_store_cutover_state", side_effect=store),
			patch.object(migration.frappe.db, "commit"),
			patch.object(migration, "_phase_smoke", side_effect=[
				migration.CutoverBlockedError("fixture drift"), {"remaining": {}},
			]),
		):
			with self.assertRaisesRegex(migration.CutoverBlockedError, "fixture drift"):
				migration.execute_cutover("backup-1")
			self.assertFalse(conf.get("parallel_workflow_cutover_receipt"))
			self.assertFalse(conf.get("enable_parallel_workflow_approval"))
			self.assertNotIn("smoke", state["completed"])
			migration.execute_cutover("backup-1")
			self.assertTrue(conf.get("parallel_workflow_cutover_receipt"))
			self.assertTrue(conf.get("enable_parallel_workflow_approval"))

	def test_legacy_cutover_receipt_does_not_bypass_smoke(self):
		from unittest.mock import patch

		migration = self.migration()
		from dinext_common.patches.v1_0 import cutover_parallel_workflow_approvals as entry

		conf = migration.frappe._dict(run_parallel_workflow_cutover=True,
			parallel_workflow_cutover_receipt={"backup": "backup-1"},
			parallel_workflow_cutover_state={"completed": ["enable_engine"]})
		with (
			patch.object(migration.frappe.local, "conf", conf),
			patch.object(migration, "execute_cutover") as execute,
		):
			entry.execute()
			execute.assert_called_once_with("backup-1")

	def test_old_checkpoint_revalidates_compatibility_and_migrates_position_status(self):
		from unittest.mock import patch

		migration = self.migration()
		state = {
			"completed": ["preflight", "drain_queues", "migrate_settings",
				"disable_retained_consumers", "delete_records"],
			"receipt": {"delete_records": {"Server Script": 1}},
		}
		executed = []

		def run_phase(phase):
			def run(_backup, _state):
				executed.append(phase)
				return {}

			return run

		with (
			patch.object(migration, "_require_cutover_operator"),
			patch.object(migration, "_cutover_state", return_value=state),
			patch.object(migration, "_store_cutover_state", side_effect=state.update),
			patch.object(migration.frappe.db, "commit"),
			patch.dict(migration.PHASE_HANDLERS, {phase: run_phase(phase) for phase in migration.CUTOVER_PHASES}),
		):
			receipt = migration.execute_cutover("backup-1")
			migration.execute_cutover("backup-1")

		self.assertEqual(executed, list(migration.CUTOVER_PHASES))
		self.assertEqual(receipt["previous_checkpoint"]["delete_records"], {"Server Script": 1})

	def test_workflow_jobs_block_cutover_even_without_an_rq_job_table(self):
		from unittest.mock import patch

		migration = self.migration()
		site = migration.frappe.local.site
		with (
			patch("frappe.utils.background_jobs.get_jobs", return_value={
				site: ["dinext_common.workflow_approval.api.run_job"],
			}),
			patch.object(migration.frappe, "get_all", return_value=["Project"]),
			patch.object(migration.frappe.db, "count", return_value=0),
		):
			with self.assertRaisesRegex(migration.CutoverBlockedError, "pending Workflow"):
				migration._phase_drain_queues()

	def test_scheduled_workflow_job_blocks_cutover_through_its_wrapper(self):
		from unittest.mock import patch

		migration = self.migration()
		site = migration.frappe.local.site
		methods = {
			"method": ["frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job"],
			"job_type": ["dinext_common.workflow_approval.deadlines.scheduler.run_deadline_ticks"],
		}
		with (
			patch("frappe.utils.background_jobs.get_jobs", side_effect=lambda *, site, key: {site: methods[key]}),
			patch.object(migration.frappe, "get_all", return_value=[]),
			patch.object(migration.frappe.db, "count", return_value=0),
		):
			with self.assertRaisesRegex(migration.CutoverBlockedError, '"rq_jobs": 1'):
				migration._phase_drain_queues()

	def test_live_script_must_match_the_reviewed_hash(self):
		from unittest.mock import patch

		migration = self.migration()
		hashes = {"Client Script": {"AFL_Approval_V3": "reviewed"}}
		conf = migration.frappe._dict(parallel_workflow_cutover_reviewed_hashes=hashes)
		with (
			patch.object(migration.frappe.local, "conf", conf),
			patch.object(migration, "summarize_live_hashes", return_value={
				"Client Script": {"AFL_Approval_V3": "changed"},
			}),
		):
			with self.assertRaisesRegex(migration.CutoverBlockedError, "AFL_Approval_V3"):
				migration._verify_reviewed_records()

	def test_consumer_apps_have_no_classified_repository_leftovers(self):
		from pathlib import Path

		migration = self.migration()
		apps = Path(__file__).resolve().parents[3]
		leftovers = migration.collect_repository_leftovers(lambda app: apps / app / app)
		self.assertEqual(leftovers, [])
