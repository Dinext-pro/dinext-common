"""Page flat Desk Workflow Task lists after checking access to each candidate page."""

import re

import frappe
from frappe.desk import reportview
from frappe.utils import cint

from dinext_common.workflow_approval.permissions import (
	prepare_source_permissions,
	task_principal_filters,
	task_read_candidates,
)

DOCTYPE = "Workflow Task"
CANDIDATE_PAGE_SIZE = 250
ACCESS_FIELDS = (
	"name", "approver", "user", "workflow", "reference_doctype", "reference_name",
	"doc", "wt_docname", "source_deleted_at",
)
COLUMN = r"(?:`tabWorkflow Task`\.)?`?([a-zA-Z_]\w*)`?"
ORDER_TERM = re.compile(COLUMN + r"\s+(asc|desc)", re.IGNORECASE)
PAGE_ARGS = {
	"doctype", "fields", "filters", "order_by", "start", "page_length", "strict",
	"save_user_settings", "save_user_settings_fields", "with_comment_count",
}


@frappe.whitelist()
@frappe.read_only()
def get():
	if frappe.form_dict.get("doctype") != DOCTYPE:
		return reportview.get()

	args = reportview.get_form_params()
	order_by = _page_order(args)
	if not order_by:
		return reportview.get()

	rows, source_permissions = _authorized_page(args, order_by)
	name_filter = _name_filter(rows)
	query = {
		**args, "filters": [*(args.filters or []), name_filter], "order_by": order_by,
		"start": 0, "page_length": len(rows) or 1,
	}
	with task_read_candidates(rows, source_permissions):
		return reportview.compress(reportview.execute(**query), args=args)


def _page_order(args):
	# Leave grouped, linked, and custom report queries under Frappe's full list policy.
	if any(key not in PAGE_ARGS and value is not None for key, value in args.items()):
		return None
	if not 0 < cint(args.page_length) <= 500 or cint(args.start) < 0:
		return None
	if any(not re.fullmatch(COLUMN, field) for field in args.fields or []):
		return None
	if args.filters and (
		not isinstance(args.filters, list)
		or any(
			len(entry) != 4 or entry[0] != DOCTYPE or not re.fullmatch(COLUMN, entry[1])
			for entry in args.filters
		)
	):
		return None
	if not isinstance(args.order_by, str):
		return None
	terms = [ORDER_TERM.fullmatch(term.strip()) for term in args.order_by.split(",")]
	if not all(terms):
		return None
	order = ", ".join(f"`tab{DOCTYPE}`.`{term[1]}` {term[2]}" for term in terms)
	return order if any(term[1].lower() == "name" for term in terms) else f"{order}, `tab{DOCTYPE}`.`name` asc"


def _name_filter(rows):
	return [DOCTYPE, "name", "in", [row.name for row in rows] or [""]]


def _authorized_page(args, order_by):
	start = cint(args.start)
	stop = start + cint(args.page_length)
	offset = 0
	user = frappe.session.user
	principal_filters = task_principal_filters(user)
	visible = []
	source_permissions = {}
	while len(visible) < stop:
		candidates = frappe.get_all(
			DOCTYPE, fields=ACCESS_FIELDS, filters=args.filters, or_filters=principal_filters,
			order_by=order_by, limit_start=offset, limit_page_length=CANDIDATE_PAGE_SIZE,
		)
		if not candidates:
			break

		prepare_source_permissions(candidates, user, source_permissions)
		with task_read_candidates(candidates, source_permissions):
			names = reportview.execute(
				DOCTYPE, fields=["name"], filters=[_name_filter(candidates)], order_by=order_by,
			)
		by_name = {row.name: row for row in candidates}
		visible.extend(by_name[row.name] for row in names)
		if len(candidates) < CANDIDATE_PAGE_SIZE:
			break
		offset += len(candidates)

	return visible[start:stop], source_permissions
