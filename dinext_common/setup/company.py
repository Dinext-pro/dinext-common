# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from erpnext.setup.doctype.company.company import Company

from dinext_common.setup.chart_of_accounts import DINEXT_CHART_NAME, get_dinext_chart_forest


class DinextCompany(Company):
	def create_default_accounts(self):
		if self.chart_of_accounts != DINEXT_CHART_NAME:
			return super().create_default_accounts()

		from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts

		frappe.local.flags.ignore_root_company_validation = True
		create_charts(
			self.name,
			custom_chart=get_dinext_chart_forest(),
			from_coa_importer=True,
		)

		self.db_set(
			"default_receivable_account",
			frappe.db.get_value(
				"Account", {"company": self.name, "account_type": "Receivable", "is_group": 0}
			),
		)

		self.db_set(
			"default_payable_account",
			frappe.db.get_value(
				"Account", {"company": self.name, "account_type": "Payable", "is_group": 0}
			),
		)
