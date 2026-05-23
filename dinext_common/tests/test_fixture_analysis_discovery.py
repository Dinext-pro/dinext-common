from pathlib import Path
import unittest


class TestFixtureAnalysisDiscovery(unittest.TestCase):
	def test_normalize_fixture_entry_supports_dt_alias(self):
		from dinext_common.dinext_common.fixture_analysis.discovery import normalize_fixture_entry

		entry = normalize_fixture_entry(
			"insights",
			Path("/tmp/insights"),
			{"dt": "Insights Data Source", "filters": {"name": ("in", ["Site DB"])}},
		)

		self.assertEqual(entry["doctype"], "Insights Data Source")
		self.assertEqual(entry["filters"], {"name": ("in", ["Site DB"])})
		self.assertEqual(entry["fixture_path"], "/tmp/insights/fixtures/insights_data_source.json")
