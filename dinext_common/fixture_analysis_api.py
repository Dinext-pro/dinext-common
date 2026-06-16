from __future__ import annotations

import frappe
from frappe.utils import cint

from dinext_common.dinext_common.fixture_analysis.service import (
	build_fixture_analysis_overview,
	build_fixture_analysis_record_detail,
	build_fixture_analysis_records,
)


@frappe.whitelist()
def get_fixture_analysis_overview(site: str | None = None):
	frappe.only_for("System Manager")
	return build_fixture_analysis_overview(site=site)


@frappe.whitelist()
def get_fixture_analysis_records(
	app: str,
	doctype: str,
	status: str | None = None,
	page_length: int = 50,
	start: int = 0,
	search_text: str | None = None,
	site: str | None = None,
):
	frappe.only_for("System Manager")
	return build_fixture_analysis_records(
		app=app,
		doctype=doctype,
		status=status,
		page_length=cint(page_length) or 50,
		start=cint(start),
		search_text=search_text,
		site=site,
	)


@frappe.whitelist()
def get_fixture_analysis_record_detail(app: str, doctype: str, record_key: str, site: str | None = None):
	frappe.only_for("System Manager")
	return build_fixture_analysis_record_detail(app=app, doctype=doctype, record_key=record_key, site=site)
