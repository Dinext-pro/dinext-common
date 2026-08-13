# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Permission-aware personal list builders for Dinext Hub section lists."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from dinext_common.setup.hub_catalog import DEFAULT_SECTION_CARD_COLUMNS, DEFAULT_SECTION_LIST_LIMIT

FLAG_FIELDS = (
	"show_quick_create",
	"show_assigned",
	"show_liked",
	"show_attention",
)


def get_section_limits(settings) -> dict[str, int]:
	limits: dict[str, int] = {}
	for row in settings.get("sections") or []:
		section = (row.section or "").strip()
		if not section:
			continue
		try:
			limit = int(row.list_limit or DEFAULT_SECTION_LIST_LIMIT)
		except (TypeError, ValueError):
			limit = DEFAULT_SECTION_LIST_LIMIT
		limits[section] = max(limit, 1)
	return limits


def get_section_card_columns(settings) -> dict[str, int]:
	columns: dict[str, int] = {}
	for row in settings.get("sections") or []:
		section = (row.section or "").strip()
		if not section:
			continue
		try:
			value = int(getattr(row, "card_columns", None) or DEFAULT_SECTION_CARD_COLUMNS)
		except (TypeError, ValueError):
			value = DEFAULT_SECTION_CARD_COLUMNS
		columns[section] = value if value >= 1 else DEFAULT_SECTION_CARD_COLUMNS
	return columns


def merge_doctype_contributions(settings) -> dict[tuple[str, str], dict[str, Any]]:
	"""Merge enabled contributions keyed by (section, document_type)."""
	merged: dict[tuple[str, str], dict[str, Any]] = {}

	for row in settings.get("doctype_items") or []:
		if not row.enabled:
			continue
		section = (row.section or "").strip()
		document_type = row.document_type
		if not section or not document_type:
			continue
		if not frappe.db.exists("DocType", document_type):
			continue

		key = (section, document_type)
		bucket = merged.setdefault(
			key,
			{
				"section": section,
				"document_type": document_type,
				"show_quick_create": 0,
				"show_assigned": 0,
				"show_liked": 0,
				"show_attention": 0,
				"attention_filters": [],
				"assigned_filters": [],
				"liked_filters": [],
			},
		)
		for flag in FLAG_FIELDS:
			if row.get(flag):
				bucket[flag] = 1
		if row.get("show_attention"):
			parsed = parse_attention_filter(row.get("attention_filter"), document_type)
			if parsed is not None:
				bucket["attention_filters"].append(parsed)
		list_filter = parse_list_filter(row.get("list_filter"), document_type)
		if row.get("show_assigned") and list_filter is not None:
			bucket["assigned_filters"].append(list_filter)
		if row.get("show_liked") and list_filter is not None:
			bucket["liked_filters"].append(list_filter)

	return merged


def parse_attention_filter(raw: Any, document_type: str) -> list | None:
	"""Parse Attention filter JSON. Returns None when invalid."""
	return parse_filter_json(raw, document_type, title="Dinext Hub invalid attention filter")


def parse_list_filter(raw: Any, document_type: str) -> list | None:
	"""Parse Assigned/Liked list filter JSON. Returns None when invalid."""
	return parse_filter_json(raw, document_type, title="Dinext Hub invalid list filter")


def parse_filter_json(raw: Any, document_type: str, *, title: str) -> list | None:
	"""Parse and normalize Frappe filter JSON. Returns None when invalid."""
	if raw in (None, "", [], {}):
		return []

	try:
		value = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError, json.JSONDecodeError):
		frappe.log_error(
			title=title,
			message=f"DocType={document_type} filter={cstr(raw)[:500]}",
		)
		return None

	if not isinstance(value, list):
		frappe.log_error(
			title=title,
			message=f"DocType={document_type} expected list, got {type(value)}",
		)
		return None

	normalized: list = []
	for item in value:
		if not isinstance(item, (list, tuple)) or len(item) < 3:
			frappe.log_error(
				title=title,
				message=f"DocType={document_type} bad clause={item!r}",
			)
			return None

		# Number Card style: [doctype, field, op, value, ...]
		if len(item) >= 4 and item[0] == document_type:
			clause = [item[1], item[2], item[3]]
		else:
			clause = [item[0], item[1], item[2]]

		normalized.append(clause)

	return normalized


