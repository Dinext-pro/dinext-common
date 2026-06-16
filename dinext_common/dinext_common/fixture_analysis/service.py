from __future__ import annotations

from .diff_engine import diff_documents
from .discovery import discover_fixture_catalog
from .formatters import build_detail_payload, build_overview_payload, build_records_payload
from .loader import load_fixture_docs
from .snapshot import load_live_docs


def build_fixture_analysis_overview(site: str | None = None) -> dict:
	app_results = []
	for app_info in discover_fixture_catalog(site=site):
		doctype_results = []
		app_counts = {"file_only": 0, "db_only": 0, "changed": 0, "equal": 0}
		for entry in app_info["entries"]:
			doctype_result = analyze_fixture_entry(entry)
			doctype_results.append(doctype_result)
			for key in app_counts:
				app_counts[key] += doctype_result["counts"][key]

		app_results.append(
			{
				"app": app_info["app"],
				"warnings": app_info["warnings"],
				"counts": app_counts,
				"doctypes": doctype_results,
			}
		)

	return build_overview_payload(app_results)


def build_fixture_analysis_records(
	*,
	app: str,
	doctype: str,
	status: str | None,
	page_length: int,
	start: int,
	search_text: str | None = None,
	site: str | None = None,
) -> dict:
	del site
	record_diff = analyze_fixture_entry(find_fixture_entry(app, doctype))["record_diff"]
	records = record_diff["records"]
	if search_text:
		search = search_text.casefold()
		records = [
			record
			for record in records
			if search in record["record_key"].casefold()
			or any(search in path.casefold() for path in record["changed_paths_preview"])
		]

	return build_records_payload(
		app=app,
		doctype=doctype,
		status=status,
		start=start,
		page_length=page_length,
		records=records,
	)


def build_fixture_analysis_record_detail(*, app: str, doctype: str, record_key: str, site: str | None = None) -> dict:
	del site
	record_diff = analyze_fixture_entry(find_fixture_entry(app, doctype))["record_diff"]
	record = record_diff["records_by_name"][record_key]
	return build_detail_payload(app=app, doctype=doctype, record=record)


def find_fixture_entry(app: str, doctype: str) -> dict:
	for app_info in discover_fixture_catalog():
		if app_info["app"] != app:
			continue
		for entry in app_info["entries"]:
			if entry["doctype"] == doctype:
				return entry
	raise KeyError(f"Fixture entry not found: {app}/{doctype}")


def analyze_fixture_entry(entry: dict) -> dict:
	file_docs, file_warnings = load_fixture_docs(entry)
	db_docs, db_warnings, is_single = load_live_docs(entry["doctype"], filters=entry.get("filters"))
	record_diff = diff_documents(entry["doctype"], file_docs, db_docs, is_single=is_single)

	return {
		"app": entry["app"],
		"doctype": entry["doctype"],
		"fixture_path": entry["fixture_path"],
		"source": entry["source"],
		"filters": entry.get("filters") or [],
		"is_single": is_single,
		"warnings": file_warnings + db_warnings,
		"counts": record_diff["counts"],
		"record_diff": record_diff,
	}
