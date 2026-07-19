from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from difflib import SequenceMatcher, unified_diff

from .constants import IGNORED_FIELDNAMES


def diff_documents(doctype: str, file_docs: list[dict], db_docs: list[dict], *, is_single: bool = False) -> dict:
	file_map = {get_record_key(doctype, doc, is_single=is_single): sanitize_record(doc) for doc in file_docs}
	db_map = {get_record_key(doctype, doc, is_single=is_single): sanitize_record(doc) for doc in db_docs}
	record_keys = sorted(set(file_map) | set(db_map))
	records: list[dict] = []
	counts = {"file_only": 0, "db_only": 0, "changed": 0, "equal": 0}

	for record_key in record_keys:
		file_doc = file_map.get(record_key)
		db_doc = db_map.get(record_key)
		record = build_record_diff(doctype, record_key, file_doc=file_doc, db_doc=db_doc, is_single=is_single)
		counts[record["status"]] += 1
		records.append(record)

	return {
		"doctype": doctype,
		"is_single": is_single,
		"counts": counts,
		"records": records,
		"records_by_name": {record["record_key"]: record for record in records},
	}


def build_record_diff(
	doctype: str, record_key: str, *, file_doc: dict | None, db_doc: dict | None, is_single: bool = False
) -> dict:
	if file_doc and not db_doc:
		status = "file_only"
		field_diffs = build_field_diffs(file_doc, {})
	elif db_doc and not file_doc:
		status = "db_only"
		field_diffs = build_field_diffs({}, db_doc)
	else:
		field_diffs = build_field_diffs(file_doc or {}, db_doc or {})
		status = "changed" if field_diffs else "equal"

	return {
		"doctype": doctype,
		"is_single": is_single,
		"record_key": record_key,
		"name": None if is_single else record_key,
		"status": status,
		"field_diff_count": len(field_diffs),
		"text_diff_count": sum(1 for field in field_diffs if field.get("text_diff")),
		"changed_paths_preview": [field["path"] for field in field_diffs[:5]],
		"field_diffs": field_diffs,
		"file_doc": deepcopy(file_doc),
		"db_doc": deepcopy(db_doc),
	}


def build_field_diffs(file_doc: dict, db_doc: dict) -> list[dict]:
	file_flat = flatten_document(file_doc)
	db_flat = flatten_document(db_doc)
	paths = sorted(set(file_flat) | set(db_flat))
	field_diffs = []

	for path in paths:
		file_value = file_flat.get(path)
		db_value = db_flat.get(path)
		if values_equal(file_value, db_value):
			continue

		field_diffs.append(
			build_field_diff_entry(path=path, file_value=file_value, db_value=db_value, file_flat=file_flat, db_flat=db_flat)
		)

	return field_diffs


def get_record_key(doctype: str, doc: dict, *, is_single: bool = False) -> str:
	if is_single:
		return f"single::{doctype}"
	return str(doc.get("name"))


def sanitize_record(doc: dict | None) -> dict:
	return deepcopy(doc or {})


def flatten_document(doc: dict) -> dict:
	flat: dict[str, object] = {}
	for key, value in sorted((doc or {}).items()):
		if key in IGNORED_FIELDNAMES or key.startswith("__"):
			continue
		flatten_value(key, value, flat)
	return flat


def flatten_value(path: str, value, flat: dict[str, object]) -> None:
	if isinstance(value, dict):
		if not value:
			flat[path] = {}
			return

		for child_key, child_value in sorted(value.items()):
			if child_key in IGNORED_FIELDNAMES or str(child_key).startswith("__"):
				continue
			child_path = f"{path}.{child_key}"
			flatten_value(child_path, child_value, flat)
		return

	if isinstance(value, list):
		if not value:
			flat[path] = []
			return

		for idx, item in enumerate(value):
			child_path = f"{path}[{idx}]"
			flatten_value(child_path, item, flat)
		return

	flat[path] = value


def values_equal(left, right) -> bool:
	return left == right


def get_change_type(path: str, file_flat: dict, db_flat: dict) -> str:
	in_file = path in file_flat
	in_db = path in db_flat
	if in_file and not in_db:
		return "added"
	if in_db and not in_file:
		return "removed"
	return "changed"