def build_section_personal_lists(
	section: str,
	configs: list[dict[str, Any]],
	*,
	limit: int,
) -> dict[str, Any] | None:
	"""Aggregate personal lists and create actions for one Hub section."""
	show_assigned = False
	show_liked = False
	show_attention = False
	create_actions: list[dict] = []
	assigned: list[dict] = []
	liked: list[dict] = []
	attention: list[dict] = []

	for config in configs:
		document_type = config["document_type"]
		if not frappe.has_permission(document_type, "read"):
			continue

		type_meta = _doctype_display(document_type)

		if config.get("show_quick_create") and frappe.has_permission(document_type, "create"):
			create_actions.append(
				{
					"doctype": document_type,
					"label": type_meta["type_label"],
					"icon": type_meta["icon"],
				}
			)

		if config.get("show_assigned"):
			show_assigned = True
			assigned.extend(
				get_assigned_records(
					document_type,
					filters_list=config.get("assigned_filters") or [],
					limit=limit,
				)
			)

		if config.get("show_liked"):
			show_liked = True
			liked.extend(
				get_liked_records(
					document_type,
					filters_list=config.get("liked_filters") or [],
					limit=limit,
				)
			)

		if config.get("show_attention"):
			show_attention = True
			attention.extend(
				get_attention_records(
					document_type,
					filters_list=config.get("attention_filters") or [],
					limit=limit,
				)
			)

	if not any([create_actions, show_assigned, show_liked, show_attention]):
		return None

	return {
		"list_limit": limit,
		"show_assigned": show_assigned,
		"show_liked": show_liked,
		"show_attention": show_attention,
		"create_actions": create_actions,
		"assigned": _merge_records(assigned, limit=limit),
		"liked": _merge_records(liked, limit=limit),
		"attention": _merge_records(attention, limit=limit),
	}


def build_doctype_block(document_type: str, config: dict[str, Any], *, limit: int) -> dict[str, Any] | None:
	"""Legacy helper retained for tests that still exercise single-DocType formatting."""
	section_payload = build_section_personal_lists(
		config.get("section") or "",
		[config],
		limit=limit,
	)
	if not section_payload:
		return None
	type_meta = _doctype_display(document_type)
	return {
		"doctype": document_type,
		"label": type_meta["type_label"],
		"show_quick_create": bool(config.get("show_quick_create"))
		and frappe.has_permission(document_type, "create"),
		"show_assigned": bool(config.get("show_assigned")),
		"show_liked": bool(config.get("show_liked")),
		"show_attention": bool(config.get("show_attention")),
		"list_limit": limit,
		"assigned": section_payload["assigned"],
		"liked": section_payload["liked"],
		"attention": section_payload["attention"],
	}


