# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from dinext_common.setup.chart_of_accounts import (
	DINEXT_CHART_NAME,
	get_charts_for_country,
	get_coa,
	get_dinext_chart_forest,
)


class TestDinextChartOfAccounts(FrappeTestCase):
	def test_forest_contains_expected_roots(self):
		forest = get_dinext_chart_forest()
		expected_roots = {
			"Активы": "Asset",
			"Обязательства": "Liability",
			"Доход": "Income",
			"Расход": "Expense",
			"Капитал": "Equity",
		}
		for root, root_type in expected_roots.items():
			self.assertIn(root, forest)
			self.assertEqual(forest[root].get("root_type"), root_type)

	def test_get_charts_for_country_includes_dinext(self):
		charts = get_charts_for_country("Russian Federation", with_standard=True)
		self.assertIn(DINEXT_CHART_NAME, charts)
		self.assertIn("Standard", charts)

	def test_get_coa_preview_for_dinext_roots(self):
		accounts = get_coa("Account", "All Accounts", chart=DINEXT_CHART_NAME)
		values = {row["value"] for row in accounts}
		self.assertTrue({"Активы", "Обязательства", "Доход", "Расход", "Капитал"}.issubset(values))

	def test_company_with_dinext_chart_creates_accounts(self):
		company_name = f"Dinext COA {random_string(5)}"
		abbr = random_string(4).upper()
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": abbr,
				"default_currency": "RUB",
				"country": "Russian Federation",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": DINEXT_CHART_NAME,
			}
		)
		try:
			company.insert(ignore_permissions=True)

			from frappe.model.base_document import get_controller

			self.assertEqual(get_controller("Company").__name__, "DinextCompany")

			account_names = frappe.get_all(
				"Account",
				filters={"company": company_name},
				pluck="account_name",
			)
			self.assertGreaterEqual(len(account_names), 40)
			for root in ("Активы", "Обязательства", "Доход", "Расход", "Капитал"):
				self.assertIn(root, account_names)

			self.assertTrue(
				frappe.db.exists(
					"Account",
					{"company": company_name, "account_type": "Receivable", "is_group": 0},
				)
			)
			self.assertTrue(
				frappe.db.exists(
					"Account",
					{"company": company_name, "account_type": "Payable", "is_group": 0},
				)
			)
		finally:
			_cleanup_company(company_name)

	def test_company_with_standard_chart_still_works(self):
		company_name = f"Std COA {random_string(5)}"
		abbr = random_string(4).upper()
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": abbr,
				"default_currency": "RUB",
				"country": "Russian Federation",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "Standard",
			}
		)
		try:
			company.insert(ignore_permissions=True)
			self.assertTrue(
				frappe.db.exists(
					"Account",
					{"company": company_name, "account_type": "Receivable", "is_group": 0},
				)
			)
			# Standard English roots, not Dinext Russian roots
			self.assertFalse(
				frappe.db.exists("Account", {"company": company_name, "account_name": "Активы"})
			)
		finally:
			_cleanup_company(company_name)


def _cleanup_company(company_name: str) -> None:
	if not frappe.db.exists("Company", company_name):
		return

	for mop in frappe.get_all("Mode of Payment Account", filters={"company": company_name}, pluck="name"):
		frappe.delete_doc("Mode of Payment Account", mop, force=1, ignore_permissions=True)

	frappe.delete_doc("Company", company_name, force=1, ignore_permissions=True)
