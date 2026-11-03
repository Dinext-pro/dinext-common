"""Per-Workflow content exclusions, validated against source metadata."""

from __future__ import annotations

import frappe
from frappe import _

from dinext_common.workflow_approval.fingerprint import (
	CHILD_IDENTITY_FIELDS,
	FRAMEWORK_FIELDS,
	NON_VALUE_FIELDTYPES,
)

EXCLUSIONS_FIELD = "custom_fingerprint_excluded_fields"
TABLE_TYPES = {"Table", "Table MultiSelect"}


def _value(obj, key, default=None):
	return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def configured_exclusions(workflow) -> set[str]:
	return {
		str(_value(row, "field_path") or "").strip()
		for row in (_value(workflow, EXCLUSIONS_FIELD, []) or [])
		if str(_value(row, "field_path") or "").strip()
	}


def _is_content_field(field, excluded) -> bool:
	return bool(_value(field, "fieldname")) and not (
		_value(field, "fieldname") in excluded
		or _value(field, "fieldtype") in NON_VALUE_FIELDTYPES | {"Password"}
		or any(_value(field, key) for key in ("virtual", "is_virtual", "non_db"))
	)


def selectable_paths(workflow) -> set[str]:
	"""Return persisted source paths, including whole tables and their child values."""
	doctype = _value(workflow, "document_type")
	if not doctype:
		return set()
	excluded = FRAMEWORK_FIELDS | {
		_value(workflow, "workflow_state_field"),
		*(_value(row, "update_field") for row in (_value(workflow, "states", []) or [])),
	}
	result = set()
	for field in frappe.get_meta(doctype).fields:
		if not _is_content_field(field, excluded):
			continue
		name = _value(field, "fieldname")
		result.add(name)
		if _value(field, "fieldtype") in TABLE_TYPES and _value(field, "options"):
			for child in frappe.get_meta(_value(field, "options")).fields:
				if (
					_is_content_field(child, CHILD_IDENTITY_FIELDS)
					and _value(child, "fieldtype") not in TABLE_TYPES
				):
					result.add(f"{name}.{_value(child, 'fieldname')}")
	return result


def validate_exclusions(workflow) -> None:
	rows = _value(workflow, EXCLUSIONS_FIELD, []) or []
	if not rows:
		return
	allowed = selectable_paths(workflow)
	seen = set()
	for index, row in enumerate(rows, 1):
		path = str(_value(row, "field_path") or "").strip()
		if not path:
			raise ValueError(_("Row {0}: select a field to exclude from the snapshot.").format(index))
		if path not in allowed:
			raise ValueError(
				_("Row {0}: field path {1} is not available for {2}.").format(
					index, path, _value(workflow, "document_type") or ""
				)
			)
		if path in seen:
			raise ValueError(_("Row {0}: field path {1} is duplicated.").format(index, path))
		seen.add(path)
		if isinstance(row, dict):
			row["field_path"] = path
		else:
			row.field_path = path


def preserve_fixture_exclusions(doc, method=None) -> None:
	"""Fixture defaults must not replace an administrator's existing snapshot settings."""
	if not frappe.flags.in_fixtures or not doc.meta.has_field(EXCLUSIONS_FIELD):
		return
	if not frappe.db.exists("Workflow", doc.name):
		return
	existing = frappe.get_doc("Workflow", doc.name)
	doc.set(EXCLUSIONS_FIELD, [row.as_dict() for row in existing.get(EXCLUSIONS_FIELD) or []])
