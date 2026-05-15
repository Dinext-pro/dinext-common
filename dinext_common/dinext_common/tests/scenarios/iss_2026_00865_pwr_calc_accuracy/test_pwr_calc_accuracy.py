# Copyright (c) 2026, Dinext
"""Точность расчётов PWR: V2 (сетка команды) vs V3 (дерево проекта), выходные."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_common.project_workload_api import (
	pwr_run_project_workload_tree,
	pwr_run_team_workload_grid,
)
from dinext_common.dinext_common.project_workload.single_project_workload_tree import (
	run_get_project_workload_data,
)
from dinext_common.dinext_common.project_workload.team_workload_grid import (
	run_get_projects_workload_data_v2,
)

from .data_setup import (
	ANCHOR_MONDAY,
	BUSINESS_USER,
	WEEK_END,
	WEEK_START,
	prepare_case_hours_with_weekend_holiday_list,
	prepare_case_hours_without_project_holiday_list,
	prepare_case_percent_fund_without_holiday_list,
	prepare_case_percent_task_effort,
	prepare_case_two_users_hours_for_pagination,
	prepare_case_user_group_excludes_second_user,
	reset_owned_data,
	SECOND_USER_EMAIL,
	try_create_application_for_leave_tc09,
)


def _parse_float_cell(value) -> float:
	if value is None:
		return 0.0
	if isinstance(value, (int, float)):
		return float(value)
	s = str(value).strip().replace(",", ".")
	try:
		return float(s)
	except ValueError:
		return 0.0


def _find_team_v2_user_row(tree_data: list, email: str):
	for row in tree_data:
		if row.get("_isUser") and (row.get("_email") == email or row.get("participant") == email):
			return row
	return None


def _find_v3_user_row(tree_data: list, email: str):
	for row in tree_data:
		if row.get("isUser") and row.get("email") == email:
			return row
	return None


def _sum_weekend_daily_hours(row: dict | None, periods: list) -> float:
	if not row:
		return 0.0
	total = 0.0
	for p in periods:
		if p.get("weekday") is None:
			continue
		if int(p["weekday"]) >= 5:
			total += _parse_float_cell(row.get(p["key"]))
	return total


def _max_daily_cell_diff_v2_v3(row_v2: dict, row_v3: dict, periods: list, date_from: str, date_to: str) -> float:
	d0 = frappe.utils.getdate(date_from)
	d1 = frappe.utils.getdate(date_to)
	max_diff = 0.0
	for p in periods:
		if p.get("date") is None:
			continue
		d = frappe.utils.getdate(p["date"])
		if d < d0 or d > d1:
			continue
		key = p["key"]
		a = _parse_float_cell(row_v2.get(key))
		b = _parse_float_cell(row_v3.get(key))
		diff = abs(a - b)
		if diff > max_diff:
			max_diff = diff
	return max_diff


def _call_pwr_team_whitelist(fd: dict):
	"""Точка входа Server Script: `frappe.call(pwr_run_team_workload_grid)`."""
	prev = getattr(frappe.local, "form_dict", None)
	frappe.local.form_dict = frappe._dict(fd)
	try:
		return pwr_run_team_workload_grid()
	finally:
		frappe.local.form_dict = prev


def _call_pwr_project_whitelist(fd: dict):
	"""Точка входа Server Script: `frappe.call(pwr_run_project_workload_tree)`."""
	prev = getattr(frappe.local, "form_dict", None)
	frappe.local.form_dict = frappe._dict(fd)
	try:
		return pwr_run_project_workload_tree()
	finally:
		frappe.local.form_dict = prev


def _sum_team_v2_user_rows_total(tree_data: list) -> float:
	total = 0.0
	for row in tree_data or []:
		if row.get("_isUser"):
			total += _parse_float_cell(row.get("workload_total"))
	return total


def _period_key_for_daily_date(periods: list, ymd: str) -> str | None:
	for p in periods or []:
		d = p.get("date")
		if d is None:
			continue
		if str(d) == ymd:
			return p.get("key")
	return None


def _sum_team_v2_daily_in_week(row: dict | None, periods: list, week_start: str, week_end: str) -> float:
	"""Сумма daily-ячеек V2 на интервале [week_start, week_end] (календарные даты)."""
	if not row:
		return 0.0
	d0 = frappe.utils.getdate(week_start)
	d1 = frappe.utils.getdate(week_end)
	total = 0.0
	for p in periods or []:
		if p.get("date") is None:
			continue
		d = frappe.utils.getdate(p["date"])
		if d < d0 or d > d1:
			continue
		key = p.get("key")
		if key:
			total += _parse_float_cell(row.get(key))
	return total


class TestISS202600865PwrCalcAccuracy(FrappeTestCase):
	def tearDown(self):
		reset_owned_data()
		super().tearDown()

	def test_tc01_team_v2_and_project_v3_total_hours_parity_without_holiday_list(self):
		"""Без holiday_list на проекте: суммарные часы пользователя в V2 и V3 совпадают (±0.2 ч)."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}

		fd_v3 = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}

		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
			out_v3 = run_get_project_workload_data(fd_v3)

		self.assertNotIn("error", out_v2)
		row_v2 = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		row_v3 = _find_v3_user_row(out_v3.get("tree_data") or [], BUSINESS_USER)
		self.assertIsNotNone(row_v2, "V2: нет строки пользователя")
		self.assertIsNotNone(row_v3, "V3: нет строки пользователя")

		t2 = _parse_float_cell(row_v2.get("workload_total"))
		t3 = _parse_float_cell(row_v3.get("workload_total"))
		self.assertAlmostEqual(t2, 40.0, delta=0.25, msg=f"V2 total={t2}")
		self.assertAlmostEqual(t3, 40.0, delta=0.25, msg=f"V3 total={t3}")
		self.assertAlmostEqual(t2, t3, delta=0.25, msg="V2 vs V3 parity")

	def test_tc02_weekend_daily_hours_zero_when_holiday_list_marks_weekly_off(self):
		"""С Holiday List (сб/вс weekly_off): на колонках выходных не должно оставаться доли часов."""
		ctx = prepare_case_hours_with_weekend_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		fd_v3 = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
			out_v3 = run_get_project_workload_data(fd_v3)

		periods_v2 = out_v2.get("periods") or []
		periods_v3 = out_v3.get("periods") or []
		row_v2 = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		row_v3 = _find_v3_user_row(out_v3.get("tree_data") or [], BUSINESS_USER)

		wk_v2 = _sum_weekend_daily_hours(row_v2, periods_v2)
		wk_v3 = _sum_weekend_daily_hours(row_v3, periods_v3)

		self.assertLess(
			wk_v3,
			0.15,
			msg=f"V3: на выходных суммарно {wk_v3} ч (ожидалось ~0). Дерево проекта должно уважать weekly_off.",
		)
		self.assertLess(
			wk_v2,
			0.15,
			msg=(
				f"V2: на выходных суммарно {wk_v2} ч (ожидалось ~0). "
				"Регрессия ISS-2026-00865: сетка команды не должна размазывать часы на сб/вс при weekly_off в Holiday List."
			),
		)

	def test_tc02b_weekend_hours_positive_without_holiday_list(self):
		"""Без holiday_list: на выходных ожидается ненулевая доля (документация поведения)."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		fd_v3 = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
			out_v3 = run_get_project_workload_data(fd_v3)
		row_v2 = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		row_v3 = _find_v3_user_row(out_v3.get("tree_data") or [], BUSINESS_USER)
		wk_v2 = _sum_weekend_daily_hours(row_v2, out_v2.get("periods") or [])
		wk_v3 = _sum_weekend_daily_hours(row_v3, out_v3.get("periods") or [])
		self.assertGreater(wk_v2, 0.5, msg="V2: без HL выходные должны получать часть часов")
		self.assertGreater(wk_v3, 0.5, msg="V3: без HL выходные должны получать часть часов")

	def test_tc03_daily_cell_parity_v2_v3_in_assignment_window(self):
		"""По дням внутри интервала назначения: максимальное расхождение ячеек V2 vs V3 мало."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		fd_v3 = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
			out_v3 = run_get_project_workload_data(fd_v3)
		row_v2 = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		row_v3 = _find_v3_user_row(out_v3.get("tree_data") or [], BUSINESS_USER)
		periods_v3 = out_v3.get("periods") or []
		md = _max_daily_cell_diff_v2_v3(row_v2, row_v3, periods_v3, WEEK_START, WEEK_END)
		self.assertLess(md, 0.15, msg=f"max daily cell diff V2 vs V3 = {md}")

	def test_tc04_percent_fund_v2_v3_parity_without_holiday_list(self):
		"""«В % от фонда»: 50% за неделю без HL → 7×8×0.5 = 28 ч; V2 и V3 согласованы."""
		ctx = prepare_case_percent_fund_without_holiday_list(50.0)
		project_name = ctx["project"]
		expected = 7.0 * 8.0 * 0.5
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		fd_v3 = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
			out_v3 = run_get_project_workload_data(fd_v3)
		row_v2 = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		row_v3 = _find_v3_user_row(out_v3.get("tree_data") or [], BUSINESS_USER)
		t2 = _parse_float_cell(row_v2.get("workload_total"))
		t3 = _parse_float_cell(row_v3.get("workload_total"))
		# Допуск ±0.75: фактический фонд часов по шаблону Worker может отличаться от 7×8 (например один день 7 ч).
		self.assertAlmostEqual(t2, expected, delta=0.75, msg=f"V2 total={t2}, expected~{expected}")
		self.assertAlmostEqual(t3, expected, delta=0.75, msg=f"V3 total={t3}, expected~{expected}")
		self.assertAlmostEqual(t2, t3, delta=0.25, msg="V2 vs V3 parity % fund")

	def test_tc05_user_totals_matches_full_for_same_user(self):
		"""mode=user_totals (первая страница) даёт тот же workload_total пользователя, что mode=full."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		base = {
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_full = run_get_projects_workload_data_v2({**base, "mode": "full"})
			out_tot = run_get_projects_workload_data_v2(
				{**base, "mode": "user_totals", "limit": 20, "offset": 0}
			)
		rf = _find_team_v2_user_row(out_full.get("tree_data") or [], BUSINESS_USER)
		rt = _find_team_v2_user_row(out_tot.get("tree_data") or [], BUSINESS_USER)
		self.assertIsNotNone(rf)
		self.assertIsNotNone(rt)
		tf = _parse_float_cell(rf.get("workload_total"))
		tt = _parse_float_cell(rt.get("workload_total"))
		self.assertAlmostEqual(tf, tt, delta=0.2, msg=f"full={tf} user_totals={tt}")

	def test_tc06_weekly_view_user_total_matches_assignment(self):
		"""Недельный вид: сумма по колонкам недель для пользователя ≈ 40 ч (одна неделя назначения)."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "weekly",
			"period_range": "quarter",
			"project": project_name,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
		row = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		self.assertIsNotNone(row)
		total = _parse_float_cell(row.get("workload_total"))
		self.assertAlmostEqual(total, 40.0, delta=0.35, msg=f"weekly workload_total={total}")

	def test_tc07_user_projects_mode_returns_project_rows(self):
		"""mode=user_projects + detail_user возвращает строки проектов для одного пользователя."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "user_projects",
			"detail_user": BUSINESS_USER,
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
		rows = out_v2.get("tree_data") or []
		# В user_projects строк пользователя нет (return_user_rows=False), только проекты.
		proj_rows = [r for r in rows if r.get("_isProject")]
		self.assertTrue(proj_rows, msg="Ожидались строки проектов (_isProject)")
		self.assertGreater(int(out_v2.get("assignments_count") or 0), 0)
		tot = _parse_float_cell(proj_rows[0].get("workload_total"))
		self.assertGreater(tot, 1.0, msg="Строка проекта должна нести ненулевую сумму")

	def test_tc08_pwr_run_team_workload_grid_matches_direct_run(self):
		"""Whitelist `pwr_run_team_workload_grid` совпадает с прямым `run_get_projects_workload_data_v2`."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			direct = run_get_projects_workload_data_v2(fd)
			via_whitelist = _call_pwr_team_whitelist(fd)
		r1 = _find_team_v2_user_row(direct.get("tree_data") or [], BUSINESS_USER)
		r2 = _find_team_v2_user_row(via_whitelist.get("tree_data") or [], BUSINESS_USER)
		self.assertAlmostEqual(
			_parse_float_cell(r1.get("workload_total")),
			_parse_float_cell(r2.get("workload_total")),
			delta=0.01,
		)

	def test_tc09_full_day_leave_redistributes_daily_hours_v2_v3(self):
		"""Согласованный полный день отпуска: на этот день почти нет часов; сумма по неделе ≈ 40; V2≈V3."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		if not try_create_application_for_leave_tc09("2026-05-06"):
			self.skipTest("Нет Worker у Administrator, Type Of Leave или DocType Application For Leave")
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		fd_v3 = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
			out_v3 = run_get_project_workload_data(fd_v3)
		pkey = _period_key_for_daily_date(out_v2.get("periods") or [], "2026-05-06")
		self.assertTrue(pkey, msg="Нет daily-периода на 2026-05-06")
		row_v2 = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		row_v3 = _find_v3_user_row(out_v3.get("tree_data") or [], BUSINESS_USER)
		self.assertLess(_parse_float_cell(row_v2.get(pkey)), 0.35, msg="V2: в день отпуска не должно оставаться полной доли")
		self.assertLess(_parse_float_cell(row_v3.get(pkey)), 0.35, msg="V3: в день отпуска не должно оставаться полной доли")
		self.assertAlmostEqual(
			_parse_float_cell(row_v2.get("workload_total")),
			_parse_float_cell(row_v3.get("workload_total")),
			delta=0.3,
		)
		self.assertAlmostEqual(_parse_float_cell(row_v2.get("workload_total")), 40.0, delta=0.35)

	def test_tc10_v2_response_contract_golden(self):
		"""TC-10: зафиксированный контракт ответа Python V2 (JSON в fixtures) на фикстуре TC-01."""
		fixture_path = Path(__file__).resolve().parent / "fixtures" / "tc10_team_v2_golden.json"
		with open(fixture_path, encoding="utf-8") as f:
			golden = json.load(f)
		golden.pop("_comment", None)

		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out = run_get_projects_workload_data_v2(fd_v2)

		self.assertNotIn("error", out)
		self.assertEqual(int(out.get("users_count") or 0), golden["counts"]["users_count"])
		self.assertEqual(int(out.get("projects_count") or 0), golden["counts"]["projects_count"])
		self.assertEqual(int(out.get("assignments_count") or 0), golden["counts"]["assignments_count"])
		row = _find_team_v2_user_row(out.get("tree_data") or [], golden["user_email"])
		self.assertIsNotNone(row, "V2: нет строки пользователя из эталона")
		tot = _parse_float_cell(row.get("workload_total"))
		wsum = _sum_team_v2_daily_in_week(row, out.get("periods") or [], golden["week_start"], golden["week_end"])
		self.assertAlmostEqual(
			tot,
			float(golden["workload_total"]),
			delta=float(golden.get("workload_total_delta", 0.25)),
		)
		self.assertAlmostEqual(
			wsum,
			float(golden["week_daily_sum"]),
			delta=float(golden.get("week_daily_sum_delta", 0.25)),
		)

	def test_tc14_user_group_filters_second_user_full_and_user_totals(self):
		"""user_group только с Administrator: в full одна строка пользователя ~40 ч; user_totals + SQL join — total_users=1."""
		ctx = prepare_case_user_group_excludes_second_user()
		project_name = ctx["project"]
		ug = ctx["user_group"]
		base = {
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
			"user_group": ug,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_full = run_get_projects_workload_data_v2({**base, "mode": "full"})
			out_tot = run_get_projects_workload_data_v2(
				{**base, "mode": "user_totals", "limit": 20, "offset": 0}
			)
		users_full = [r for r in (out_full.get("tree_data") or []) if r.get("_isUser")]
		self.assertEqual(len(users_full), 1, msg="Ожидался один пользователь после фильтра User Group")
		self.assertAlmostEqual(_parse_float_cell(users_full[0].get("workload_total")), 40.0, delta=0.35)
		self.assertEqual(int(out_tot.get("total_users") or 0), 1)
		rows_tot = out_tot.get("tree_data") or []
		self.assertEqual(len([r for r in rows_tot if r.get("_isUser")]), 1)

	def test_tc04b_percent_task_effort_v2_v3_parity(self):
		"""«В % от трудоемкости»: PWE план май 160 ч, 50% → ожидаем ~80 ч на интервале недели; V2≈V3."""
		if not frappe.db.exists("DocType", "Project Work Efforts"):
			self.skipTest("DocType Project Work Efforts не установлен")
		if not frappe.db.sql(
			"""
			select name from `tabFiscal Year`
			where year_start_date <= %(end)s and year_end_date >= %(start)s
			limit 1
			""",
			{"start": WEEK_START, "end": WEEK_END},
		):
			self.skipTest("Нет Fiscal Year на даты теста")
		ctx = prepare_case_percent_task_effort(50.0, plan_hours_may=160.0)
		project_name = ctx["project"]
		expected = 160.0 * 0.5
		fd_v2 = {
			"mode": "full",
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		fd_v3 = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
			out_v3 = run_get_project_workload_data(fd_v3)
		row_v2 = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		row_v3 = _find_v3_user_row(out_v3.get("tree_data") or [], BUSINESS_USER)
		t2 = _parse_float_cell(row_v2.get("workload_total"))
		t3 = _parse_float_cell(row_v3.get("workload_total"))
		self.assertAlmostEqual(t2, expected, delta=1.5, msg=f"V2 total={t2}, expected~{expected}")
		self.assertAlmostEqual(t3, expected, delta=1.5, msg=f"V3 total={t3}, expected~{expected}")
		self.assertAlmostEqual(t2, t3, delta=1.0, msg="V2 vs V3 parity task %")

	def test_tc05b_user_totals_two_pages_sum_matches_full(self):
		"""Два пользователя: сумма workload_total по страницам user_totals = сумма строк пользователей в full."""
		ctx = prepare_case_two_users_hours_for_pagination(40.0, 20.0)
		project_name = ctx["project"]
		base = {
			"view_type": "daily",
			"period_range": "quarter",
			"project": project_name,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_full = run_get_projects_workload_data_v2({**base, "mode": "full"})
			p0 = run_get_projects_workload_data_v2(
				{**base, "mode": "user_totals", "limit": 1, "offset": 0}
			)
			p1 = run_get_projects_workload_data_v2(
				{**base, "mode": "user_totals", "limit": 1, "offset": 1}
			)
		sum_full = _sum_team_v2_user_rows_total(out_full.get("tree_data"))
		self.assertAlmostEqual(sum_full, 60.0, delta=0.3, msg=f"full sum users={sum_full}")
		self.assertEqual(int(p0.get("total_users") or 0), 2)
		r0 = _find_team_v2_user_row(p0.get("tree_data") or [], BUSINESS_USER)
		r1 = _find_team_v2_user_row(p1.get("tree_data") or [], SECOND_USER_EMAIL)
		self.assertIsNotNone(r0)
		self.assertIsNotNone(r1)
		s_pages = _parse_float_cell(r0.get("workload_total")) + _parse_float_cell(r1.get("workload_total"))
		self.assertAlmostEqual(s_pages, sum_full, delta=0.25, msg=f"pages sum={s_pages} full={sum_full}")

	def test_tc12_monthly_view_user_total_matches_assignment(self):
		"""Месячный вид V2: итог пользователя по столбцам месяцев ≈ 40 ч (назначение внутри одного месяца)."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd_v2 = {
			"mode": "full",
			"view_type": "monthly",
			"period_range": "quarter",
			"project": project_name,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			out_v2 = run_get_projects_workload_data_v2(fd_v2)
		row = _find_team_v2_user_row(out_v2.get("tree_data") or [], BUSINESS_USER)
		self.assertIsNotNone(row)
		total = _parse_float_cell(row.get("workload_total"))
		self.assertAlmostEqual(total, 40.0, delta=0.5, msg=f"monthly workload_total={total}")

	def test_tc13_pwr_run_project_workload_tree_matches_direct(self):
		"""Whitelist `pwr_run_project_workload_tree` = прямой `run_get_project_workload_data`."""
		ctx = prepare_case_hours_without_project_holiday_list(40.0)
		project_name = ctx["project"]
		fd = {
			"project": project_name,
			"view_type": "daily",
			"date_from": WEEK_START,
			"date_to": WEEK_END,
		}
		with patch.object(frappe.utils, "nowdate", return_value=ANCHOR_MONDAY):
			frappe.set_user(BUSINESS_USER)
			direct = run_get_project_workload_data(fd)
			via_whitelist = _call_pwr_project_whitelist(fd)
		r1 = _find_v3_user_row(direct.get("tree_data") or [], BUSINESS_USER)
		r2 = _find_v3_user_row(via_whitelist.get("tree_data") or [], BUSINESS_USER)
		self.assertAlmostEqual(
			_parse_float_cell(r1.get("workload_total")),
			_parse_float_cell(r2.get("workload_total")),
			delta=0.01,
		)


def reset():
	reset_owned_data()
