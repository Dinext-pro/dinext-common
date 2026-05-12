# Copyright (c) 2026, Dinext
"""Whitelisted API для вызова из Server Script через frappe.call (RestrictedPython без import).

Три точки входа (whitelist → api_method Server Script → модуль ядра):
- pwr_run_team_workload_grid → get_projects_workload_data_v2 → team_workload_grid.run_get_projects_workload_data_v2
- pwr_run_project_workload_tree → get_project_workload_data → single_project_workload_tree.run_get_project_workload_data
- pwr_run_tasks_forecast_workload → get_tasks_forecast_and_workload_v2 → tasks_forecast_workload.run_get_tasks_forecast_and_workload
"""

import frappe

from dinext_common.dinext_common.project_workload.single_project_workload_tree import (
	run_get_project_workload_data,
)
from dinext_common.dinext_common.project_workload.tasks_forecast_workload import (
	run_get_tasks_forecast_and_workload,
)
from dinext_common.dinext_common.project_workload.team_workload_grid import (
	run_get_projects_workload_data_v2,
)


@frappe.whitelist()
def pwr_run_team_workload_grid():
	"""Отчёт загрузки команды (Projects Workload Report). API method: get_projects_workload_data_v2."""
	return run_get_projects_workload_data_v2(frappe.form_dict)


@frappe.whitelist()
def pwr_run_project_workload_tree():
	"""Дерево загрузки одного проекта (форма Project). API method: get_project_workload_data."""
	return run_get_project_workload_data(frappe.form_dict)


@frappe.whitelist()
def pwr_run_tasks_forecast_workload():
	"""Прогноз PWE и факт PWA по задачам проекта. API method: get_tasks_forecast_and_workload_v2."""
	return run_get_tasks_forecast_and_workload(frappe.form_dict)
