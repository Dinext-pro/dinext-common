import json
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from dinext_common import hooks
from dinext_common.workflow_approval import migration


class TestWorkflowLegacyApiRetirement(unittest.TestCase):
	def test_normal_install_and_update_retire_old_endpoints(self):
		hook = "dinext_common.workflow_approval.migration.retire_legacy_script_apis"
		self.assertIn(hook, hooks.after_sync)
		self.assertIn(hook, hooks.after_migrate)

	def test_fixtures_keep_custom_scripts_and_exclude_legacy_apis(self):
		app_path = Path(hooks.__file__).parent
		rows = json.loads((app_path / "fixtures/server_script.json").read_text())
		legacy = migration.cutover_records("remove")
		self.assertFalse({row["name"] for row in rows} & set(legacy["Server Script"]))
		self.assertFalse({row.get("api_method") for row in rows} & set(legacy["Legacy API"]))
		self.assertNotIn("IssueAssignUserGroup", {row["name"] for row in rows})
		fixture = next(item for item in hooks.fixtures if isinstance(item, dict) and item["doctype"] == "Server Script")
		excluded_names = next(values for field, operator, values in fixture["filters"] if (field, operator) == ("name", "not in"))
		self.assertEqual(
			set(excluded_names),
			set(migration._SHARED_LEGACY_RECORDS["Server Script"]) | {"IssueAssignUserGroup"},
		)

	def test_only_the_old_api_records_are_disabled_once(self):
		with (
			patch.object(migration.frappe, "db", Mock()) as db,
			patch.object(migration.frappe, "get_all", side_effect=[["Workflow Task Processing"], []]) as load,
			patch.object(migration.frappe, "cache") as cache,
		):
			migration.retire_legacy_script_apis()
			migration.retire_legacy_script_apis()

		self.assertEqual(load.call_count, 2)
		filters = load.call_args.kwargs["filters"]
		self.assertEqual(filters["disabled"], 0)
		self.assertEqual(filters["script_type"], "API")
		self.assertEqual(filters["module"], "Dinext Common")
		self.assertEqual(set(filters["name"][1]), set(migration._SHARED_LEGACY_RECORDS["Server Script"]))
		self.assertEqual(set(filters["api_method"][1]), set(migration._SHARED_LEGACY_RECORDS["Legacy API"]))
		self.assertEqual(db.set_value.call_args_list, [
			call("Server Script", "Workflow Task Processing", "disabled", 1, update_modified=False),
		])
		cache.delete_value.assert_called_once_with("server_script_map")
