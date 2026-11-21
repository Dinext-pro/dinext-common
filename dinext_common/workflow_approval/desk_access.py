"""Permission-aware Desk search for Common-owned Workflow records and cards."""
import frappe
from frappe.config import get_modules_from_all_apps_for_user
from frappe.desk import search
from frappe.desk.doctype.number_card.number_card import get_cards_for_user as get_standard_cards
from frappe.query_builder import Criterion
from frappe.utils import cint

from dinext_common.workflow_approval.permissions import (
	MONITORING_APPROVAL_NUMBER_CARDS,
	WORKFLOW_READ_DOCTYPES,
	may_read_monitoring_cards,
	require_no_workflow_shares,
)

WORKFLOW_TRANSITION_CHILD = "Available Workflow Transitions"
STANDARD_CARD_QUERY = "frappe.desk.doctype.number_card.number_card.get_cards_for_user"
WORKFLOW_CARD_QUERY = "dinext_common.workflow_approval.desk_access.get_cards_for_user"


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_cards_for_user(doctype, txt, searchfield, start, page_len, filters):
	if doctype != "Number Card":
		frappe.throw(frappe._("Expected a Number Card lookup."), frappe.ValidationError)
	ordinary = [
		row for row in get_standard_cards(doctype, txt, searchfield, start, page_len, filters)
		if row[0] not in MONITORING_APPROVAL_NUMBER_CARDS
	]
	user = frappe.session.user
	if not may_read_monitoring_cards(user):
		return ordinary

	require_no_workflow_shares(doctype, user)
	card = frappe.qb.DocType(doctype)
	allowed_modules = [
		module["module_name"] for module in get_modules_from_all_apps_for_user()
	]
	query = (
		frappe.qb.get_query(doctype, filters=frappe.parse_json(filters), validate_filters=True)
		.select(card.name, card.label, card.document_type)
		.where(card.name.isin(sorted(MONITORING_APPROVAL_NUMBER_CARDS)))
		.where(card.module.isin(allowed_modules) | card.module.isnull() | (card.module == ""))
	)
	if txt:
		search_fields = frappe.get_meta(doctype).get_search_fields()
		query = query.where(Criterion.any([card[field].like(f"%{txt}%") for field in search_fields]))
	return ordinary + [
		row for row in query.run()
		if frappe.has_permission(doctype, "read", doc=row[0], throw=False)
	]


def _search_workflow_transitions(txt, start, page_length, filters, as_dict):
	filters = frappe.parse_json(filters) or []
	if isinstance(filters, dict):
		filters = [search.make_filter_tuple(WORKFLOW_TRANSITION_CHILD, key, value) for key, value in filters.items()]
	return frappe.get_list(
		WORKFLOW_TRANSITION_CHILD,
		parent_doctype="Workflow Task",
		filters=[
			*filters, ["parenttype", "=", "Workflow Task"],
			["parentfield", "=", "available_workflow_transitions"],
		],
		or_filters=[["name", "like", f"%{txt}%"], ["action", "like", f"%{txt}%"]] if txt else [],
		fields=["name", "action", "next_state"],
		order_by="name asc",
		limit_start=max(cint(start), 0),
		limit_page_length=cint(page_length) if cint(page_length) > 0 else search.PAGE_LENGTH_FOR_LINK_VALIDATION,
		as_list=not as_dict,
	)


@frappe.whitelist()
def search_widget(
	doctype, txt, query=None, searchfield=None, start=0, page_length=10, filters=None,
	filter_fields=None, as_dict=False, reference_doctype=None, ignore_user_permissions=False,
):
	if doctype == WORKFLOW_TRANSITION_CHILD:
		return _search_workflow_transitions(txt, start, page_length, filters, as_dict)
	if doctype in WORKFLOW_READ_DOCTYPES:
		if doctype == "Number Card" and query in {STANDARD_CARD_QUERY, WORKFLOW_CARD_QUERY}:
			rows = get_cards_for_user(doctype, txt, searchfield, start, page_length, filters)
			if as_dict:
				return [dict(zip(("name", "label", "document_type"), row)) for row in rows]
			return rows
		query = None
		ignore_user_permissions = False

	return search.search_widget(
		doctype, txt, query=query, searchfield=searchfield, start=start, page_length=page_length,
		filters=filters, filter_fields=filter_fields, as_dict=as_dict,
		reference_doctype=reference_doctype, ignore_user_permissions=ignore_user_permissions,
	)


@frappe.whitelist()
def search_link(
	doctype, txt, query=None, filters=None, page_length=10, searchfield=None,
	reference_doctype=None, ignore_user_permissions=False,
):
	if doctype not in WORKFLOW_READ_DOCTYPES and doctype != WORKFLOW_TRANSITION_CHILD:
		return search.search_link(
			doctype, txt, query=query, filters=filters, page_length=page_length,
			searchfield=searchfield, reference_doctype=reference_doctype,
			ignore_user_permissions=ignore_user_permissions,
		)
	rows = search_widget(
		doctype, txt.strip(), query=query, filters=filters, page_length=page_length,
		searchfield=searchfield, reference_doctype=reference_doctype,
		ignore_user_permissions=ignore_user_permissions,
	)
	return search.build_for_autosuggest(rows, doctype=doctype)
