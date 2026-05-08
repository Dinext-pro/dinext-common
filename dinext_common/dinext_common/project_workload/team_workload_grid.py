# Copyright (c) 2026, Dinext
"""Сетка загрузки команды: ответ API get_projects_workload_data_v2 (бывший Exp_V2)."""

import frappe


def run_get_projects_workload_data_v2(fd):
	"""fd — dict или объект с .get как frappe._dict."""
	if fd is None:
		fd = {}
	PERF_TRACE = []
	PERF_TOTAL_START = frappe.utils.now_datetime()

	def perf_log(message):
		line = "[PWR V2 PERF] " + str(message)
		PERF_TRACE.append(line)
		frappe.log(line)

	def perf_start(label):
		perf_log("START " + label)
		return frappe.utils.now_datetime()

	def perf_end(label, started_at, extra=""):
		finished_at = frappe.utils.now_datetime()
		elapsed_ms = (finished_at - started_at).total_seconds() * 1000
		suffix = ""
		if extra:
			suffix = " | " + str(extra)
		perf_log("END " + label + ": " + str(int(elapsed_ms)) + " ms" + suffix)
		return elapsed_ms

	try:
		# ISS-2026-00865 V2: режимы нужны для первичной загрузки пользователей и lazy-load проектов.
		user = fd.get('user')
		project = fd.get('project')
		user_group = fd.get('user_group')
		view_type = fd.get('view_type', 'daily')
		period_range = fd.get('period_range', 'quarter')
		mode = fd.get('mode', 'full')
		detail_user = fd.get('detail_user')
		
		try:
		    limit = int(fd.get('limit') or 20)
		except Exception:
		    limit = 20
		try:
		    offset = int(fd.get('offset') or 0)
		except Exception:
		    offset = 0
		if limit < 1:
		    limit = 20
		if limit > 100:
		    limit = 100
		if offset < 0:
		    offset = 0
		
		if mode == 'user_projects' and detail_user:
		    # Для детализации считаем только одного пользователя, сохраняя остальные фильтры.
		    user = detail_user
		
		frappe.log("Filter values - user: " + str(user) + ", project: " + str(project) + ", user_group: " + str(user_group) + ", mode: " + str(mode))
		perf_log("PARAMS mode=" + str(mode) + ", limit=" + str(limit) + ", offset=" + str(offset) + ", detail_user=" + str(detail_user) + ", view_type=" + str(view_type) + ", period_range=" + str(period_range) + ", user=" + str(user) + ", project=" + str(project) + ", user_group=" + str(user_group))
		
		# ISS-2026-00865 V2: для user_totals сначала выбираем только страницу пользователей,
		# а затем грузим назначения только по этой странице. Детализация проектов остается
		# отдельным mode=user_projects.
		user_totals_sql_paged = mode == 'user_totals'
		total_users = 0
		page_users = []
		has_more = False
		next_offset = None
		
		# ISS-2026-00865: периоды и границы SQL — dinext_common.project_workload (локально).
		early_period_start = perf_start("Generate periods early for SQL window")
		from dinext_common.dinext_common.project_workload.periods import generate_periods_for_pwr_report
		from dinext_common.dinext_common.project_workload.windows import (
		    compute_assignment_sql_lower_bound,
		    get_visible_window,
		)
		periods = generate_periods_for_pwr_report(view_type, period_range)
		display_start_win, display_end_win = get_visible_window(periods, view_type)
		assignment_lower_dt = compute_assignment_sql_lower_bound(display_start_win)
		assignment_date_to_lower_bound = frappe.utils.getdate(assignment_lower_dt)
		display_end = frappe.utils.getdate(display_end_win)
		ws = str(assignment_date_to_lower_bound)
		we = str(display_end)
		perf_end("Generate periods early for SQL window", early_period_start, "periods=" + str(len(periods)) + ", window_sql=" + str(ws) + ".." + str(we))
		
		# ========== 1. ПОЛУЧЕНИЕ ВСЕХ НЕОБХОДИМЫХ ДАННЫХ ==========
		# ISS-2026-00865 этап II: выборка назначений — dinext_common.project_workload_assignments (frappe.call).
		
		
		use_sql_ug = bool(user_totals_sql_paged and user_group)
		
		assignments = []
		if user_totals_sql_paged:
		    perf_section_start = perf_start("SQL user_totals bundle")
		    from dinext_common.dinext_common.project_workload.assignments import (
		        count_pwr_report_distinct_users,
		        fetch_pwr_report_assignments,
		        fetch_pwr_report_user_page,
		    )
		    use_join = bool(use_sql_ug)
		    total_users = count_pwr_report_distinct_users(
		        ws,
		        we,
		        user=user,
		        project=project,
		        user_group_parent=user_group,
		        use_sql_user_group_join=use_join,
		    )
		    page_users = fetch_pwr_report_user_page(
		        ws,
		        we,
		        limit=limit,
		        offset=offset,
		        user=user,
		        project=project,
		        user_group_parent=user_group,
		        use_sql_user_group_join=use_join,
		    )
		    if not page_users:
		        bundle = {"total_users": total_users, "page_users": [], "assignments": []}
		    else:
		        assignments_fb = fetch_pwr_report_assignments(
		            ws,
		            we,
		            user=user,
		            project=project,
		            user_group_parent=user_group,
		            use_sql_user_group_join=use_join,
		            restrict_users=page_users,
		        )
		        bundle = {
		            "total_users": total_users,
		            "page_users": page_users,
		            "assignments": assignments_fb,
		        }
		    total_users = int(bundle.get("total_users") or 0)
		    page_users = bundle.get("page_users") or []
		    assignments = bundle.get("assignments") or []
		    if offset + len(page_users) < total_users:
		        has_more = True
		        next_offset = offset + len(page_users)
		    perf_end(
		        "SQL user_totals bundle",
		        perf_section_start,
		        "total_users=" + str(total_users) + ", page_users=" + str(len(page_users)) + ", assignments=" + str(len(assignments)) + ", has_more=" + str(has_more),
		    )
		
		perf_section_start = perf_start("SQL main assignments")
		if user_totals_sql_paged:
		    pass
		elif not assignments:
		    from dinext_common.dinext_common.project_workload.assignments import fetch_pwr_report_assignments
		    assignments = fetch_pwr_report_assignments(
		        ws,
		        we,
		        user=user,
		        project=project,
		        user_group_parent=user_group,
		        use_sql_user_group_join=bool(use_sql_ug),
		        restrict_users=None,
		    )
		    if assignments is None:
		        assignments = []
		perf_end("SQL main assignments", perf_section_start, "rows=" + str(len(assignments)) + ", date_to_lower=" + str(assignment_date_to_lower_bound) + ", date_from_upper=" + str(display_end) + ", pre_paged_users=" + str(len(page_users)))
		
		if not assignments:
		    return  {
		        'tree_data': [], 'periods': [], 'users_count': 0,
		        'projects_count': 0, 'assignments_count': 0,
		        'message': 'No assignments found'
		    }
		
		
		# Фильтр по группе пользователей
		if user_group and not user_totals_sql_paged:
		    perf_section_start = perf_start("SQL user group members")
		    group_users_result = frappe.qb.get_query(
		        "User Group Member",
		        fields=["user"],
		        filters=[["parent", "=", user_group], ["user", "is", "set"]],
		    ).run(as_dict=True)
		    perf_end("SQL user group members", perf_section_start, "rows=" + str(len(group_users_result)))
		
		    group_users = {}
		    for row in group_users_result:
		        group_users[row['user']] = True
		
		    if group_users:
		        perf_section_start = perf_start("Python filter assignments by user_group")
		        assignments_before_group_filter = len(assignments)
		        filtered_assignments = []
		        for a in assignments:
		            if a['user'] in group_users:
		                filtered_assignments.append(a)
		        assignments = filtered_assignments
		        perf_end("Python filter assignments by user_group", perf_section_start, "before=" + str(assignments_before_group_filter) + ", after=" + str(len(assignments)))
		        if not assignments:
		            return  {
		                'tree_data': [], 'periods': [], 'users_count': 0,
		                'projects_count': 0, 'assignments_count': 0,
		                'message': 'No assignments after group filter'
		            }
		
		
		frappe.log("Found " + str(len(assignments)) + " assignments")
		
		# 1.2 Собираем уникальные сущности
		users_set = {}
		projects_set = {}
		for a in assignments:
		    users_set[a['user']] = True
		    projects_set[a['project_name']] = True
		
		if not user_totals_sql_paged:
		    all_users_list = list(users_set.keys())
		    all_users_list.sort()
		    total_users = len(all_users_list)
		    page_users = all_users_list
		    has_more = False
		    next_offset = None
		
		if mode == 'user_totals' and not user_totals_sql_paged:
		    page_users = all_users_list[offset:offset + limit]
		    if offset + limit < total_users:
		        has_more = True
		        next_offset = offset + limit
		    page_user_map = {}
		    for page_user in page_users:
		        page_user_map[page_user] = True
		    paged_assignments = []
		    for assignment in assignments:
		        if assignment['user'] in page_user_map:
		            paged_assignments.append(assignment)
		    assignments = paged_assignments
		elif mode == 'user_projects':
		    detail_user_value = detail_user or user
		    page_users = []
		    if detail_user_value:
		        page_users.append(detail_user_value)
		    page_user_map = {}
		    for page_user in page_users:
		        page_user_map[page_user] = True
		    detail_assignments = []
		    for assignment in assignments:
		        if assignment['user'] in page_user_map:
		            detail_assignments.append(assignment)
		    assignments = detail_assignments
		
		users_set = {}
		projects_set = {}
		for a in assignments:
		    users_set[a['user']] = True
		    projects_set[a['project_name']] = True
		users_list = list(users_set.keys())
		users_list.sort()
		projects_list = list(projects_set.keys())
		projects_list.sort()
		perf_log("PAGING total_users=" + str(total_users) + ", returned_users=" + str(len(users_list)) + ", has_more=" + str(has_more) + ", next_offset=" + str(next_offset))
		
		# ========== 2. ПАРАЛЛЕЛЬНАЯ ЗАГРУЗКА ДАННЫХ ==========
		
		# 2.1 Данные пользователей
		users_data = {}
		if users_list:
		    perf_section_start = perf_start("SQL users/workers/timesheet templates")
		    User = frappe.qb.DocType("User")
		    Worker = frappe.qb.DocType("Worker")
		    TS = frappe.qb.DocType("Timesheet Template")
		    users_db = (
		        frappe.qb.from_(User)
		        .left_join(Worker)
		        .on(User.name == Worker.wuser)
		        .left_join(TS)
		        .on(Worker.wtimesheet_template == TS.name)
		        .select(
		            User.name,
		            User.full_name,
		            User.user_image,
		            User.email,
		            Worker.wholiday_list,
		            Worker.wtimesheet_template,
		            TS.hours_on_date,
		            TS.tt_working_hours_on_date,
		        )
		        .where(User.name.isin(users_list))
		        .where(User.enabled == 1)
		    ).run(as_dict=True)
		    perf_end("SQL users/workers/timesheet templates", perf_section_start, "users_filter=" + str(len(users_list)) + ", rows=" + str(len(users_db)))
		    for u in users_db:
		        users_data[u['name']] = u
		
		# 2.2 Данные проектов
		projects_data = {}
		if projects_list:
		    perf_section_start = perf_start("SQL projects")
		    projects_db = frappe.qb.get_query(
		        "Project",
		        fields=["name", "project_name", "holiday_list"],
		        filters=[["name", "in", projects_list]],
		    ).run(as_dict=True)
		    perf_end("SQL projects", perf_section_start, "projects_filter=" + str(len(projects_list)) + ", rows=" + str(len(projects_db)))
		    for p in projects_db:
		        projects_data[p['name']] = p
		
		# ========== 3. ЗАГРУЗКА СПРАВОЧНИКОВ ==========
		
		# 3.1 Working Hours Override
		working_hours_overrides = {}
		working_hours_refs = {}
		for user_data in users_data.values():
		    if user_data.get('tt_working_hours_on_date'):
		        working_hours_refs[user_data['tt_working_hours_on_date']] = True
		
		if working_hours_refs:
		    ref_list = list(working_hours_refs.keys())
		    perf_section_start = perf_start("SQL working hours overrides")
		    overrides = frappe.qb.get_query(
		        "Working Hours Table",
		        fields=["parent as ref_name", "wht_date", "wht_hours"],
		        filters=[
		            ["parent", "in", ref_list],
		            ["parentfield", "=", "hod_working_hours_table"],
		            ["parenttype", "=", "Working Hours On Date"],
		        ],
		    ).run(as_dict=True)
		    perf_end("SQL working hours overrides", perf_section_start, "refs=" + str(len(ref_list)) + ", rows=" + str(len(overrides)))
		    for row in overrides:
		        if row.ref_name not in working_hours_overrides:
		            working_hours_overrides[row.ref_name] = {}
		        if row.wht_date:
		            working_hours_overrides[row.ref_name][str(row.wht_date)] = float(row.wht_hours or 0)
		
		# 3.2 Holiday Lists
		holiday_lists_cache = {}
		# ISS-2026-00865: дополнительный set-cache только для быстрого lookup;
		# response по-прежнему использует списки holiday_lists_cache.
		holiday_date_sets = {}
		all_holiday_lists = {}
		
		# Собираем все holiday lists
		for project in projects_data.values():
		    if project.get('holiday_list'):
		        all_holiday_lists[project['holiday_list']] = True
		
		for user in users_data.values():
		    if user.get('wholiday_list'):
		        all_holiday_lists[user['wholiday_list']] = True
		
		if all_holiday_lists:
		    holiday_list = list(all_holiday_lists.keys())
		    perf_section_start = perf_start("SQL holidays")
		    holidays = frappe.qb.get_query(
		        "Holiday",
		        fields=["parent as list_name", "holiday_date", "description", "weekly_off"],
		        filters=[
		            ["parent", "in", holiday_list],
		            ["parentfield", "=", "holidays"],
		            ["parenttype", "=", "Holiday List"],
		        ],
		    ).run(as_dict=True)
		    perf_end("SQL holidays", perf_section_start, "holiday_lists=" + str(len(holiday_list)) + ", rows=" + str(len(holidays)))
		    for row in holidays:
		        if row.list_name not in holiday_lists_cache:
		            holiday_lists_cache[row.list_name] = []
		            holiday_date_sets[row.list_name] = {}
		
		        holiday_item = {
		            'date': str(row.holiday_date),
		            'description': row.description,
		            'weekly_off': row.weekly_off
		        }
		        holiday_lists_cache[row.list_name].append(holiday_item)
		        holiday_date_sets[row.list_name][str(row.holiday_date)] = True
		
		# 3.3 Отсутствия
		user_absences = {}
		if users_list:
		    today = frappe.utils.nowdate()
		    perf_section_start = perf_start("SQL absences")
		    absences = frappe.qb.get_query(
		        "Application For Leave",
		        fields=[
		            "lauser",
		            "alfrom_date",
		            "alto_date",
		            "altype_of_leave",
		            "alfrom_hours",
		            "alto_hours",
		        ],
		        filters=[
		            ["lauser", "in", users_list],
		            ["status", "=", "Согласовано"],
		            ["alfrom_date", "is", "set"],
		            ["alto_date", "is", "set"],
		            ["alto_date", ">=", today],
		        ],
		    ).run(as_dict=True)
		    perf_end("SQL absences", perf_section_start, "users=" + str(len(users_list)) + ", rows=" + str(len(absences)))
		    for absence in absences:
		        user_email = absence.lauser
		        if user_email not in user_absences:
		            user_absences[user_email] = []
		
		        absence_item = {
		            'from_date': absence.alfrom_date,
		            'to_date': absence.alto_date,
		            'type': absence.altype_of_leave,
		            'alfrom_hours': absence.alfrom_hours,
		            'alto_hours': absence.alto_hours
		        }
		        user_absences[user_email].append(absence_item)
		
		# 3.4 Плановые часы (Project Work Efforts)
		monthly_plan_cache = {}
		# ISS-2026-00865: раньше здесь был N+1, отдельный SQL на каждую пару task+role.
		# Для сохранения результата ключ cache остается тем же: task_role_year_month.
		task_role_pairs = {}
		tasks_set = {}
		roles_set = {}
		for assignment in assignments:
		    if assignment.get('task') and assignment.get('role'):
		        pair_key = assignment['task'] + "\n" + assignment['role']
		        task_role_pairs[pair_key] = True
		        tasks_set[assignment['task']] = True
		        roles_set[assignment['role']] = True
		
		if task_role_pairs:
		    task_list = list(tasks_set.keys())
		    role_list = list(roles_set.keys())
		    perf_section_start = perf_start("SQL project work efforts batch")
		    PWE = frappe.qb.DocType("Project Work Efforts")
		    PWEA = frappe.qb.DocType("Project Work Efforts Amount")
		    plans = (
		        frappe.qb.from_(PWE)
		        .inner_join(PWEA)
		        .on(PWEA.parent == PWE.name)
		        .select(
		            PWE.pwe_task.as_("task"),
		            PWE.pwe_project_role.as_("role"),
		            PWEA.pwea_year.as_("year"),
		            PWEA.pwea_month.as_("month"),
		            PWEA.pwea_plan.as_("plan_hours"),
		        )
		        .where(PWE.pwe_task.isin(task_list))
		        .where(PWE.pwe_project_role.isin(role_list))
		        .where(PWEA.pwea_plan > 0)
		    ).run(as_dict=True)
		    for plan in plans:
		        key = plan['task'] + "_" + plan['role'] + "_" + str(plan['year']) + "_" + str(plan['month'])
		        monthly_plan_cache[key] = float(plan['plan_hours'] or 0)
		    perf_end("SQL project work efforts batch", perf_section_start, "task_roles=" + str(len(task_role_pairs)) + ", tasks=" + str(len(task_list)) + ", roles=" + str(len(role_list)) + ", rows=" + str(len(plans)) + ", cache=" + str(len(monthly_plan_cache)))
		else:
		    perf_log("SKIP SQL project work efforts batch | task_roles=0")
		
		# ========== 4. ПЕРИОДЫ ==========
		# periods уже сгенерированы в начале (pwr_generate_periods_and_sql_bounds); дубликат генерации убран.
		frappe.log("Generated " + str(len(periods)) + " periods for view_type=" + view_type + ", range=" + period_range)
		if periods:
		    frappe.log("First period: " + str(periods[0]))
		# ISS-2026-00865: один раз строим lookup, чтобы не перебирать periods в горячих циклах.
		perf_section_start = perf_start("Build date_to_period_key")
		from dinext_common.dinext_common.project_workload.periods import build_date_to_period_key
		date_to_period_key = build_date_to_period_key(periods, view_type)
		if date_to_period_key is None:
		    date_to_period_key = {}
		perf_end("Build date_to_period_key", perf_section_start, "dates=" + str(len(date_to_period_key)))
		
		# ========== 5. ПРЕДВАРИТЕЛЬНЫЕ ВЫЧИСЛЕНИЯ ==========
		
		# 5.1 Кэш рабочих часов пользователей по дням
		perf_section_start = perf_start("Precompute user daily hours")
		user_daily_hours = {}
		user_daily_hours_dates_count = 0
		for user_email in users_list:
		    user_data = users_data.get(user_email, {})
		    base_hours = 8.0
		    if user_data.get('hours_on_date'):
		        base_hours = float(user_data['hours_on_date'])
		
		    working_hours_ref = user_data.get('tt_working_hours_on_date')
		
		    hours_dict = {}
		    # Предвычисляем часы для всех дат во всех периодах
		    for period in periods:
		        if view_type == 'daily':
		            date_str = period['date']
		            hours_on_date = base_hours
		
		            if working_hours_ref and working_hours_ref in working_hours_overrides:
		                override_dict = working_hours_overrides[working_hours_ref]
		                if date_str in override_dict:
		                    hours_on_date = override_dict[date_str]
		
		            hours_dict[date_str] = hours_on_date
		            user_daily_hours_dates_count = user_daily_hours_dates_count + 1
		        else:
		            # Для недель/месяцев вычисляем все даты в диапазоне
		            start_date = frappe.utils.getdate(period['start_date'])
		            end_date = frappe.utils.getdate(period['end_date'])
		            current_date = start_date
		            while current_date <= end_date:
		                date_str = str(current_date)
		                hours_on_date = base_hours
		
		                if working_hours_ref and working_hours_ref in working_hours_overrides:
		                    override_dict = working_hours_overrides[working_hours_ref]
		                    if date_str in override_dict:
		                        hours_on_date = override_dict[date_str]
		
		                hours_dict[date_str] = hours_on_date
		                user_daily_hours_dates_count = user_daily_hours_dates_count + 1
		                current_date = frappe.utils.add_days(current_date, 1)
		
		    user_daily_hours[user_email] = hours_dict
		perf_end("Precompute user daily hours", perf_section_start, "users=" + str(len(users_list)) + ", date_entries=" + str(user_daily_hours_dates_count))
		
		# 5.2 Функция проверки рабочего дня (аналогичная оригинальной)
		working_day_cache = {}
		
		def is_working_day_cached(date_str, user_email, project_name):
		    """Кэшированная проверка рабочего дня по оригинальной логике"""
		    cache_key = date_str + "_" + user_email + "_" + project_name
		
		    if cache_key in working_day_cache:
		        return working_day_cache[cache_key]
		
		    # Проверка праздников проекта
		    project_data = projects_data.get(project_name, {})
		    project_holiday_list = project_data.get('holiday_list')
		    if project_holiday_list and project_holiday_list in holiday_date_sets:
		        if date_str in holiday_date_sets[project_holiday_list]:
		            working_day_cache[cache_key] = False
		            return False
		
		    # Проверка праздников пользователя
		    user_data = users_data.get(user_email, {})
		    user_holiday_list = user_data.get('wholiday_list')
		    if user_holiday_list and user_holiday_list in holiday_date_sets:
		        if date_str in holiday_date_sets[user_holiday_list]:
		            working_day_cache[cache_key] = False
		            return False
		
		    # Проверка отсутствий (оригинальная логика)
		    if user_email in user_absences:
		        user_hours_dict = user_daily_hours.get(user_email, {})
		        user_hours = user_hours_dict.get(date_str, 8.0)
		        target_date = frappe.utils.getdate(date_str)
		
		        user_absence_list = user_absences[user_email]
		        for absence in user_absence_list:
		            if not (absence['from_date'] and absence['to_date']):
		                continue
		
		            from_date = frappe.utils.getdate(absence['from_date'])
		            to_date = frappe.utils.getdate(absence['to_date'])
		
		            if from_date <= target_date and target_date <= to_date:
		                absence_hours = 0.0
		                if target_date == from_date and absence.get('alfrom_hours'):
		                    absence_hours = float(absence['alfrom_hours'])
		                elif target_date == to_date and absence.get('alto_hours'):
		                    absence_hours = float(absence['alto_hours'])
		                else:
		                    absence_hours = user_hours
		
		                if absence_hours >= user_hours:
		                    working_day_cache[cache_key] = False
		                    return False
		
		    working_day_cache[cache_key] = True
		    return True
		
		# 5.3 Функция получения часов отсутствия (оригинальная)
		def get_absence_hours(date_str, user_email):
		    """Получение часов отсутствия на конкретную дату по оригинальной логике"""
		    if user_email not in user_absences:
		        return 0.0
		
		    user_hours_dict = user_daily_hours.get(user_email, {})
		    user_hours = user_hours_dict.get(date_str, 8.0)
		    target_date = frappe.utils.getdate(date_str)
		
		    user_absence_list = user_absences[user_email]
		    for absence in user_absence_list:
		        if not (absence['from_date'] and absence['to_date']):
		            continue
		
		        from_date = frappe.utils.getdate(absence['from_date'])
		        to_date = frappe.utils.getdate(absence['to_date'])
		
		        if from_date <= target_date and target_date <= to_date:
		            if target_date == from_date and absence.get('alfrom_hours'):
		                return float(absence['alfrom_hours'])
		            elif target_date == to_date and absence.get('alto_hours'):
		                return float(absence['alto_hours'])
		            else:
		                return user_hours
		
		    return 0.0
		
		# ========== 6. РАСЧЕТ НАГРУЗКИ ПО ОРИГИНАЛЬНОЙ ЛОГИКЕ ==========
		
		frappe.log("Starting workload calculation with original logic...")
		perf_section_start = perf_start("Calculate workload original logic")
		start_time = frappe.utils.now_datetime()
		
		# Результаты: для user_totals считаем напрямую user -> period_key -> hours,
		# для user_projects сохраняем детализацию user -> project -> period_key -> hours.
		direct_user_totals = user_totals_sql_paged
		results = {}
		assignment_calculations = 0
		workload_type_counts = {}
		date_loop_iterations = 0
		period_lookup_iterations = 0
		
		def find_period_key(date_str):
		    nonlocal period_lookup_iterations
		    period_lookup_iterations = period_lookup_iterations + 1
		    return date_to_period_key.get(date_str)
		
		month_working_day_iterations = 0
		
		# Глобальный кэш рабочих дней в месяце
		month_working_days_cache = {}
		
		# ОПТИМИЗАЦИЯ: Предварительно группируем назначения по пользователям и проектам
		assignments_by_user_project = {}
		for assignment in assignments:
		    user_email = assignment['user']
		    project_name = assignment['project_name']
		
		    if user_email not in assignments_by_user_project:
		        assignments_by_user_project[user_email] = {}
		
		    if project_name not in assignments_by_user_project[user_email]:
		        assignments_by_user_project[user_email][project_name] = []
		
		    assignments_by_user_project[user_email][project_name].append(assignment)
		
		# Обрабатываем каждую комбинацию пользователь-проект
		user_emails = list(assignments_by_user_project.keys())
		for user_email in user_emails:
		    user_projects = assignments_by_user_project[user_email]
		    project_names = list(user_projects.keys())
		
		    for project_name in project_names:
		        user_assignments = user_projects[project_name]
		
		        # Инициализируем структуру результатов
		        if user_email not in results:
		            results[user_email] = {}
		            if direct_user_totals:
		                for p in periods:
		                    results[user_email][p['key']] = 0.0
		
		        if not direct_user_totals and project_name not in results[user_email]:
		            results[user_email][project_name] = {}
		            for p in periods:
		                results[user_email][project_name][p['key']] = 0.0
		
		        # Обрабатываем все назначения пользователя на этом проекте
		        for assignment in user_assignments:
		            workload_label = assignment.get('workload') or 'Unknown'
		            workload_type_counts[workload_label] = workload_type_counts.get(workload_label, 0) + 1
		            date_from = frappe.utils.getdate(assignment['date_from'])
		            date_to = frappe.utils.getdate(assignment['date_to'])
		
		            # Тип 1: В рабочих часах (ОРИГИНАЛЬНАЯ ЛОГИКА)
		            if assignment['workload'] == 'В рабочих часах':
		                total_assignment_hours = 0.0
		                if assignment['wl_value']:
		                    total_assignment_hours = float(assignment['wl_value'])
		
		                # ISS-2026-00865: для "В рабочих часах" сохраняем оригинальный знаменатель
		                # по полному диапазону назначения. Если обрезать его видимым окном,
		                # итоговые часы в tree_data изменятся.
		                total_available_in_period = 0.0
		                date_available_hours = {}  # Кэшируем доступные часы по датам
		
		                current_date = date_from
		                while current_date <= date_to:
		                    date_loop_iterations = date_loop_iterations + 1
		                    date_str = str(current_date)
		
		                    if is_working_day_cached(date_str, user_email, project_name):
		                        day_base_hours_dict = user_daily_hours.get(user_email, {})
		                        day_base_hours = day_base_hours_dict.get(date_str, 8.0)
		                        absence_hours = get_absence_hours(date_str, user_email)
		                        available_hours = day_base_hours - absence_hours
		                        if available_hours < 0:
		                            available_hours = 0.0
		
		                        total_available_in_period = total_available_in_period + available_hours
		                        date_available_hours[date_str] = available_hours
		                        assignment_calculations = assignment_calculations + 1
		
		                    current_date = frappe.utils.add_days(current_date, 1)
		
		                if total_available_in_period > 0:
		                    # Распределяем нагрузку по датам
		                    date_keys = list(date_available_hours.keys())
		                    for date_str in date_keys:
		                        available_hours_on_date = date_available_hours[date_str]
		                        if available_hours_on_date > 0:
		                            daily_ratio = available_hours_on_date / total_available_in_period
		                            daily_hours = total_assignment_hours * daily_ratio
		
		                            # ISS-2026-00865: быстрый lookup вместо вложенного перебора periods.
		                            period_key = find_period_key(date_str)
		
		                            if period_key:
		                                if direct_user_totals:
		                                    current_value = results[user_email][period_key]
		                                    results[user_email][period_key] = current_value + daily_hours
		                                else:
		                                    current_value = results[user_email][project_name][period_key]
		                                    results[user_email][project_name][period_key] = current_value + daily_hours
		
		            # Тип 2: В % от фонда рабочих часов (ОРИГИНАЛЬНАЯ ЛОГИКА)
		            elif assignment['workload'] == 'В % от фонда рабочих часов':
		                percentage_value = 0.0
		                if assignment['wl_value']:
		                    percentage_value = float(assignment['wl_value']) / 100  # Делим на 100 сразу
		
		                current_date = date_from
		                while current_date <= date_to:
		                    date_loop_iterations = date_loop_iterations + 1
		                    date_str = str(current_date)
		
		                    if is_working_day_cached(date_str, user_email, project_name):
		                        day_base_hours_dict = user_daily_hours.get(user_email, {})
		                        day_base_hours = day_base_hours_dict.get(date_str, 8.0)
		                        absence_hours = get_absence_hours(date_str, user_email)
		                        available_hours = day_base_hours - absence_hours
		                        if available_hours < 0:
		                            available_hours = 0.0
		
		                        daily_load = percentage_value * available_hours
		                        assignment_calculations = assignment_calculations + 1
		
		                        # ISS-2026-00865: быстрый lookup вместо вложенного перебора periods.
		                        period_key = find_period_key(date_str)
		
		                        if period_key:
		                            if direct_user_totals:
		                                current_value = results[user_email][period_key]
		                                results[user_email][period_key] = current_value + daily_load
		                            else:
		                                current_value = results[user_email][project_name][period_key]
		                                results[user_email][project_name][period_key] = current_value + daily_load
		
		                    current_date = frappe.utils.add_days(current_date, 1)
		
		            # Тип 3: В % от трудоемкости задачи (ИСПРАВЛЕННАЯ PROD-ЛОГИКА)
		            elif assignment['workload'] == 'В % от трудоемкости задачи':
		                percentage_value = 0.0
		                if assignment['wl_value']:
		                    percentage_value = float(assignment['wl_value']) / 100  # Делим на 100 сразу
		
		                task = assignment['task']
		                role = assignment['role']
		
		                # ISS-2026-00865 / ISS-2026-00586: prod-версия считает плановую
		                # трудоемкость только по рабочим дням внутри диапазона назначения,
		                # а не по всем рабочим дням календарного месяца.
		                months_in_period = {}
		                current_date = date_from
		                while current_date <= date_to:
		                    date_loop_iterations = date_loop_iterations + 1
		                    year = current_date.year
		                    month = current_date.month
		                    month_key = str(year) + "_" + str(month)
		
		                    if month_key not in months_in_period:
		                        months_in_period[month_key] = {
		                            'year': year,
		                            'month': month,
		                            'working_days': 0,
		                            'dates': []
		                        }
		
		                    date_str = str(current_date)
		                    months_in_period[month_key]['dates'].append(date_str)
		
		                    if is_working_day_cached(date_str, user_email, project_name):
		                        months_in_period[month_key]['working_days'] = months_in_period[month_key]['working_days'] + 1
		                        month_working_day_iterations = month_working_day_iterations + 1
		
		                    current_date = frappe.utils.add_days(current_date, 1)
		
		                for month_key, month_info in months_in_period.items():
		                    year = month_info['year']
		                    month = month_info['month']
		                    plan_key = task + "_" + role + "_" + str(year) + "_" + str(month)
		
		                    if plan_key in monthly_plan_cache:
		                        monthly_plan_hours = monthly_plan_cache[plan_key]
		
		                        if monthly_plan_hours > 0 and month_info['working_days'] > 0:
		                            base_daily_hours = monthly_plan_hours / month_info['working_days']
		
		                            for date_str in month_info['dates']:
		                                if is_working_day_cached(date_str, user_email, project_name):
		                                    daily_load = percentage_value * base_daily_hours
		
		                                    # ISS-2026-00865: быстрый lookup вместо вложенного перебора periods.
		                                    period_key = find_period_key(date_str)
		
		                                    if period_key:
		                                        if direct_user_totals:
		                                            current_value = results[user_email][period_key]
		                                            results[user_email][period_key] = current_value + daily_load
		                                        else:
		                                            current_value = results[user_email][project_name][period_key]
		                                            results[user_email][project_name][period_key] = current_value + daily_load
		                                        assignment_calculations = assignment_calculations + 1
		
		end_time = frappe.utils.now_datetime()
		time_diff = end_time - start_time
		calculation_time = time_diff.total_seconds() * 1000
		
		frappe.log("Calculation completed in " + str(calculation_time) + " ms, " + str(assignment_calculations) + " date calculations")
		perf_end("Calculate workload original logic", perf_section_start, "assignments=" + str(len(assignments)) + ", direct_user_totals=" + str(direct_user_totals) + ", workload_types=" + str(workload_type_counts) + ", date_loop_iterations=" + str(date_loop_iterations) + ", period_lookup_iterations=" + str(period_lookup_iterations) + ", month_working_day_iterations=" + str(month_working_day_iterations) + ", working_day_cache_size=" + str(len(working_day_cache)))
		
		# ========== 7. ФОРМИРОВАНИЕ TREE DATA ==========
		
		perf_section_start = perf_start("Build tree_data response")
		tree_data = []
		user_emails_result = list(results.keys())
		user_emails_result.sort()
		return_user_rows = mode != 'user_projects'
		return_project_rows = mode != 'user_totals'
		
		for user_email in user_emails_result:
		    projects_result = results[user_email]
		
		    # Строка пользователя
		    user_total = {}
		    for p in periods:
		        user_total[p['key']] = 0.0
		
		    if direct_user_totals:
		        period_keys = list(projects_result.keys())
		        for period_key in period_keys:
		            user_total[period_key] = projects_result[period_key]
		        project_names_result = []
		    else:
		        # Суммируем нагрузку по всем проектам пользователя
		        project_names_result = list(projects_result.keys())
		        for project_name in project_names_result:
		            period_hours = projects_result[project_name]
		            period_keys = list(period_hours.keys())
		            for period_key in period_keys:
		                hours = period_hours[period_key]
		                user_total[period_key] = user_total[period_key] + hours
		
		    # Получаем данные пользователя
		    user_info = users_data.get(user_email, {})
		    if not user_info:
		        # Если пользователь не найден в users_data, создаем базовую запись
		        user_info = {
		            'full_name': user_email,
		            'user_image': None,
		            'email': user_email,
		            'name': user_email,
		            'wholiday_list': None
		        }
		
		    # Создаем строку пользователя
		    user_row = {
		        'participant': user_email,
		        'user_data': {
		            'full_name': user_info.get('full_name') or user_email,
		            'user_image': user_info.get('user_image'),
		            'email': user_email,
		            'name': user_email
		        },
		        'indent': 0,
		        'expandable': direct_user_totals or len(projects_result) > 0,
		        '_isUser': True,
		        '_detailsLoaded': return_project_rows,
		        '_email': user_email,
		        '_workingHours': user_daily_hours.get(user_email, {}),
		        '_absences': user_absences.get(user_email, []),
		        '_userHolidays': holiday_lists_cache.get(user_info.get('wholiday_list', ''), [])
		    }
		
		    # Добавляем нагрузку по периодам
		    user_total_sum = 0.0
		    for period in periods:
		        period_key = period['key']
		        hours = user_total.get(period_key, 0.0)
		        user_row[period_key] = "%.1f" % hours
		        user_total_sum = user_total_sum + hours
		
		    user_row['workload_total'] = "%.1f" % user_total_sum
		    if return_user_rows:
		        tree_data.append(user_row)
		
		    # Строки проектов для этого пользователя
		    project_names_result.sort()
		    for project_name in project_names_result:
		        if not return_project_rows:
		            continue
		        period_hours = projects_result[project_name]
		        project_info = projects_data.get(project_name, {})
		        if not project_info:
		            # Если проект не найден в projects_data, создаем базовую запись
		            project_info = {
		                'project_name': project_name,
		                'holiday_list': None
		            }
		
		        project_row = {
		            'participant': user_email,
		            'user_data': user_row['user_data'],
		            'project': project_info.get('project_name') or project_name,
		            'project_name': project_name,
		            'indent': 1,
		            'expandable': False,
		            '_isProject': True,
		            '_email': user_email,
		            '_project': project_name,
		            '_workingHours': user_daily_hours.get(user_email, {}),
		            '_absences': user_absences.get(user_email, []),
		            '_projectHolidays': holiday_lists_cache.get(project_info.get('holiday_list', ''), [])
		        }
		
		        project_total = 0.0
		        for period in periods:
		            period_key = period['key']
		            hours = period_hours.get(period_key, 0.0)
		            project_row[period_key] = "%.1f" % hours
		            project_total = project_total + hours
		
		        project_row['workload_total'] = "%.1f" % project_total
		        tree_data.append(project_row)
		perf_end("Build tree_data response", perf_section_start, "mode=" + str(mode) + ", users=" + str(len(user_emails_result)) + ", rows=" + str(len(tree_data)))
		perf_end("TOTAL get_projects_workload_data_v2", PERF_TOTAL_START, "mode=" + str(mode) + ", tree_rows=" + str(len(tree_data)) + ", periods=" + str(len(periods)) + ", assignments=" + str(len(assignments)))
		frappe.log_error("\n".join(PERF_TRACE), "PWR V2 PERF get_projects_workload_data_v2")
		
		# ========== 8. ФИНАЛЬНЫЙ ОТВЕТ ==========
		
		return  {
		    'tree_data': tree_data,
		    'periods': periods,
		    'users_count': len(users_list),
		    'projects_count': len(projects_list),
		    'assignments_count': len(assignments),
		    'mode': mode,
		    'limit': limit,
		    'offset': offset,
		    'next_offset': next_offset,
		    'has_more': has_more,
		    'total_users': total_users,
		    'message': 'Data loaded successfully in ' + str(int(calculation_time)) + ' ms (CORRECTED LOGIC V2)',
		    'performance': {
		        'calculation_time_ms': calculation_time,
		        'assignments': len(assignments),
		        'date_calculations': assignment_calculations,
		        'working_day_cache_size': len(working_day_cache),
		        'trace': PERF_TRACE
		    }
		}
	except Exception as e:
		try:
			perf_end("TOTAL get_projects_workload_data_v2 FAILED", PERF_TOTAL_START, "error=" + str(e))
		except Exception:
			pass
		frappe.log_error("\n".join(PERF_TRACE), "PWR V2 PERF get_projects_workload_data_v2 FAILED")
		frappe.log("Error in get_projects_workload_data_v2: " + str(e))
		return {
			"tree_data": [],
			"periods": [],
			"users_count": 0,
			"projects_count": 0,
			"assignments_count": 0,
			"mode": fd.get("mode", "full"),
			"error": str(e),
			"message": "Error loading data",
		}
