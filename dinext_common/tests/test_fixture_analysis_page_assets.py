import json
from pathlib import Path
import unittest


class TestFixtureAnalysisPageAssets(unittest.TestCase):
	def test_fixture_analysis_standard_page_files_exist(self):
		base_path = (
			Path(__file__).resolve().parents[1] / "dinext_common" / "page" / "fixture_analysis"
		)
		page_json = json.loads((base_path / "fixture_analysis.json").read_text(encoding="utf-8"))

		self.assertTrue((base_path / "__init__.py").exists())
		self.assertTrue((base_path / "fixture_analysis.js").exists())
		self.assertEqual(page_json["doctype"], "Page")
		self.assertEqual(page_json["name"], "fixture-analysis")
		self.assertEqual(page_json["title"], "Fixture Analysis")
