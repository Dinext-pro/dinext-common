from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestFixtureAnalysisApi(FrappeTestCase):
	def test_get_fixture_analysis_overview_requires_system_manager_and_returns_service_payload(self):
		from dinext_common.fixture_analysis_api import get_fixture_analysis_overview

		payload = {"apps": [{"app": "dinext_common", "counts": {"changed": 2}}]}

		with patch("dinext_common.fixture_analysis_api.frappe.only_for") as only_for:
			with patch(
				"dinext_common.fixture_analysis_api.build_fixture_analysis_overview", return_value=payload
			) as build_overview:
				result = get_fixture_analysis_overview()

		only_for.assert_called_once_with("System Manager")
		build_overview.assert_called_once_with(site=None)
		self.assertEqual(result, payload)

	def test_get_fixture_analysis_records_passes_filters_to_service(self):
		from dinext_common.fixture_analysis_api import get_fixture_analysis_records

		payload = {"records": [{"record_key": "CHG-001", "status": "changed"}]}

		with patch("dinext_common.fixture_analysis_api.frappe.only_for"):
			with patch(
				"dinext_common.fixture_analysis_api.build_fixture_analysis_records", return_value=payload
			) as build_records:
				result = get_fixture_analysis_records(
					app="dinext_common", doctype="Server Script", status="changed", page_length=25, start=50
				)

		build_records.assert_called_once_with(
			app="dinext_common",
			doctype="Server Script",
			status="changed",
			page_length=25,
			start=50,
			search_text=None,
			site=None,
		)
		self.assertEqual(result, payload)

	def test_get_fixture_analysis_record_detail_uses_service_contract(self):
		from dinext_common.fixture_analysis_api import get_fixture_analysis_record_detail

		payload = {
			"app": "dinext_common",
			"doctype": "Server Script",
			"record_key": "CHG-001",
			"field_diffs": [{"path": "script", "change_type": "changed"}],
		}

		with patch("dinext_common.fixture_analysis_api.frappe.only_for"):
			with patch(
				"dinext_common.fixture_analysis_api.build_fixture_analysis_record_detail", return_value=payload
			) as build_detail:
				result = get_fixture_analysis_record_detail(
					app="dinext_common", doctype="Server Script", record_key="CHG-001"
				)

		build_detail.assert_called_once_with(
			app="dinext_common", doctype="Server Script", record_key="CHG-001", site=None
		)
		self.assertEqual(result["field_diffs"][0]["path"], "script")
