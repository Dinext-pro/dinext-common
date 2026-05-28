# Copyright (c) 2026, Dinext
"""Backward-compat shim: canonical API in dinext_projects.project_workload_api."""

from dinext_projects.project_workload_api import (  # noqa: F401
	pwr_run_project_workload_tree,
	pwr_run_tasks_forecast_workload,
	pwr_run_team_workload_grid,
)

__all__ = [
	"pwr_run_team_workload_grid",
	"pwr_run_project_workload_tree",
	"pwr_run_tasks_forecast_workload",
]
