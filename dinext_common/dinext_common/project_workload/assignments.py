# Copyright (c) 2026, Dinext
"""Общая выборка назначений Project Workload (ISS-2026-00865 этап II)."""

import frappe
from frappe.query_builder.functions import Count
from frappe.utils import getdate


def _as_date(value):
	if value is None:
		return None
	return getdate(value)


def build_pwr_assignment_base_query(
	window_start,
	window_end,
	*,
	user=None,
	project=None,
	user_group_parent=None,
	use_sql_user_group_join=False,
):
	"""Базовый qb: PWA + Task, пересечение интервала назначения с [window_start, window_end]."""
	window_start = _as_date(window_start)
	window_end = _as_date(window_end)

	PWA = frappe.qb.DocType("Project Workload Assignment")
	Task = frappe.qb.DocType("Task")

	q = frappe.qb.from_(PWA).left_join(Task).on(PWA.task == Task.name)

	if user_group_parent and use_sql_user_group_join:
		UGM = frappe.qb.DocType("User Group Member")
		q = q.inner_join(UGM).on((UGM.parent == user_group_parent) & (UGM.user == PWA.user))

	q = (
		q.where(PWA.user.isnotnull())
		.where(PWA.task.isnotnull())
		.where(Task.project.isnotnull())
		.where(PWA.date_from.isnotnull())
		.where(PWA.date_to >= window_start)
		.where(PWA.date_from <= window_end)
	)

	if user:
		q = q.where(PWA.user == user)
	if project:
		q = q.where(Task.project == project)

	return q, PWA, Task


def fetch_pwr_report_assignments(
	window_start,
	window_end,
	*,
	user=None,
	project=None,
	user_group_parent=None,
	use_sql_user_group_join=False,
	restrict_users=None,
):
	"""Строки как в Get Projects Workload Data_Exp_V2 (поля PWA + project_name)."""
	q, PWA, Task = build_pwr_assignment_base_query(
		window_start,
		window_end,
		user=user,
		project=project,
		user_group_parent=user_group_parent,
		use_sql_user_group_join=use_sql_user_group_join,
	)

	q = q.select(
		PWA.name,
		PWA.task,
		PWA.role,
		PWA.user,
		PWA.date_from,
		PWA.date_to,
		PWA.workload,
		PWA.wl_value,
		PWA.acc_separately,
		Task.project.as_("project_name"),
	)

	if restrict_users:
		q = q.where(PWA.user.isin(list(restrict_users)))

	return q.run(as_dict=True)


def count_pwr_report_distinct_users(
	window_start,
	window_end,
	*,
	user=None,
	project=None,
	user_group_parent=None,
	use_sql_user_group_join=False,
):
	q, PWA, Task = build_pwr_assignment_base_query(
		window_start,
		window_end,
		user=user,
		project=project,
		user_group_parent=user_group_parent,
		use_sql_user_group_join=use_sql_user_group_join,
	)
	rows = q.select(Count(PWA.user).distinct().as_("total_users")).run(as_dict=True)
	if not rows:
		return 0
	return int(rows[0].get("total_users") or 0)


def fetch_pwr_report_user_page(
	window_start,
	window_end,
	*,
	limit,
	offset,
	user=None,
	project=None,
	user_group_parent=None,
	use_sql_user_group_join=False,
):
	q, PWA, Task = build_pwr_assignment_base_query(
		window_start,
		window_end,
		user=user,
		project=project,
		user_group_parent=user_group_parent,
		use_sql_user_group_join=use_sql_user_group_join,
	)
	rows = (
		q.select(PWA.user.as_("user"))
		.distinct()
		.orderby(PWA.user)
		.limit(int(limit))
		.offset(int(offset))
		.run(as_dict=True)
	)
	out = []
	for r in rows:
		u = r.get("user")
		if u:
			out.append(u)
	return out


def fetch_project_assignments_with_worker_context(project, date_from, date_to):
	"""Строки как в Get_Project_Workload_Data_V3 (Task + PWA + User + Worker + Timesheet Template)."""
	date_from = _as_date(date_from)
	date_to = _as_date(date_to)

	Task = frappe.qb.DocType("Task")
	PWA = frappe.qb.DocType("Project Workload Assignment")
	User = frappe.qb.DocType("User")
	Worker = frappe.qb.DocType("Worker")
	TimesheetTemplate = frappe.qb.DocType("Timesheet Template")

	q = (
		frappe.qb.from_(Task)
		.inner_join(PWA)
		.on(PWA.task == Task.name)
		.inner_join(User)
		.on((User.name == PWA.user) & (User.enabled == 1))
		.left_join(Worker)
		.on(Worker.wuser == PWA.user)
		.left_join(TimesheetTemplate)
		.on(TimesheetTemplate.name == Worker.wtimesheet_template)
		.select(
			Task.name.as_("task_id"),
			Task.subject.as_("task_subject"),
			PWA.name.as_("assignment_name"),
			PWA.role,
			PWA.user,
			PWA.date_from,
			PWA.date_to,
			PWA.workload,
			PWA.wl_value,
			PWA.acc_separately,
			User.full_name,
			User.user_image,
			User.email,
			Worker.wholiday_list,
			Worker.wtimesheet_template,
			TimesheetTemplate.hours_on_date,
			TimesheetTemplate.tt_working_hours_on_date,
		)
		.where(Task.project == project)
		.where(PWA.date_from.isnotnull())
		.where(PWA.date_to.isnotnull())
		.where(PWA.date_to >= date_from)
		.where(PWA.date_from <= date_to)
		.orderby(PWA.user, PWA.role, PWA.date_from)
	)

	return q.run(as_dict=True)