def get_recent_records(allowed_doctypes: list[str], *, limit: int) -> list[dict]:
	"""Build recently opened docs from persistent Route History for the current user."""
	allowed = [dt for dt in allowed_doctypes if dt and frappe.db.exists("DocType", dt)]
	if not allowed or limit < 1:
		return []

	slug_to_doctype = {
		frappe.scrub(dt).replace("_", "-"): dt for dt in allowed
	}
	allowed_set = set(allowed)

	# Route History is System Manager-readable only; filter by current user explicitly.
	rows = frappe.get_all(
		"Route History",
		filters={"user": frappe.session.user},
		fields=["route", "creation"],
		order_by="creation desc",
		limit_page_length=max(limit * 40, 40),
		ignore_permissions=True,
	)

	ordered: list[tuple[str, str, Any]] = []
	seen: set[tuple[str, str]] = set()
	for row in rows:
		parsed = _parse_route_history_route(row.route or "", allowed_set, slug_to_doctype)
		if not parsed:
			continue
		document_type, name = parsed
		key = (document_type, name)
		if key in seen:
			continue
		seen.add(key)
		ordered.append((document_type, name, row.creation))
		if len(ordered) >= limit:
			break

	# Preserve Route History order while enriching titles/permissions per DocType.
	by_doctype: dict[str, list[str]] = {}
	modified_by_key: dict[tuple[str, str], Any] = {}
	for document_type, name, creation in ordered:
		by_doctype.setdefault(document_type, []).append(name)
		modified_by_key[(document_type, name)] = creation

	formatted_by_key: dict[tuple[str, str], dict] = {}
	for document_type, names in by_doctype.items():
		for record in format_records(
			document_type,
			names,
			limit=len(names),
			modified_by_name={name: modified_by_key[(document_type, name)] for name in names},
		):
			formatted_by_key[(document_type, record["name"])] = record

	return [
		formatted_by_key[key]
		for key in ((document_type, name) for document_type, name, _ in ordered)
		if key in formatted_by_key
	][:limit]


def _parse_route_history_route(
	route: str,
	allowed_set: set[str],
	slug_to_doctype: dict[str, str],
) -> tuple[str, str] | None:
	raw = cstr(route).strip().strip("/")
	if not raw:
		return None

	if raw.startswith("app/"):
		raw = raw[4:]
	parts = [part for part in raw.split("/") if part]
	if len(parts) < 2:
		return None

	if parts[0] == "Form" and len(parts) >= 3:
		document_type = parts[1]
		name = "/".join(parts[2:])
		if document_type in allowed_set and name:
			return document_type, name
		return None

	# Desk path style: <doctype-slug>/<name>
	slug = parts[0]
	document_type = slug_to_doctype.get(slug)
	if not document_type and parts[0] in allowed_set:
		document_type = parts[0]
	name = "/".join(parts[1:])
	if document_type and name and document_type in allowed_set:
		return document_type, name
	return None


def get_assigned_records(document_type: str, *, limit: int, filters_list: list | None = None) -> list[dict]:
	todos = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": document_type,
			"allocated_to": frappe.session.user,
			"status": ("not in", ("Cancelled", "Closed")),
			"reference_name": ("is", "set"),
		},
		fields=["reference_name", "modified"],
		order_by="modified desc",
		limit_page_length=max(limit * 5, limit),
	)

	seen: set[str] = set()
	ordered: list[tuple[str, Any]] = []
	for todo in todos:
		name = todo.reference_name
		if not name or name in seen:
			continue
		seen.add(name)
		ordered.append((name, todo.modified))
		if len(ordered) >= limit * 3:
			break

	names = [name for name, _ in ordered]
	allowed = _names_matching_filters(document_type, names, filters_list)
	if allowed is not None:
		ordered = [(name, modified) for name, modified in ordered if name in allowed]
		names = [name for name, _ in ordered]

	return format_records(document_type, names, limit=limit, modified_by_name=dict(ordered))


def get_liked_records(document_type: str, *, limit: int, filters_list: list | None = None) -> list[dict]:
	user = frappe.session.user
	if not filters_list:
		filters_list = [[]]

	by_name: dict[str, Any] = {}
	for filters in filters_list:
		liked_filters: list = [["_liked_by", "like", f"%{user}%"]]
		if filters:
			liked_filters.extend(filters)
		try:
			rows = frappe.get_list(
				document_type,
				filters=liked_filters,
				fields=["name", "modified"],
				order_by="modified desc",
				limit_page_length=limit,
				ignore_permissions=False,
			)
		except Exception:
			frappe.log_error(
				title="Dinext Hub liked list failed",
				message=f"DocType={document_type} filters={filters!r}",
			)
			continue
		for row in rows:
			if row.name and row.name not in by_name:
				by_name[row.name] = row.modified

	ordered = sorted(by_name.items(), key=lambda item: item[1] or "", reverse=True)
	names = [name for name, _ in ordered]
	return format_records(document_type, names, limit=limit, modified_by_name=by_name)


