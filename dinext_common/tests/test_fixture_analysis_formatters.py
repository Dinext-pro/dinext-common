import unittest


class TestFixtureAnalysisFormatters(unittest.TestCase):
	def test_build_overview_payload_omits_record_level_details(self):
		from dinext_common.dinext_common.fixture_analysis.formatters import build_overview_payload

		payload = build_overview_payload(
			[
				{
					"app": "dinext_common",
					"warnings": [],
					"counts": {"file_only": 1, "db_only": 0, "changed": 2, "equal": 3},
					"doctypes": [
						{
							"app": "dinext_common",
							"doctype": "Server Script",
							"warnings": [],
							"counts": {"file_only": 1, "db_only": 0, "changed": 2, "equal": 3},
							"record_diff": {"records": [{"record_key": "SHOULD-NOT-BE-HERE"}]},
						}
					],
				}
			]
		)

		self.assertEqual(payload["counts"]["changed"], 2)
		self.assertNotIn("record_diff", payload["apps"][0]["doctypes"][0])

	def test_build_records_payload_omits_detail_only_fields(self):
		from dinext_common.dinext_common.fixture_analysis.formatters import build_records_payload

		payload = build_records_payload(
			app="dinext_common",
			doctype="Server Script",
			status="all",
			start=0,
			page_length=20,
			records=[
				{
					"record_key": "TEST-001",
					"status": "changed",
					"field_diff_count": 2,
					"text_diff_count": 1,
					"changed_paths_preview": ["script", "enabled"],
					"field_diffs": [{"path": "script"}],
					"file_doc": {"name": "TEST-001"},
					"db_doc": {"name": "TEST-001"},
				}
			],
		)

		record = payload["records"][0]
		self.assertEqual(record["record_key"], "TEST-001")
		self.assertNotIn("field_diffs", record)
		self.assertNotIn("file_doc", record)
		self.assertNotIn("db_doc", record)

	def test_compact_record_summary_includes_system_route_for_db_records(self):
		from dinext_common.dinext_common.fixture_analysis.formatters import compact_record_summary

		record = compact_record_summary(
			{
				"doctype": "Server Script",
				"is_single": False,
				"record_key": "TEST-001",
				"name": "TEST-001",
				"status": "changed",
				"field_diff_count": 1,
				"text_diff_count": 1,
				"changed_paths_preview": ["script"],
				"db_doc": {"name": "TEST-001"},
			}
		)

		self.assertEqual(record["system_route"], {"doctype": "Server Script", "name": "TEST-001"})

	def test_build_detail_payload_includes_single_doctype_system_route(self):
		from dinext_common.dinext_common.fixture_analysis.formatters import build_detail_payload

		payload = build_detail_payload(
			app="dinext_common",
			doctype="Website Settings",
			record={
				"doctype": "Website Settings",
				"is_single": True,
				"record_key": "single::Website Settings",
				"status": "changed",
				"field_diffs": [],
				"db_doc": {"name": "Website Settings"},
			},
		)

		self.assertEqual(payload["system_route"], {"doctype": "Website Settings", "name": "Website Settings"})
