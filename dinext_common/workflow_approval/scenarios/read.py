"""Load sets of persisted documents without replacing custom Frappe loaders."""

from __future__ import annotations

from collections.abc import Sequence

import frappe
from frappe.model.base_document import DOCTYPES_FOR_DOCTYPE, get_controller
from frappe.model.document import Document
from frappe.utils.nestedset import NestedSet


def load_documents(doctype: str, names: Sequence[str]) -> dict[str, Document]:
	"""Hydrate ordinary documents in batches and keep native loaders for special cases."""
	if not names:
		return {}

	meta = frappe.get_meta(doctype)
	if not (meta.is_virtual or meta.issingle or doctype in DOCTYPES_FOR_DOCTYPE):
		controller = get_controller(doctype)
		if (
			controller.__init__ is Document.__init__
			and controller.load_from_db is Document.load_from_db
			and getattr(controller, "__setup__", None) in (None, NestedSet.__setup__)
		):
			return _load_standard_documents(controller, doctype, names, meta.get_table_fields())

	documents = {}
	for name in names:
		try:
			documents[name] = frappe.get_doc(doctype, name)
		except (frappe.DoesNotExistError, frappe.PermissionError):
			continue
	return documents


def _load_standard_documents(
	controller: type[Document], doctype: str, names: Sequence[str], table_fields
) -> dict[str, Document]:
	rows = frappe.db.get_values(doctype, {"name": ("in", list(names))}, "*", as_dict=True)
	parents = {row.name: row for row in rows}
	if not parents:
		return {}

	for field in table_fields:
		for row in rows:
			row[field.fieldname] = []
		if frappe.get_meta(field.options).is_virtual:
			continue
		for child in frappe.db.get_values(
			field.options,
			{"parent": ("in", list(parents)), "parenttype": doctype, "parentfield": field.fieldname},
			"*",
			as_dict=True,
			order_by="idx asc",
		):
			parents[child.parent][field.fieldname].append(child)

	return {name: controller(dict(row, doctype=doctype)) for name, row in parents.items()}
