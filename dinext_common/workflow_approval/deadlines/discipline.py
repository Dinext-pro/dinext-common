"""One approval-discipline observation per real personal obligation."""

from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def _datetime(value, site_timezone="UTC"):
	if not value:
		return None
	result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
	return (result.replace(tzinfo=ZoneInfo(site_timezone)) if result.tzinfo is None else result).astimezone(
		timezone.utc
	)


def observations(rows, *, now, site_timezone="UTC"):
	grouped = defaultdict(list)
	for row in rows:
		if not row.get("deadline_assignment_id") or row.get("status") == "Cancelled":
			continue
		if row.get("status") == "Completed" and str(row.get("completion_source") or "").startswith(
			("Automatic", "Carried")
		):
			continue
		grouped[row["deadline_assignment_id"]].append(row)
	result = []
	current = _datetime(now, site_timezone)
	for items in grouped.values():
		row = dict(
			max(
				items,
				key=lambda item: (
					item.get("status") == "Completed",
					str(item.get("creation") or ""),
					item["name"],
				),
			)
		)
		due = _datetime(row.get("deadline_due_at"), site_timezone)
		completed = _datetime(row.get("completed_at"), site_timezone)
		status = (
			"Error"
			if row.get("deadline_error")
			else "Unknown"
			if not due
			else "On Time"
			if row.get("status") == "Completed" and completed and completed <= due
			else "Completed Late"
			if row.get("status") == "Completed" and completed
			else "Overdue"
			if row.get("status") == "Working" and due < current
			else "Pending"
		)
		row["discipline_status"] = status
		row["delay_hours"] = max(0, ((completed or current) - due).total_seconds() / 3600) if due else None
		row["due_date"] = (
			due.astimezone(ZoneInfo(row.get("deadline_timezone") or site_timezone)).date() if due else None
		)
		result.append(row)
	return result


def summarize(rows, *, from_date, to_date, now, site_timezone="UTC"):
	start = date.fromisoformat(str(from_date)[:10])
	end = date.fromisoformat(str(to_date)[:10])
	items = observations(rows, now=now, site_timezone=site_timezone)
	cohort = [row for row in items if row["due_date"] and start <= row["due_date"] <= end]
	eligible = [row for row in cohort if row["discipline_status"] in ("On Time", "Completed Late", "Overdue")]
	on_time = sum(row["discipline_status"] == "On Time" for row in eligible)
	return dict(
		observations=len(eligible),
		on_time=on_time,
		on_time_percent=100 * on_time / len(eligible) if eligible else None,
		completed_late=sum(row["discipline_status"] == "Completed Late" for row in eligible),
		open_overdue=sum(row["discipline_status"] == "Overdue" for row in items),
		errors=sum(row["discipline_status"] in ("Error", "Unknown") for row in items),
		rows=cohort,
		all_rows=items,
	)


def _candidate_rows(filters, fields):
	"""Trusted discovery: current work or the selected due cohort, never all history."""
	import frappe
	from frappe.utils import add_days, getdate, nowdate

	query = {"deadline_assignment_id": ["is", "set"], "status": ["!=", "Cancelled"]}
	for field in ("approver", "workflow", "workflow_state", "reference_doctype", "reference_name"):
		if filters.get(field):
			query[field] = filters[field]
	start = getdate(filters.get("from_date") or add_days(nowdate(), -29))
	end = getdate(filters.get("to_date") or nowdate())
	# Recipient offsets can put a due date on a neighbouring site date.
	# Exact cohort selection follows authorization in summarize().
	bounds = [str(add_days(start, -2)) + " 00:00:00", str(add_days(end, 2)) + " 23:59:59.999999"]
	return frappe.get_all(
		"Workflow Task",
		filters=query,
		or_filters=[["status", "=", "Working"], ["deadline_due_at", "between", bounds]],
		fields=fields,
		limit_page_length=0,
		order_by="creation asc",
	)


def visible_rows(filters=None):
	import frappe

	from dinext_common.workflow_approval.permissions import (
		_batch_read_helper,
		prepare_source_permissions,
		task_read_candidates,
	)

	if not frappe.has_permission("Workflow Task", "read"):
		return []
	fields = [
		"name",
		"creation",
		"reference_doctype",
		"reference_name",
		"workflow",
		"workflow_state",
		"approver",
		"user",
		"doc",
		"wt_docname",
		"source_deleted_at",
		"status",
		"completed_at",
		"completion_source",
		"deadline_assignment_id",
		"deadline_due_at",
		"deadline_started_at",
		"deadline_timezone",
		"deadline_error",
		"source_title",
		"source_created_at",
	]
	candidates = _candidate_rows(filters or {}, fields)
	if not candidates:
		return []
	source_permissions = {}
	prepare_source_permissions(candidates, frappe.session.user, source_permissions)
	batch_read = _batch_read_helper()
	result = []
	for offset in range(0, len(candidates), 500):
		page = candidates[offset : offset + 500]
		with task_read_candidates(page, source_permissions):
			rows = frappe.get_list(
				"Workflow Task",
				filters={"name": ["in", [row.name for row in page]]},
				fields=fields,
				limit_page_length=0,
				order_by="creation asc",
			)
			if batch_read:
				allowed = batch_read("Workflow Task", [row.name for row in rows])
			else:
				allowed = {
					row.name
					for row in rows
					if frappe.get_doc(dict(row, doctype="Workflow Task")).has_permission("read")
				}
			result.extend(row for row in rows if row.name in allowed)
	# Verify the source generation in batches without loading every child table.
	by_type = defaultdict(set)
	for row in result:
		if row.source_created_at:
			by_type[row.reference_doctype].add(row.reference_name)
	identities = {}
	for doctype, source_names in by_type.items():
		names = list(source_names)
		for offset in range(0, len(names), 500):
			for source in frappe.get_all(
				doctype, filters={"name": ["in", names[offset : offset + 500]]}, fields=["name", "creation"]
			):
				identities[(doctype, source.name)] = source.creation
	return [
		dict(row)
		for row in result
		if not row.source_created_at
		or row.source_created_at == identities.get((row.reference_doctype, row.reference_name))
	]


def metrics(filters=None):
	from frappe.utils import add_days, get_system_timezone, now_datetime, nowdate

	filters = filters or {}
	return summarize(
		visible_rows(filters),
		from_date=filters.get("from_date") or add_days(nowdate(), -29),
		to_date=filters.get("to_date") or nowdate(),
		now=now_datetime(),
		site_timezone=get_system_timezone(),
	)


def _card(key, *, percent=False):
	import frappe

	if frappe.session.user == "Guest":
		raise frappe.PermissionError
	value = metrics()[key]
	return {
		"value": round(value, 1) if value is not None else frappe._("No observations"),
		"fieldtype": ("Percent" if percent else "Int") if value is not None else "Data",
		"route": ["query-report", "Approval Deadline Discipline"],
		"route_options": {},
	}


import frappe


@frappe.whitelist()
def overdue_card():
	return _card("open_overdue")


@frappe.whitelist()
def on_time_card():
	return _card("on_time_percent", percent=True)


@frappe.whitelist()
def late_card():
	return _card("completed_late")


@frappe.whitelist()
def errors_card():
	return _card("errors")
