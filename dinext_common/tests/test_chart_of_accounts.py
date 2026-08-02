# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from dinext_common.setup.chart_of_accounts import (
	DINEXT_CHART_NAME,
	_load_template_rows,
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

	def test_template_has_corrected_account_types_and_no_typos(self):
		rows = _load_template_rows()
		by_name = {row[0]: row for row in rows}

		self.assertIn("Внеоборотные активы", by_name)
		self.assertNotIn("Внеоборотные активны", by_name)
		self.assertIn("Нераспределенная прибыль", by_name)

		for name in by_name:
			self.assertEqual(name, name.strip(), msg=f"trailing/leading whitespace in {name!r}")

		expected_types = {
			"НМА": "Fixed Asset",
			"ОС": "Fixed Asset",
			"Авансы выданные": "Current Asset",
			"Авансы полученные": "Current Liability",
			"Запас материалов": "Stock",
			"Касса": "Cash",
			"Расчетные счета": "Bank",
			"Округление": "Round Off",
			"Себестоимость продаж": "Cost of Goods Sold",
			"Капитальные вложения": "Capital Work in Progress",
			"Работы / услуги (выручка)": "Income Account",
			"Дебиторская задолженность": "Receivable",
			"Кредиторская задолженность": "Payable",
		}
		for account_name, account_type in expected_types.items():
			self.assertEqual(by_name[account_name][5], account_type)

		self.assertIsNone(by_name["Текущие обязательства"][5])
		self.assertIsNone(by_name["Налоги и сборы"][5])

	def test_empty_template_message_has_russian_translation(self):
		from frappe.translate import get_full_dict

		messages = get_full_dict("ru")
		self.assertEqual(
			messages.get("Dinext Chart of Accounts template is empty"),
			"Шаблон плана счетов Dinext пуст",
		)

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
			self.assertGreaterEqual(len(account_names), 50)
			for root in ("Активы", "Обязательства", "Доход", "Расход", "Капитал"):
				self.assertIn(root, account_names)
			self.assertIn("Нераспределенная прибыль", account_names)
			self.assertIn("Внеоборотные активы", account_names)

			for account_type in (
				"Cash",
				"Bank",
				"Receivable",
				"Payable",
				"Stock",
				"Round Off",
				"Fixed Asset",
			):
				self.assertTrue(
					frappe.db.exists(
						"Account",
						{"company": company_name, "account_type": account_type, "is_group": 0},
					),
					msg=f"missing leaf account_type={account_type}",
				)

			company.reload()
			self.assertTrue(company.default_cash_account)
			self.assertTrue(company.default_bank_account)
			self.assertTrue(company.default_receivable_account)
			self.assertTrue(company.default_payable_account)
			self.assertTrue(company.round_off_account)
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
