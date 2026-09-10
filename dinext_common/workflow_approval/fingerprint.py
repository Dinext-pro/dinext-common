"""Versioned canonical content fingerprints for approval reuse."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from frappe.utils import get_system_timezone

FINGERPRINT_VERSION = "1"

FRAMEWORK_FIELDS = {
	"_assign",
	"_comments",
	"_liked_by",
	"_seen",
	"_user_tags",
	"creation",
	"docstatus",
	"idx",
	"modified",
	"modified_by",
	"name",
	"owner",
	"parent",
	"parentfield",
	"parenttype",
}

NON_VALUE_FIELDTYPES = {
	"Button",
	"Column Break",
	"Fold",
	"HTML",
	"Heading",
	"Section Break",
	"Tab Break",
}

CHILD_IDENTITY_FIELDS = {
	"creation",
	"docstatus",
	"idx",
	"modified",
	"modified_by",
	"name",
	"owner",
	"parent",
	"parentfield",
	"parenttype",
}

REUSE_IDENTITY_FIELDS = (
	"approver",
	"reference_doctype",
	"reference_name",
	"source_created_at",
	"workflow",
	"transition_uuid",
	"transition_semantic_hash",
)


@dataclass(frozen=True)
class ContentFingerprint:
	"""Canonical payload and digest stored with an approval completion."""

	version: str
	digest: str
	canonical_json: str


def _field_value(field: object, name: str, default: object = None) -> object:
	if isinstance(field, dict):
		return field.get(name, default)
	return getattr(field, name, default)


def _decimal_text(value: Decimal) -> str:
	normalized = format(value, "f")
	if "." in normalized:
		normalized = normalized.rstrip("0").rstrip(".")
	return normalized or "0"


def _canonical_child(value: object) -> object:
	if isinstance(value, dict):
		return {
			str(key): _canonical_child(item)
			for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
			if str(key) not in CHILD_IDENTITY_FIELDS
		}
	if isinstance(value, (list, tuple)):
		return [_canonical_child(item) for item in value]
	return _canonical_scalar(value)


def _canonical_scalar(value: object, fieldtype: str | None = None) -> object:
	if value is None:
		return None
	if isinstance(value, Decimal):
		return _decimal_text(value)
	if isinstance(value, datetime):
		if value.tzinfo is None:
			value = value.replace(tzinfo=ZoneInfo(get_system_timezone()))
		return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
	if isinstance(value, (date, time)):
		return value.isoformat()
	if fieldtype == "JSON" and isinstance(value, str):
		try:
			value = json.loads(value)
		except (TypeError, ValueError):
			return value
	if isinstance(value, dict):
		return {
			str(key): _canonical_scalar(item)
			for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
		}
	if isinstance(value, (list, tuple)):
		return [_canonical_scalar(item) for item in value]
	if isinstance(value, float):
		return _decimal_text(Decimal(str(value)))
	if isinstance(value, (bool, int, str)):
		return value
	return str(value)


def fingerprint_document(
	document: dict[str, Any] | object,
	fields: list[dict[str, Any] | object],
	*,
	workflow_state_field: str | None = None,
	workflow_update_field: str | None = None,
	excluded_fields: set[str] | None = None,
	version: str = FINGERPRINT_VERSION,
) -> ContentFingerprint:
	"""Return a fail-closed fingerprint over persisted business fields."""
	excluded = set(excluded_fields or ())
	excluded.update(FRAMEWORK_FIELDS)
	excluded.update(filter(None, (workflow_state_field, workflow_update_field)))
	values: dict[str, object] = {}
	schema: list[dict[str, object]] = []

	for field in fields:
		fieldname = str(_field_value(field, "fieldname", "") or "")
		fieldtype = str(_field_value(field, "fieldtype", "") or "")
		if (
			not fieldname
			or fieldname in excluded
			or fieldtype in NON_VALUE_FIELDTYPES
			or fieldtype == "Password"
			or bool(_field_value(field, "virtual", False))
			or bool(_field_value(field, "is_virtual", False))
			or bool(_field_value(field, "non_db", False))
		):
			continue

		schema.append(
			{
				"fieldname": fieldname,
				"fieldtype": fieldtype,
				"options": _field_value(field, "options") or None,
			}
		)
		if isinstance(document, dict):
			value = document.get(fieldname)
		else:
			value = getattr(document, fieldname, None)
		if fieldtype in {"Table", "Table MultiSelect"}:
			values[fieldname] = _canonical_child(value or [])
		else:
			values[fieldname] = _canonical_scalar(value, fieldtype)

	payload = {"schema": schema, "values": values, "version": version}
	canonical_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
	return ContentFingerprint(
		version=version,
		digest=hashlib.sha256(canonical_json.encode()).hexdigest(),
		canonical_json=canonical_json,
	)


def find_latest_reusable_task(
	tasks: list[dict[str, Any] | object],
	**criteria: object,
) -> dict[str, Any] | object | None:
	"""Return the latest identity-matching completion only when its fingerprint matches."""
	identity_matches = []
	for task in tasks:
		get = task.get if isinstance(task, dict) else lambda key, default=None: getattr(task, key, default)
		if get("status") != "Completed":
			continue
		if any(get(field) != criteria.get(field) for field in REUSE_IDENTITY_FIELDS):
			continue
		if not get("content_fingerprint") or not get("content_fingerprint_version"):
			continue
		identity_matches.append(task)

	if not identity_matches:
		return None

	def completed_at(task: dict[str, Any] | object) -> str:
		if isinstance(task, dict):
			return str(task.get("completed_at") or "")
		return str(getattr(task, "completed_at", "") or "")

	latest = max(identity_matches, key=completed_at)
	get = latest.get if isinstance(latest, dict) else lambda key, default=None: getattr(latest, key, default)
	if (
		get("content_fingerprint_version") != criteria.get("content_fingerprint_version")
		or get("content_fingerprint") != criteria.get("content_fingerprint")
	):
		return None
	return latest
