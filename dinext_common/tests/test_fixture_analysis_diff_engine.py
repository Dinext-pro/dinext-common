import unittest


class TestFixtureAnalysisDiffEngine(unittest.TestCase):
	def test_diff_documents_groups_record_statuses(self):
		from dinext_common.dinext_common.fixture_analysis.diff_engine import diff_documents

		file_docs = [
			{"name": "NEW-001", "title": "Only in fixture"},
			{"name": "CHG-001", "title": "New title", "script": "line 1\nline 2 updated"},
			{"name": "EQ-001", "title": "Same title"},
		]
		db_docs = [
			{"name": "CHG-001", "title": "Old title", "script": "line 1\nline 2"},
			{"name": "EQ-001", "title": "Same title"},
			{"name": "DB-001", "title": "Only in database"},
		]

		result = diff_documents("Server Script", file_docs, db_docs)

		self.assertEqual(result["counts"]["file_only"], 1)
		self.assertEqual(result["counts"]["db_only"], 1)
		self.assertEqual(result["counts"]["changed"], 1)
		self.assertEqual(result["counts"]["equal"], 1)
		self.assertEqual(result["records_by_name"]["NEW-001"]["status"], "file_only")
		self.assertEqual(result["records_by_name"]["DB-001"]["status"], "db_only")
		self.assertEqual(result["records_by_name"]["CHG-001"]["status"], "changed")
		self.assertEqual(result["records_by_name"]["EQ-001"]["status"], "equal")

	def test_diff_documents_builds_field_and_text_diff_details(self):
		from dinext_common.dinext_common.fixture_analysis.diff_engine import diff_documents

		file_docs = [
			{
				"name": "CHG-001",
				"script": "line 1\nline 2 updated",
				"config": {"enabled": 1, "items": [{"code": "A", "value": 2}]},
			}
		]
		db_docs = [
			{
				"name": "CHG-001",
				"script": "line 1\nline 2",
				"config": {"enabled": 1, "items": [{"code": "A", "value": 1}]},
			}
		]

		result = diff_documents("Server Script", file_docs, db_docs)
		record = result["records_by_name"]["CHG-001"]
		field_diffs = {field["path"]: field for field in record["field_diffs"]}

		self.assertIn("script", field_diffs)
		self.assertIn("config.items[0].value", field_diffs)
		self.assertEqual(field_diffs["script"]["change_type"], "changed")
		self.assertIn("-line 2", field_diffs["script"]["text_diff"])
		self.assertIn("+line 2 updated", field_diffs["script"]["text_diff"])
		self.assertEqual(field_diffs["config.items[0].value"]["file_value"], 2)
		self.assertEqual(field_diffs["config.items[0].value"]["db_value"], 1)

	def test_large_text_diff_is_grouped_into_hunks_with_line_numbers(self):
		from dinext_common.dinext_common.fixture_analysis.diff_engine import diff_documents

		db_script = "\n".join(
			[
				"def execute():",
				"    total = 0",
				"    for row in rows:",
				"        total += row.value",
				"    if total > 10:",
				"        return 'large'",
				"    return 'small'",
				"",
				"def format_result(value):",
				"    return f'Result: {value}'",
			]
		)
		file_script = "\n".join(
			[
				"def execute():",
				"    total = 0",
				"    for row in rows:",
				"        total += row.amount",
				"    if total >= 10:",
				"        return 'large'",
				"    return 'small'",
				"",
				"def format_result(value):",
				"    return f'Computed result: {value}'",
			]
		)

		record = diff_documents(
			"Server Script",
			[{"name": "SCRIPT-001", "script": file_script}],
			[{"name": "SCRIPT-001", "script": db_script}],
		)["records_by_name"]["SCRIPT-001"]
		field_diff = next(field for field in record["field_diffs"] if field["path"] == "script")

		self.assertIn("text_diff_hunks", field_diff)
		self.assertGreaterEqual(len(field_diff["text_diff_hunks"]), 1)
		first_hunk = field_diff["text_diff_hunks"][0]
		self.assertIn("lines", first_hunk)
		self.assertTrue(any(line["kind"] == "removed" for line in first_hunk["lines"]))
		self.assertTrue(any(line["kind"] == "added" for line in first_hunk["lines"]))
		self.assertTrue(any(line["old_lineno"] == 4 for line in first_hunk["lines"]))
		self.assertTrue(any(line["new_lineno"] == 10 for line in first_hunk["lines"]))

	def test_diff_documents_ignores_noise_fields(self):
		from dinext_common.dinext_common.fixture_analysis.diff_engine import diff_documents

		file_docs = [{"name": "EQ-001", "title": "Same", "modified": "2026-01-02 00:00:00"}]
		db_docs = [{"name": "EQ-001", "title": "Same", "modified": "2026-01-01 00:00:00"}]

		result = diff_documents("Client Script", file_docs, db_docs)

		self.assertEqual(result["counts"]["equal"], 1)
		self.assertFalse(result["records_by_name"]["EQ-001"]["field_diffs"])
