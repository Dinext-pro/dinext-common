"""Workflow scenario settings, validation and import preservation."""

from __future__ import annotations

import ast
import re
import unicodedata
from typing import Any

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CONDITION_FIELD = "custom_activation_condition"
ORDER_FIELD = "custom_selection_order"


def get_custom_fields() -> dict[str, list[dict[str, Any]]]:
	"""Extend the platform-owned Workflow without customising owned DocTypes."""
	return {
		"Workflow": [
			{
				"fieldname": "custom_workflow_scenario_section",
				"fieldtype": "Section Break",
				"insert_after": "workflow_state_field",
				"label": "Workflow Scenario",
			},
			{
				"fieldname": ORDER_FIELD,
				"fieldtype": "Int",
				"insert_after": "custom_workflow_scenario_section",
				"label": "Selection Order",
				"description": "The matching Workflow with the lowest number is selected. Numbers must be unique within the document type, including inactive Workflows.",
				"reqd": 1,
				"non_negative": 1,
				"in_list_view": 1,
			},
			{
				"fieldname": CONDITION_FIELD,
				"fieldtype": "Code",
				"options": "Python",
				"insert_after": ORDER_FIELD,
				"label": "Activation Condition",
				"description": "Safe Python expression using doc. Leave blank to always match. A running process keeps its Workflow until completion.",
			},
		],
	}


def ensure_fields() -> None:
	fields = get_custom_fields()
	for row in fields["Workflow"]:
		row["module"] = "Dinext Common"
	create_custom_fields(fields, ignore_validate=True, update=True)


def normalized_order(value: object) -> int:
	"""Do not silently truncate a fractional number or accept a boolean."""
	if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
		raise ValueError(_("Workflow selection order must be a positive integer"))
	return int(str(value))


def validate_condition(condition: str | None) -> None:
	"""Compile with the same restricted policy as evaluation; never run it here."""
	condition = unicodedata.normalize("NFKC", str(condition or "")).strip()
	if not condition:
		return
	from frappe.utils.safe_exec import FrappeTransformer
	from RestrictedPython import compile_restricted

	try:
		tree = ast.parse(condition, mode="eval")
		if any(isinstance(node, (ast.NamedExpr, ast.Lambda)) for node in ast.walk(tree)):
			raise SyntaxError("Assignment expressions and lambda expressions are not allowed")
		compile_restricted(
			condition, filename="<Workflow activation condition>", mode="eval", policy=FrappeTransformer
		)
	except (SyntaxError, TypeError, ValueError) as exc:
		raise ValueError(_("Invalid Workflow activation condition: {0}").format(str(exc))) from exc


def next_selection_order(doctype: str) -> int:
	rows = frappe.get_all("Workflow", filters={"document_type": doctype}, fields=[ORDER_FIELD])
	return max((int(row.get(ORDER_FIELD) or 0) for row in rows), default=0) + 1


@frappe.whitelist()
def get_next_selection_order(doctype: str) -> int:
	frappe.has_permission("Workflow", ptype="create", throw=True)
	return next_selection_order(doctype)


def validate_settings(doc: object) -> None:
	validate_condition(doc.get(CONDITION_FIELD))
	raw_order = doc.get(ORDER_FIELD)
	if raw_order is None or raw_order == "":
		raw_order = next_selection_order(doc.get("document_type"))
	order = normalized_order(raw_order)
	duplicate = frappe.db.get_value(
		"Workflow",
		{
			"document_type": doc.get("document_type"),
			ORDER_FIELD: order,
			"name": ("!=", doc.get("name") or ""),
		},
		"name",
	)
	if duplicate:
		raise ValueError(_("Workflow selection order {0} is already used by {1}").format(order, duplicate))
	doc.set(ORDER_FIELD, order)


def validate_selection_settings(doc: object, method: str | None = None) -> None:
	try:
		validate_settings(doc)
	except ValueError as exc:
		frappe.throw(str(exc))


def preserve_fixture_settings(doc: object, method: str | None = None) -> None:
	"""Old producer fixtures must not erase the site's chosen routing policy."""
	if not frappe.flags.in_fixtures or not frappe.db.exists("Workflow", doc.get("name")):
		return
	existing = frappe.get_doc("Workflow", doc.get("name"))
	if existing.get(ORDER_FIELD):
		doc.set(ORDER_FIELD, existing.get(ORDER_FIELD))
	if existing.get(CONDITION_FIELD) is not None:
		doc.set(CONDITION_FIELD, existing.get(CONDITION_FIELD))


def ensure_constraints() -> None:
	"""The database arbitrates racing saves after application validation."""
	frappe.db.add_unique(
		"Workflow", ["document_type", ORDER_FIELD], constraint_name="workflow_scenario_selection_order"
	)
