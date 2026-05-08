# Copyright (c) 2026, Dinext
"""Whitelisted API для вызова из Server Script через frappe.call (RestrictedPython без import)."""

import json

import frappe

from dinext_common.dinext_common.project_workload.assignments import (
	count_pwr_report_distinct_users,
	fetch_pwr_report_assignments,
	fetch_pwr_report_user_page,
	fetch_project_assignments_with_worker_context,
)
from dinext_common.dinext_common.project_workload.periods import (
	build_date_to_period_key,
	generate_periods_for_pwr_report,
)
from dinext_common.dinext_common.project_workload.single_project_workload_tree import (
	run_get_project_workload_data,
)
from dinext_common.dinext_common.project_workload.tasks_forecast_workload import (
	run_get_tasks_forecast_and_workload,
)
from dinext_common.dinext_common.project_workload.team_workload_grid import (
	run_get_projects_workload_data_v2,
)
from dinext_common.dinext_common.project_workload.windows import (
	compute_assignment_sql_lower_bound,
	get_visible_window,
)


def _bool(v):
	if v is True or v is False:
		return v
	if isinstance(v, str):
		return v.lower() in ("1", "true", "yes")
	return bool(v)


def _parse_restrict_users(raw):
	if raw is None or raw == "":
		return None
	if isinstance(raw, (list, tuple)):
		return list(raw)
	if isinstance(raw, str):
		try:
			data = json.loads(raw)
			if isinstance(data, list):
				return data
		except json.JSONDecodeError:
			pass
		return [raw]
	return None


@frappe.whitelist()
def pwr_report_fetch_assignments(
	window_start,
	window_end,
	user=None,
	project=None,
	user_group=None,
	use_sql_user_group_join=None,
	restrict_users=None,
):
	use_join = _bool(use_sql_user_group_join)
	ru = _parse_restrict_users(restrict_users)
	return fetch_pwr_report_assignments(
		window_start,
		window_end,
		user=user,
		project=project,
		user_group_parent=user_group,
		use_sql_user_group_join=use_join,
		restrict_users=ru,
	)


@frappe.whitelist()
def pwr_report_count_distinct_users(
	window_start,
	window_end,
	user=None,
	project=None,
	user_group=None,
	use_sql_user_group_join=None,
):
	use_join = _bool(use_sql_user_group_join)
	return count_pwr_report_distinct_users(
		window_start,
		window_end,
		user=user,
		project=project,
		user_group_parent=user_group,
		use_sql_user_group_join=use_join,
	)


@frappe.whitelist()
def pwr_report_fetch_user_page(
	window_start,
	window_end,
	limit,
	offset,
	user=None,
	project=None,
	user_group=None,
	use_sql_user_group_join=None,
):
	use_join = _bool(use_sql_user_group_join)
	lim = int(limit or 0) or 20
	off = int(offset or 0)
	return fetch_pwr_report_user_page(
		window_start,
		window_end,
		limit=lim,
		offset=off,
		user=user,
		project=project,
		user_group_parent=user_group,
		use_sql_user_group_join=use_join,
	)


@frappe.whitelist()
def pwr_report_user_totals_assignments_bundle(
	window_start,
	window_end,
	limit,
	offset,
	user=None,
	project=None,
	user_group=None,
	use_sql_user_group_join=None,
):
	"""Один round-trip для режима user_totals: count + page_users + assignments."""
	use_join = _bool(use_sql_user_group_join)
	lim = int(limit or 0) or 20
	off = int(offset or 0)
	total_users = count_pwr_report_distinct_users(
		window_start,
		window_end,
		user=user,
		project=project,
		user_group_parent=user_group,
		use_sql_user_group_join=use_join,
	)
	page_users = fetch_pwr_report_user_page(
		window_start,
		window_end,
		limit=lim,
		offset=off,
		user=user,
		project=project,
		user_group_parent=user_group,
		use_sql_user_group_join=use_join,
	)
	if not page_users:
		return {'total_users': total_users, 'page_users': [], 'assignments': []}
	assignments = fetch_pwr_report_assignments(
		window_start,
		window_end,
		user=user,
		project=project,
		user_group_parent=user_group,
		use_sql_user_group_join=use_join,
		restrict_users=page_users,
	)
	return {'total_users': total_users, 'page_users': page_users, 'assignments': assignments}


@frappe.whitelist()
def pwr_project_fetch_assignments_extended(project, date_from, date_to):
	if not project:
		return []
	return fetch_project_assignments_with_worker_context(project, date_from, date_to)


@frappe.whitelist()
def pwr_generate_periods_and_sql_bounds(view_type='daily', period_range='quarter'):
	"""Периоды PWR V2 + границы окна для SQL назначений (один вызов из Server Script)."""
	periods = generate_periods_for_pwr_report(view_type, period_range or 'quarter')
	display_start, display_end = get_visible_window(periods, view_type)
	assignment_lower = compute_assignment_sql_lower_bound(display_start)
	return {
		'periods': periods,
		'window_start_sql': str(assignment_lower),
		'window_end_sql': str(display_end),
	}


@frappe.whitelist()
def pwr_build_date_to_period_key_map(periods, view_type):
	if isinstance(periods, str):
		periods = json.loads(periods)
	return build_date_to_period_key(periods, view_type)


@frappe.whitelist()
def pwr_run_get_projects_workload_data_v2():
	"""Полный ответ API get_projects_workload_data_v2 (ядро team_workload_grid)."""
	return run_get_projects_workload_data_v2(frappe.form_dict)


@frappe.whitelist()
def pwr_run_get_project_workload_data():
	"""Полный ответ API get_project_workload_data (ядро single_project_workload_tree)."""
	return run_get_project_workload_data(frappe.form_dict)


@frappe.whitelist()
def pwr_run_get_tasks_forecast_and_workload():
	"""Ответ API get_tasks_forecast_and_workload / v2 (ядро tasks_forecast_workload)."""
	return run_get_tasks_forecast_and_workload(frappe.form_dict)
