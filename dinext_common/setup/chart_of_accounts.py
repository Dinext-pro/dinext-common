# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

DINEXT_CHART_NAME = "Dinext"
COA_TEMPLATE_RELATIVE_PATH = ("setup", "data", "coa_importer_template.xlsx")


def get_coa_template_path() -> str:
	return frappe.get_app_path("dinext_common", *COA_TEMPLATE_RELATIVE_PATH)


def _load_template_rows() -> list:
	path = get_coa_template_path()
	with open(path, "rb") as template_file:
		rows = read_xlsx_file_from_attached_file(fcontent=template_file.read())

	if not rows:
		frappe.throw(_("Dinext Chart of Accounts template is empty"))

	# Drop header; normalize roots like Chart of Accounts Importer Excel path
	data = []
	for row in rows[1:]:
		row = list(row)
		if len(row) < 8:
			row.extend([None] * (8 - len(row)))
		if not row[1]:
			row[1] = row[0]
			row[3] = row[2]
		data.append(row)

	return data


def get_dinext_chart_forest() -> dict:
	from erpnext.accounts.doctype.chart_of_accounts_importer.chart_of_accounts_importer import (
		build_forest,
	)

	return build_forest(_load_template_rows())


@frappe.whitelist()
def get_charts_for_country(country, with_standard=False):
	from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import (
		get_charts_for_country as erpnext_get_charts_for_country,
	)

	charts = list(erpnext_get_charts_for_country(country, with_standard=with_standard) or [])
	if DINEXT_CHART_NAME not in charts:
		charts.append(DINEXT_CHART_NAME)
	return charts


@frappe.whitelist()
def get_coa(doctype, parent, is_root=None, chart=None):
	from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import (
		build_tree_from_json,
	)

	chart = chart if chart else frappe.flags.chart
	frappe.flags.chart = chart

	if chart == DINEXT_CHART_NAME:
		parent = None if parent == _("All Accounts") else parent
		forest = get_dinext_chart_forest()
		accounts = build_tree_from_json("", chart_data=forest, from_coa_importer=True) or []
		return [d for d in accounts if d["parent_account"] == parent]

	from erpnext.accounts.utils import get_coa as erpnext_get_coa

	return erpnext_get_coa(doctype, parent, is_root=is_root, chart=chart)
