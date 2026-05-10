# Copyright (c) 2026, Dinext
"""Вспомогательные функции по периодам Project Workload."""

import frappe


def build_date_to_period_key(periods, view_type):
	"""ISS-2026-00865: O(1) date -> period lookup without changing period payload."""
	result = {}
	for period in periods:
		if view_type == 'daily':
			result[period['date']] = period['key']
		else:
			current_date = frappe.utils.getdate(period['start_date'])
			end_date = frappe.utils.getdate(period['end_date'])
			while current_date <= end_date:
				result[str(current_date)] = period["key"]
				current_date = frappe.utils.add_days(current_date, 1)
	return result


def generate_periods_for_pwr_report(view_type, period_range):
	"""Сетка периодов для отчёта PWR V2 (как в Server Script Get Projects Workload Data_Exp_V2)."""
	periods = []
	today = frappe.utils.nowdate()
	current_date_obj = frappe.utils.getdate(today)

	if view_type == 'daily':
		days_count = 90
		if period_range == 'half_year':
			days_count = 180
		elif period_range == 'year':
			days_count = 365
		for i in range(days_count):
			date_str = frappe.utils.add_days(today, i)
			date_obj = frappe.utils.getdate(date_str)
			periods.append(
				{
					'key': 'workload_' + date_str,
					'date': date_str,
					'year': date_obj.year,
					'month': date_obj.month,
					'day': date_obj.day,
					'weekday': date_obj.weekday(),
				}
			)
	elif view_type == 'weekly':
		weeks_count = 13
		if period_range == 'half_year':
			weeks_count = 26
		elif period_range == 'year':
			weeks_count = 52
		week_start = frappe.utils.add_days(today, -current_date_obj.weekday())
		for i in range(weeks_count):
			week_start_date = frappe.utils.add_days(week_start, i * 7)
			week_end_date = frappe.utils.add_days(week_start_date, 6)
			week_start_obj = frappe.utils.getdate(week_start_date)
			periods.append(
				{
					'key': 'workload_' + str(week_start_obj.year) + '_week_' + str(i + 1),
					'year': week_start_obj.year,
					'week': i + 1,
					'start_date': str(week_start_date),
					'end_date': str(week_end_date),
				}
			)
	else:
		months_count = 3
		if period_range == 'half_year':
			months_count = 6
		elif period_range == 'year':
			months_count = 12
		for i in range(months_count):
			total_month = current_date_obj.month + i
			year = current_date_obj.year
			month = total_month
			if total_month > 12:
				year = year + 1
				month = total_month - 12
			month_str = str(month)
			if len(month_str) == 1:
				month_str = '0' + month_str
			start_date = frappe.utils.get_first_day(str(year) + '-' + month_str + '-01')
			end_date = frappe.utils.get_last_day(start_date)
			periods.append(
				{
					'key': 'workload_' + str(year) + '_' + str(month),
					'year': year,
					'month': month,
					'start_date': str(start_date),
					'end_date': str(end_date),
				}
			)

	return periods
