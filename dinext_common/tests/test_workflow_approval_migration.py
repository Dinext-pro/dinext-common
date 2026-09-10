import unittest


class TestWorkflowApprovalMigration(unittest.TestCase):
	def migration(self):
		try:
			from dinext_common.workflow_approval import migration
		except (ImportError, ModuleNotFoundError) as exc:
			self.fail(f"workflow approval migration module is missing: {exc}")
		return migration

	def test_deletion_manifest_contains_exact_classified_records(self):
		migration = self.migration()
		manifest = migration.LEGACY_DELETION_MANIFEST

		self.assertEqual(len(manifest["Server Script"]), 14)
		self.assertEqual(len(manifest["Client Script"]), 8)
		self.assertEqual(len(manifest["Notification"]), 3)
		self.assertEqual(len(manifest["Custom DocPerm"]), 3)
		self.assertEqual(len(manifest["Legacy API"]), 5)
		self.assertIn("UTP_UT_Status_V3", manifest["Server Script"])
		self.assertIn("Task Limit Exceeded_V4", manifest["Server Script"])
		self.assertIn("UTP_comm_2_UT_transfer", migration.RETAINED_SYSTEM_RECORDS["Server Script"])

	def test_content_hash_ignores_runtime_noise_but_detects_behavior_changes(self):
		migration = self.migration()
		base = {"name": "Script", "script": "result = 1", "modified": "old", "owner": "Administrator"}
		noise = {"name": "Script", "script": "result = 1", "modified": "new", "owner": "Administrator"}
		changed = {"name": "Script", "script": "result = 2", "modified": "new", "owner": "Administrator"}

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
		for doctype, names in migration.LEGACY_DELETION_MANIFEST.items():
			for name in names:
				self.assertEqual(rows[(doctype, name)], "remove")
		for doctype, names in migration.RETAINED_SYSTEM_RECORDS.items():
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

	def test_consumer_apps_have_no_classified_repository_leftovers(self):
		from pathlib import Path

		migration = self.migration()
		apps = Path(__file__).resolve().parents[3]
		leftovers = migration.collect_repository_leftovers(lambda app: apps / app / app)
		self.assertEqual(leftovers, [])
