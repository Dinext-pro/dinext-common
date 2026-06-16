import json
from pathlib import Path
import unittest


class TestFixtureAnalysisGolden(unittest.TestCase):
	def test_record_detail_matches_golden_payload(self):
		from dinext_common.dinext_common.fixture_analysis.diff_engine import diff_documents

		golden_path = Path(__file__).resolve().parent / "fixtures" / "fixture_analysis_record_detail_golden.json"
		expected = json.loads(golden_path.read_text(encoding="utf-8"))

		record = diff_documents(
			"Server Script",
			[
				{
					"name": "TEST-SCRIPT",
					"script": "line 1\nline 2 updated\nline 3",
					"enabled": 1,
				}
			],
			[
				{
					"name": "TEST-SCRIPT",
					"script": "line 1\nline 2\nline 3",
					"enabled": 0,
				}
			],
		)["records_by_name"]["TEST-SCRIPT"]

		actual = {
			"status": record["status"],
			"changed_paths_preview": record["changed_paths_preview"],
			"field_diffs": [
				{
					"path": field["path"],
					"change_type": field["change_type"],
					"file_value": field["file_value"],
					"db_value": field["db_value"],
					"text_diff": field["text_diff"],
				}
				for field in record["field_diffs"]
			],
		}

		self.assertEqual(actual, expected)