def build_field_diff_entry(*, path: str, file_value, db_value, file_flat: dict, db_flat: dict) -> dict:
	text_diff_payload = build_text_diff_payload(file_value, db_value)
	return {
		"path": path,
		"top_level_field": path.split(".", 1)[0].split("[", 1)[0],
		"change_type": get_change_type(path, file_flat, db_flat),
		"file_value": deepcopy(file_value),
		"db_value": deepcopy(db_value),
		"text_diff": text_diff_payload["text_diff"],
		"text_diff_hunks": text_diff_payload["text_diff_hunks"],
		"text_diff_is_multiline": text_diff_payload["is_multiline"],
	}


def build_text_diff(file_value, db_value) -> str | None:
	return build_text_diff_payload(file_value, db_value)["text_diff"]


def build_text_diff_payload(file_value, db_value) -> dict:
	if not should_render_text_diff(file_value, db_value):
		return {
			"text_diff": None,
			"text_diff_hunks": [],
			"is_multiline": False,
		}

	file_text = stringify_value(file_value).splitlines()
	db_text = stringify_value(db_value).splitlines()
	text_diff = "\n".join(
		unified_diff(db_text, file_text, fromfile="db", tofile="fixture", lineterm="", n=1)
	)
	return {
		"text_diff": text_diff,
		"text_diff_hunks": build_text_diff_hunks(db_text, file_text),
		"is_multiline": len(file_text) > 1 or len(db_text) > 1,
	}


def build_text_diff_hunks(db_lines: list[str], file_lines: list[str], *, context_lines: int = 3) -> list[dict]:
	matcher = SequenceMatcher(None, db_lines, file_lines)
	hunks = []

	for group in matcher.get_grouped_opcodes(context_lines):
		hunk_lines = []
		old_start = None
		new_start = None

		for tag, i1, i2, j1, j2 in group:
			if old_start is None and tag != "insert":
				old_start = i1 + 1
			if new_start is None and tag != "delete":
				new_start = j1 + 1

			if tag == "equal":
				for old_idx, new_idx in zip(range(i1, i2), range(j1, j2), strict=False):
					hunk_lines.append(
						make_hunk_line(
							kind="context",
							text=db_lines[old_idx],
							old_lineno=old_idx + 1,
							new_lineno=new_idx + 1,
						)
					)
			elif tag == "delete":
				for old_idx in range(i1, i2):
					hunk_lines.append(
						make_hunk_line(
							kind="removed",
							text=db_lines[old_idx],
							old_lineno=old_idx + 1,
							new_lineno=None,
						)
					)
			elif tag == "insert":
				for new_idx in range(j1, j2):
					hunk_lines.append(
						make_hunk_line(
							kind="added",
							text=file_lines[new_idx],
							old_lineno=None,
							new_lineno=new_idx + 1,
						)
					)
			elif tag == "replace":
				max_len = max(i2 - i1, j2 - j1)
				for offset in range(max_len):
					old_idx = i1 + offset
					new_idx = j1 + offset
					if old_idx < i2:
						hunk_lines.append(
							make_hunk_line(
								kind="removed",
								text=db_lines[old_idx],
								old_lineno=old_idx + 1,
								new_lineno=None,
							)
						)
					if new_idx < j2:
						hunk_lines.append(
							make_hunk_line(
								kind="added",
								text=file_lines[new_idx],
								old_lineno=None,
								new_lineno=new_idx + 1,
							)
						)

		hunks.append(
			{
				"old_start": old_start,
				"new_start": new_start,
				"lines": hunk_lines,
			}
		)

	return hunks


def make_hunk_line(*, kind: str, text: str, old_lineno: int | None, new_lineno: int | None) -> dict:
	return {
		"kind": kind,
		"text": text,
		"old_lineno": old_lineno,
		"new_lineno": new_lineno,
	}


def should_render_text_diff(file_value, db_value) -> bool:
	return isinstance(file_value, (str, dict, list)) or isinstance(db_value, (str, dict, list))


def stringify_value(value) -> str:
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	if isinstance(value, dict):
		lines = []
		for key, child in sorted(value.items()):
			if key in IGNORED_FIELDNAMES or str(key).startswith("__"):
				continue
			lines.extend(prefix_lines(f"{key}: ", stringify_value(child).splitlines() or [""]))
		return "\n".join(lines)
	if isinstance(value, list):
		lines = []
		for idx, child in enumerate(value):
			lines.extend(prefix_lines(f"[{idx}] ", stringify_value(child).splitlines() or [""]))
		return "\n".join(lines)
	return str(value)


def prefix_lines(prefix: str, lines: Iterable[str]) -> list[str]:
	lines = list(lines)
	if not lines:
		return [prefix.rstrip()]
	return [f"{prefix}{lines[0]}"] + [line for line in lines[1:]]
