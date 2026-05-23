from __future__ import annotations


def build_overview_payload(app_results: list[dict]) -> dict:
	counts = {"file_only": 0, "db_only": 0, "changed": 0, "equal": 0}
	for app_result in app_results:
		for key in counts:
			counts[key] += app_result["counts"][key]

	return {
		"apps": [compact_app_result(app_result) for app_result in app_results],
		"counts": counts,
	}


def build_records_payload(
	*, app: str, doctype: str, status: str | None, start: int, page_length: int, records: list[dict]
) -> dict:
	filtered_records = [record for record in records if not status or status == "all" or record["status"] == status]
	page_records = filtered_records[start : start + page_length]
	return {
		"app": app,
		"doctype": doctype,
		"status": status or "all",
		"total_count": len(filtered_records),
		"start": start,
		"page_length": page_length,
		"has_more": start + page_length < len(filtered_records),
		"records": [compact_record_summary(record) for record in page_records],
	}


def build_detail_payload(*, app: str, doctype: str, record: dict) -> dict:
	return {
		"app": app,
		"doctype": doctype,
		"record_key": record["record_key"],
		"status": record["status"],
		"system_route": build_system_route(record),
		"field_diffs": record["field_diffs"],
		"file_doc": record.get("file_doc"),
		"db_doc": record.get("db_doc"),
	}


def compact_app_result(app_result: dict) -> dict:
	return {
		"app": app_result["app"],
		"warnings": app_result.get("warnings", []),
		"counts": app_result["counts"],
		"doctypes": [compact_doctype_summary(doctype_result) for doctype_result in app_result.get("doctypes", [])],
	}


def compact_doctype_summary(doctype_result: dict) -> dict:
	return {
		"app": doctype_result["app"],
		"doctype": doctype_result["doctype"],
		"fixture_path": doctype_result.get("fixture_path"),
		"source": doctype_result.get("source"),
		"filters": doctype_result.get("filters", []),
		"is_single": doctype_result.get("is_single", False),
		"warnings": doctype_result.get("warnings", []),
		"counts": doctype_result["counts"],
	}


def compact_record_summary(record: dict) -> dict:
	return {
		"record_key": record["record_key"],
		"name": record.get("name"),
		"status": record["status"],
		"system_route": build_system_route(record),
		"field_diff_count": record.get("field_diff_count", 0),
		"text_diff_count": record.get("text_diff_count", 0),
		"changed_paths_preview": record.get("changed_paths_preview", []),
	}


def build_system_route(record: dict) -> dict | None:
	if not record.get("db_doc"):
		return None

	doctype = record.get("doctype")
	if not doctype:
		return None

	if record.get("is_single"):
		return {"doctype": doctype, "name": doctype}

	name = record.get("name") or record["db_doc"].get("name") or record.get("record_key")
	if not name:
		return None

	return {"doctype": doctype, "name": name}