def _names_matching_filters(document_type: str, names: list[str], filters_list: list | None) -> set[str] | None:
	"""Intersect names with each list filter and union the matches.

	Returns None when there is no extra restriction (empty/missing filters).
	"""
	if not names:
		return set()
	if not filters_list:
		return None

	allowed: set[str] | None = None
	for filters in filters_list:
		if not filters:
			return None
		try:
			rows = frappe.get_list(
				document_type,
				filters=list(filters) + [["name", "in", names]],
				fields=["name"],
				limit_page_length=len(names),
				ignore_permissions=False,
			)
		except Exception:
			frappe.log_error(
				title="Dinext Hub assigned list filter failed",
				message=f"DocType={document_type} filters={filters!r}",
			)
			continue
		matched = {row.name for row in rows if row.name}
		allowed = matched if allowed is None else allowed | matched

	return allowed if allowed is not None else set()


def get_attention_records(document_type: str, *, filters_list: list, limit: int) -> list[dict]:
	if not filters_list:
		# Attention enabled with empty filter means all readable docs (capped)
		filters_list = [[]]

	by_name: dict[str, Any] = {}
	for filters in filters_list:
		try:
			rows = frappe.get_list(
				document_type,
				filters=filters or None,
				fields=["name", "modified"],
				order_by="modified desc",
				limit_page_length=limit,
				ignore_permissions=False,
			)
		except Exception:
			frappe.log_error(
				title="Dinext Hub attention list failed",
				message=f"DocType={document_type} filters={filters!r}",
			)
			continue
		for row in rows:
			if row.name and row.name not in by_name:
				by_name[row.name] = row.modified

	ordered = sorted(by_name.items(), key=lambda item: item[1] or "", reverse=True)
	names = [name for name, _ in ordered[: limit * 2]]
	return format_records(document_type, names, limit=limit, modified_by_name=by_name)


def format_records(
	document_type: str,
	names: list[str],
	*,
	limit: int,
	modified_by_name: dict[str, Any] | None = None,
) -> list[dict]:
	records: list[dict] = []
	meta = frappe.get_meta(document_type)
	title_field = meta.get_title_field()
	fields = ["name", "modified"]
	if title_field and title_field != "name" and meta.has_field(title_field):
		fields.append(title_field)
	type_meta = _doctype_display(document_type)

	for name in names:
		if len(records) >= limit:
			break
		if not frappe.db.exists(document_type, name):
			continue
		if not frappe.has_permission(document_type, "read", name):
			continue

		values = frappe.db.get_value(document_type, name, fields, as_dict=True) or {}
		title = ""
		if title_field and title_field != "name":
			title = cstr(values.get(title_field) or "")
		if not title:
			title = cstr(values.get("name") or name)

		modified = None
		if modified_by_name and name in modified_by_name:
			modified = modified_by_name[name]
		else:
			modified = values.get("modified")

		records.append(
			{
				"doctype": document_type,
				"type_label": type_meta["type_label"],
				"icon": type_meta["icon"],
				"name": name,
				"title": title,
				"modified": cstr(modified or ""),
				"route": f"/app/{frappe.scrub(document_type).replace('_', '-')}/{name}",
			}
		)

	return records


def _merge_records(records: list[dict], *, limit: int) -> list[dict]:
	seen: set[tuple[str, str]] = set()
	unique: list[dict] = []
	for row in records:
		key = (row.get("doctype") or "", row.get("name") or "")
		if not key[0] or not key[1] or key in seen:
			continue
		seen.add(key)
		unique.append(row)

	unique.sort(key=lambda row: row.get("modified") or "", reverse=True)
	return unique[:limit]


def _doctype_display(document_type: str) -> dict[str, str]:
	meta = frappe.get_meta(document_type)
	icon = ""
	if getattr(meta, "icon", None):
		icon = cstr(meta.icon)
	return {
		"type_label": _(meta.name or document_type),
		"icon": icon,
	}
