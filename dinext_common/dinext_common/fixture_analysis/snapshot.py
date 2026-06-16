from __future__ import annotations

import frappe

from .constants import INVALID_DOCTYPE_WARNING


def load_live_docs(doctype: str, *, filters: list | None = None) -> tuple[list[dict], list[str], bool]:
	if not frappe.db.exists("DocType", doctype):
		return [], [INVALID_DOCTYPE_WARNING], False

	meta = frappe.get_meta(doctype)
	if meta.issingle:
		doc = frappe.get_doc(doctype).as_dict()
		return [doc], [], True

	names = []
	start = 0
	page_length = 500
	while True:
		batch = frappe.get_all(
			doctype,
			filters=filters or None,
			pluck="name",
			start=start,
			limit_page_length=page_length,
			order_by="name asc",
		)
		if not batch:
			break
		names.extend(batch)
		if len(batch) < page_length:
			break
		start += page_length

	return [frappe.get_doc(doctype, name).as_dict() for name in names], [], False
