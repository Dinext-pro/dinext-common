# Copyright (c) 2026, Dinext
"""Дерево загрузки одного проекта: ответ API get_project_workload_data (бывший Server Script V3)."""

import frappe

from dinext_common.dinext_common.project_workload.assignments import (
	fetch_project_assignments_with_worker_context,
)


def run_get_project_workload_data(fd):
	"""fd — dict или объект с .get как frappe._dict."""
	if fd is None:
		fd = {}

	def logger(message):
		pass

	try:
		# Получаем параметры
		project = fd.get('project')
		view_type = fd.get('view_type', 'daily')
		date_from = fd.get('date_from')
		date_to = fd.get('date_to')
		
		logger(f"Project: {project}, View Type: {view_type}, Period: {date_from} to {date_to}")
		
		if not project:
		    return {
		        'tree_data': [], 
		        'periods': [],
		        'users_count': 0,
		        'tasks_count': 0,
		        'assignments_count': 0,
		        'message': 'No project specified'
		    }
		
		# ========== 1. ОПТИМИЗИРОВАННОЕ ПОЛУЧЕНИЕ ДАННЫХ ПРОЕКТА ==========
		
		project_data = frappe.db.get_value('Project', project, 
		    ['expected_start_date', 'expected_end_date', 'holiday_list'], as_dict=True)
		
		if not project_data:
		    return {
		        'tree_data': [], 
		        'periods': [],
		        'users_count': 0,
		        'tasks_count': 0,
		        'assignments_count': 0,
		        'message': 'Project not found'
		    }
		
		project_data = frappe._dict(project_data)
		project_start_date = project_data.expected_start_date or frappe.utils.nowdate()
		project_end_date = project_data.expected_end_date or frappe.utils.add_days(project_start_date, 90)
		project_holiday_list = project_data.holiday_list
		
		logger(f"Project dates - Start: {project_start_date}, End: {project_end_date}, Holiday List: {project_holiday_list}")
		
		# ========== 2. ОПРЕДЕЛЕНИЕ ПЕРИОДА ОТОБРАЖЕНИЯ ==========
		
		# Если даты не указаны, используем текущую дату и +1 месяц
		if not date_from:
		    date_from = frappe.utils.nowdate()
		
		if not date_to:
		    date_to = frappe.utils.add_months(date_from, 1)
		    # Если дата окончания проекта раньше, используем ее
		    if project_end_date and project_end_date < date_to:
		        date_to = project_end_date
		
		# Преобразуем строки в даты
		start_date_obj = frappe.utils.getdate(date_from)
		end_date_obj = frappe.utils.getdate(date_to)
		
		# Проверяем корректность диапазона
		if start_date_obj > end_date_obj:
		    # Меняем местами если нужно
		    start_date_obj, end_date_obj = end_date_obj, start_date_obj
		    date_from, date_to = date_to, date_from
		
		# Ограничиваем максимальный период (макс 365 дней для производительности)
		max_days = min(365, (end_date_obj - start_date_obj).days + 1)
		if max_days < 1:
		    return {
		        'tree_data': [], 
		        'periods': [],
		        'users_count': 0,
		        'tasks_count': 0,
		        'assignments_count': 0,
		        'message': 'Invalid date range'
		    }
		
		logger(f"Display period - From: {date_from}, To: {date_to}, Days: {max_days}")
		
		# ========== 3. НАЗНАЧЕНИЯ: общая выборка dinext_common (ISS-2026-00865 этап II) ==========
		
		assignments_data = fetch_project_assignments_with_worker_context(project, str(date_from), str(date_to))
		if assignments_data is None:
		    assignments_data = []
		assignments_data = [frappe._dict(a) for a in assignments_data]
		
		if not assignments_data:
		    return {
		        'tree_data': [], 
		        'periods': [],
		        'users_count': 0,
		        'tasks_count': 0,
		        'assignments_count': 0,
		        'message': 'No assignments found for project'
		    }
		
		logger(f"Found {len(assignments_data)} assignments")
		
		# ========== 4. НОВАЯ ТРЕХУРОВНЕВАЯ ГРУППИРОВКА (ПОЛЬЗОВАТЕЛЬ -> РОЛЬ -> ЗАДАЧА) ==========
		
		assignments_by_user_role_task = {}
		users_data = {}
		unique_tasks = set()
		
		logger(f"Начинаем группировку {len(assignments_data)} назначений по пользователям, ролям и задачам")
		
		for assignment in assignments_data:
		    user_email = assignment.user
		    role = assignment.role or 'No Role'
		    task_id = assignment.task_id
		    task_subject = assignment.task_subject or f"Задача {task_id}"
		
		    # Сохраняем данные пользователя
		    if user_email not in users_data:
		        users_data[user_email] = {
		            'full_name': assignment.full_name or user_email,
		            'user_image': assignment.user_image,
		            'email': user_email,
		            'name': user_email,
		            'wholiday_list': assignment.wholiday_list,
		            'wtimesheet_template': assignment.wtimesheet_template,
		            'hours_on_date': assignment.hours_on_date,
		            'tt_working_hours_on_date': assignment.tt_working_hours_on_date
		        }
		        logger(f"Добавлен пользователь: {user_email}")
		
		    # Трехуровневая структура: пользователь -> роль -> задача
		    if user_email not in assignments_by_user_role_task:
		        assignments_by_user_role_task[user_email] = {}
		
		    if role not in assignments_by_user_role_task[user_email]:
		        assignments_by_user_role_task[user_email][role] = {}
		
		    if task_id not in assignments_by_user_role_task[user_email][role]:
		        assignments_by_user_role_task[user_email][role][task_id] = {
		            'task_subject': task_subject,
		            'assignments': []
		        }
		
		    assignments_by_user_role_task[user_email][role][task_id]['assignments'].append(assignment)
		    unique_tasks.add(task_id)
		
		users_list = list(users_data.keys())
		logger(f"Группировка завершена. Пользователей: {len(users_list)}, задач: {len(unique_tasks)}")
		
		# ========== 4.5 ПОЛУЧЕНИЕ ДЕРЕВА ЗАДАЧ ПРОЕКТА (через frappe.qb) ==========
		
		Task = frappe.qb.DocType("Task")
		
		tasks_query = (
		    frappe.qb.from_(Task)
		    .select(
		        Task.name.as_("task_id"),
		        Task.subject.as_("task_subject"),
		        Task.parent_task.as_("parent_task_id"),
		        Task.status,
		        Task.exp_start_date,
		        Task.exp_end_date
		    )
		    .where(Task.project == project)
		    .orderby(Task.lft)
		)
		
		all_tasks = tasks_query.run(as_dict=True)
		logger(f"Найдено задач в проекте: {len(all_tasks)}")
		
		# Строим словарь задач для быстрого доступа
		tasks_dict = {}
		for task in all_tasks:
		    tasks_dict[task.task_id] = {
		        'task_id': task.task_id,
		        'task_subject': task.task_subject,
		        'parent_task_id': task.parent_task_id,
		        'children': [],
		        'has_direct_load': False  # Будет установлено позже
		    }
		
		# Строим иерархию (заполняем children)
		root_tasks = []
		for task_id, task_info in tasks_dict.items():
		    parent_id = task_info['parent_task_id']
		    if parent_id and parent_id in tasks_dict:
		        tasks_dict[parent_id]['children'].append(task_id)
		    else:
		        root_tasks.append(task_id)
		
		logger(f"Построено дерево задач. Корневых задач: {len(root_tasks)}")
		
		# Определяем, у каких задач есть прямая загрузка (назначения)
		tasks_with_direct_load = set()
		for assignment in assignments_data:
		    tasks_with_direct_load.add(assignment.task_id)
		
		for task_id in tasks_with_direct_load:
		    if task_id in tasks_dict:
		        tasks_dict[task_id]['has_direct_load'] = True
		
		logger(f"Задач с прямой загрузкой: {len(tasks_with_direct_load)}")
		
		# ========== 5. ОПТИМИЗИРОВАННАЯ ГЕНЕРАЦИЯ ПЕРИОДОВ (КАК В РЕФЕРЕНСЕ) ==========
		
		periods = []
		
		if view_type == 'daily':
		    current_date = start_date_obj
		    # Ограничиваем количество периодов для оптимизации (макс 365 дней)
		    for i in range(max_days):
		        if current_date > end_date_obj:
		            break
		
		        date_str = str(current_date)
		        periods.append({
		            'key': 'workload_' + date_str,
		            'date': date_str,
		            'year': current_date.year,
		            'month': current_date.month,
		            'day': current_date.day,
		            'weekday': current_date.weekday()
		        })
		        current_date = frappe.utils.add_days(current_date, 1)
		
		elif view_type == 'weekly':
		    # Генерация недельных периодов КАК В РЕФЕРЕНСЕ
		    # Находим начало недели (понедельник) ОТНОСИТЕЛЬНО ТЕКУЩЕЙ ДАТЫ
		    current_date = start_date_obj
		    days_to_monday = current_date.weekday()  # weekday: 0 = Monday, 6 = Sunday
		    week_start = frappe.utils.add_days(current_date, -days_to_monday)
		
		    # Считаем количество недель, которое нужно отобразить
		    # Определяем количество полных недель от week_start до end_date_obj
		    days_diff = (end_date_obj - week_start).days
		    weeks_count = (days_diff // 7) + 1
		
		    for i in range(weeks_count):
		        week_start_date = frappe.utils.add_days(week_start, i * 7)
		        week_end_date = frappe.utils.add_days(week_start_date, 6)  # Воскресенье
		
		        # ВАЖНО: Всегда добавляем ПОЛНУЮ неделю, даже если она начинается до start_date_obj
		        # Это обеспечит правильный расчет для дней в прошлом (9.03 и 10.03)
		        periods.append({
		            'key': f"workload_{week_start_date.year}-W{week_start_date.isocalendar()[1]:02d}",
		            'date': str(week_start_date),  # Для обратной совместимости
		            'start_date': str(week_start_date),
		            'end_date': str(week_end_date),
		            'year': week_start_date.year,
		            'week': week_start_date.isocalendar()[1],
		            'week_start': str(week_start_date),
		            'week_end': str(week_end_date)
		        })
		
		        # Безопасность: ограничиваем количество недель
		        if len(periods) > 156:  # ~3 года
		            break
		
		elif view_type == 'monthly':
		    # Генерация месячных периодов
		    current_date = start_date_obj
		
		    # Находим первый день месяца для начальной даты
		    month_start = frappe.utils.getdate(f"{current_date.year}-{current_date.month:02d}-01")
		
		    # Генерируем месяцы пока не достигнем end_date_obj
		    while month_start <= end_date_obj:
		        month_end = frappe.utils.get_last_day(month_start)
		
		        # ВАЖНО: Всегда добавляем ПОЛНЫЙ месяц
		        periods.append({
		            'key': f"workload_{month_start.year}-{month_start.month:02d}",
		            'date': str(month_start),
		            'start_date': str(month_start),
		            'end_date': str(month_end),
		            'year': month_start.year,
		            'month': month_start.month,
		            'month_start': str(month_start),
		            'month_end': str(month_end)
		        })
		
		        # Переходим к следующему месяцу
		        if month_start.month == 12:
		            month_start = frappe.utils.getdate(f"{month_start.year + 1}-01-01")
		        else:
		            month_start = frappe.utils.getdate(f"{month_start.year}-{month_start.month + 1:02d}-01")
		
		        # Безопасность: ограничиваем количество месяцев
		        if len(periods) > 60:  # 5 лет
		            break
		
		logger(f"Generated {len(periods)} periods for {view_type} view")
		
		# ========== 6. ОПТИМИЗИРОВАННАЯ ЗАГРУЗКА ДОПОЛНИТЕЛЬНЫХ ДАННЫХ ==========
		
		# 6.1 Рабочие часы пользователей (загружаем одним запросом через frappe.qb)
		working_hours_overrides = {}
		override_refs = set()
		
		for user_email, user_info in users_data.items():
		    if user_info.get('tt_working_hours_on_date'):
		        override_refs.add(user_info['tt_working_hours_on_date'])
		
		if override_refs:
		    WorkingHoursTable = frappe.qb.DocType("Working Hours Table")
		
		    overrides_query = (
		        frappe.qb.from_(WorkingHoursTable)
		        .select(
		            WorkingHoursTable.parent.as_("ref_name"),
		            WorkingHoursTable.wht_date,
		            WorkingHoursTable.wht_hours
		        )
		        .where(WorkingHoursTable.parent.isin(list(override_refs)))
		        .where(WorkingHoursTable.parentfield == "hod_working_hours_table")
		        .where(WorkingHoursTable.parenttype == "Working Hours On Date")
		    )
		
		    overrides = overrides_query.run(as_dict=True)
		    for row in overrides:
		        if row.ref_name not in working_hours_overrides:
		            working_hours_overrides[row.ref_name] = {}
		        if row.wht_date:
		            working_hours_overrides[row.ref_name][str(row.wht_date)] = float(row.wht_hours or 0)
		
		# 6.2 Holiday Lists (загружаем одним запросом через frappe.qb)
		holiday_lists_cache = {}
		all_holiday_lists = set()
		
		# Добавляем holiday list проекта
		if project_holiday_list:
		    all_holiday_lists.add(project_holiday_list)
		
		# Добавляем holiday lists пользователей
		for user_info in users_data.values():
		    if user_info.get('wholiday_list'):
		        all_holiday_lists.add(user_info['wholiday_list'])
		
		if all_holiday_lists:
		    Holiday = frappe.qb.DocType("Holiday")
		
		    holidays_query = (
		        frappe.qb.from_(Holiday)
		        .select(
		            Holiday.parent.as_("list_name"),
		            Holiday.holiday_date,
		            Holiday.description,
		            Holiday.weekly_off
		        )
		        .where(Holiday.parent.isin(list(all_holiday_lists)))
		        .where(Holiday.parentfield == "holidays")
		        .where(Holiday.parenttype == "Holiday List")
		        .where(Holiday.holiday_date >= date_from)
		        .where(Holiday.holiday_date <= date_to)
		        .orderby(Holiday.parent, Holiday.holiday_date)
		    )
		
		    holidays = holidays_query.run(as_dict=True)
		    for row in holidays:
		        if row.list_name not in holiday_lists_cache:
		            holiday_lists_cache[row.list_name] = []
		
		        holiday_lists_cache[row.list_name].append({
		            'date': str(row.holiday_date),
		            'description': row.description,
		            'weekly_off': row.weekly_off
		        })
		
		# 6.3 Отсутствия (загружаем одним запросом через frappe.qb)
		user_absences = {}
		if users_list:
		    ApplicationForLeave = frappe.qb.DocType("Application For Leave")
		
		    absences_query = (
		        frappe.qb.from_(ApplicationForLeave)
		        .select(
		            ApplicationForLeave.lauser,
		            ApplicationForLeave.alfrom_date,
		            ApplicationForLeave.alto_date,
		            ApplicationForLeave.altype_of_leave,
		            ApplicationForLeave.alfrom_hours,
		            ApplicationForLeave.alto_hours
		        )
		        .where(ApplicationForLeave.lauser.isin(users_list))
		        .where(ApplicationForLeave.status == "Согласовано")
		        .where(ApplicationForLeave.alfrom_date.isnotnull())
		        .where(ApplicationForLeave.alto_date.isnotnull())
		        .where(ApplicationForLeave.alto_date >= date_from)
		        .where(ApplicationForLeave.alfrom_date <= date_to)
		        .orderby(ApplicationForLeave.lauser, ApplicationForLeave.alfrom_date)
		    )
		
		    absences = absences_query.run(as_dict=True)
		    for absence in absences:
		        user_email = absence.lauser
		        if user_email not in user_absences:
		            user_absences[user_email] = []
		
		        user_absences[user_email].append({
		            'from_date': absence.alfrom_date,
		            'to_date': absence.alto_date,
		            'type': absence.altype_of_leave,
		            'alfrom_hours': absence.alfrom_hours,
		            'alto_hours': absence.alto_hours
		        })
		
		logger(f"Loaded {sum(len(v) for v in user_absences.values())} absence records")
		
		# 6.4 Плановые часы (Project Work Efforts) - ДЛЯ ТИПА 3 (через frappe.qb)
		monthly_plan_cache = {}
		
		# Собираем уникальные task+role для запроса плановых часов
		task_role_set = set()
		for user_email, roles in assignments_by_user_role_task.items():
		    for role, tasks in roles.items():
		        for task_id, task_data in tasks.items():
		            for assignment in task_data['assignments']:
		                if assignment.task_id and assignment.role:
		                    task_role_set.add((assignment.task_id, assignment.role))
		
		if task_role_set:
		    # Определяем DocType'ы
		    PWE = frappe.qb.DocType("Project Work Efforts")
		    PWEA = frappe.qb.DocType("Project Work Efforts Amount")
		
		    # Строим условия для OR между разными (task, role)
		    conditions = []
		    for task_id, role in task_role_set:
		        conditions.append(
		            (PWE.pwe_task == task_id) & (PWE.pwe_project_role == role)
		        )
		
		    if conditions:
		        # Объединяем все условия через OR
		        final_condition = conditions[0]
		        for cond in conditions[1:]:
		            final_condition = final_condition | cond
		
		        # Строим запрос
		        efforts_query = (
		            frappe.qb.from_(PWE)
		            .inner_join(PWEA)
		            .on(PWEA.parent == PWE.name)
		            .select(
		                PWE.pwe_task.as_("task"),
		                PWE.pwe_project_role.as_("role"),
		                PWEA.pwea_year.as_("year"),
		                PWEA.pwea_month.as_("month"),
		                PWEA.pwea_plan.as_("plan_hours")
		            )
		            .where(final_condition)
		            .where(PWEA.pwea_plan > 0)
		        )
		
		        plans = efforts_query.run(as_dict=True)
		        for plan in plans:
		            key = f"{plan.task}_{plan.role}_{plan.year}_{plan.month}"
		            monthly_plan_cache[key] = float(plan.plan_hours or 0)
		
		        logger(f"Loaded {len(plans)} monthly plan records")
		
		# ========== 7. ОПТИМИЗИРОВАННЫЕ ПРЕДВАРИТЕЛЬНЫЕ ВЫЧИСЛЕНИЯ ==========
		
		# 7.1 Кэш рабочих часов пользователей по дням
		user_daily_hours = {}
		for user_email, user_info in users_data.items():
		    base_hours = float(user_info.get('hours_on_date') or 8.0)
		    working_hours_ref = user_info.get('tt_working_hours_on_date')
		    override_dict = working_hours_overrides.get(working_hours_ref, {}) if working_hours_ref else {}
		
		    hours_dict = {}
		    for period in periods:
		        date_str = period['date']
		        hours_on_date = override_dict.get(date_str, base_hours)
		        hours_dict[date_str] = hours_on_date
		
		    user_daily_hours[user_email] = hours_dict
		
		# 7.2 Создаем быстрые lookup-таблицы для праздников
		project_holidays_set = set()
		project_weekly_off_set = set()
		
		if project_holiday_list and project_holiday_list in holiday_lists_cache:
		    for h in holiday_lists_cache[project_holiday_list]:
		        project_holidays_set.add(h['date'])
		        if h.get('weekly_off'):
		            project_weekly_off_set.add(h['date'])
		
		user_holidays_cache = {}
		user_weekly_off_cache = {}
		
		for user_email, user_info in users_data.items():
		    holiday_list = user_info.get('wholiday_list')
		    user_holidays = set()
		    user_weekly_off = set()
		
		    if holiday_list and holiday_list in holiday_lists_cache:
		        for h in holiday_lists_cache[holiday_list]:
		            user_holidays.add(h['date'])
		            if h.get('weekly_off'):
		                user_weekly_off.add(h['date'])
		
		    user_holidays_cache[user_email] = user_holidays
		    user_weekly_off_cache[user_email] = user_weekly_off
		
		# ========== 7.2.1 ПОДГОТОВКА USER_HOLIDAYS ДЛЯ КЛИЕНТА ==========
		
		# Подготавливаем holidays для каждого пользователя
		user_holidays_for_client = {}
		for user_email in users_list:
		    user_holidays_for_client[user_email] = []
		    if user_email in user_holidays_cache:
		        for date in user_holidays_cache[user_email]:
		            user_holidays_for_client[user_email].append({
		                'date': date,
		                'weekly_off': date in user_weekly_off_cache.get(user_email, set())
		            })
		
		logger(f"Prepared user holidays for {len(user_holidays_for_client)} users")
		
		# 7.3 Создаем быстрые lookup-таблицы для отсутствий
		user_absence_cache = {}
		for user_email, absences in user_absences.items():
		    absence_dict = {}
		    for absence in absences:
		        start = frappe.utils.getdate(absence['from_date'])
		        end = frappe.utils.getdate(absence['to_date'])
		        current = start
		        while current <= end:
		            date_str = str(current)
		            if date_str not in absence_dict:
		                absence_dict[date_str] = []
		            absence_dict[date_str].append(absence)
		            current = frappe.utils.add_days(current, 1)
		    user_absence_cache[user_email] = absence_dict
		
		# ========== 8. ОПТИМИЗИРОВАННЫЙ РАСЧЕТ НАГРУЗКИ (С ИЕРАРХИЕЙ ЗАДАЧ) ==========
		
		logger("Starting workload calculation with TASK HIERARCHY...")
		start_time = frappe.utils.now_datetime()
		
		# Результаты: user -> role -> period_key -> hours
		results = {}
		# Результаты по задачам: task_key (user_role_task) -> period_key -> hours
		task_results = {}
		# Результаты по задачам с учетом иерархии (будем заполнять после аккумуляции)
		hierarchical_task_results = {}
		
		workload_calculations = 0
		
		# Создаем lookup для быстрого доступа к периодам по дате
		period_by_date = {p['date']: p for p in periods}
		
		date_to_period_key = {}
		
		if view_type == 'daily':
		    # Для дней - прямая связь
		    for period in periods:
		        date_to_period_key[period['date']] = period['key']
		else:
		    # Для недель/месяцев - все даты в диапазоне маппятся на соответствующий период
		    for period in periods:
		        start = frappe.utils.getdate(period['start_date'])
		        end = frappe.utils.getdate(period['end_date'])
		        current = start
		        while current <= end:
		            date_str = str(current)
		            date_to_period_key[date_str] = period['key']
		            current = frappe.utils.add_days(current, 1)
		
		# Вспомогательная функция для проверки рабочего дня
		def is_working_day_optimized(date_str, user_email):
		    """Оптимизированная проверка рабочего дня"""
		    # 1. Праздничный календарь проекта: weekly_off — нерабочий день; прочие праздники — нерабочие.
		    if date_str in project_weekly_off_set:
		        return False
		    if date_str in project_holidays_set and date_str not in project_weekly_off_set:
		        return False
		    
		    # 2. Календарь пользователя (Worker.wholiday_list): та же логика.
		    user_holidays = user_holidays_cache.get(user_email, set())
		    user_weekly_off = user_weekly_off_cache.get(user_email, set())
		    if date_str in user_weekly_off:
		        return False
		    if date_str in user_holidays and date_str not in user_weekly_off:
		        return False
		
		    # 3. Проверка полных отсутствий
		    if date_str in user_absence_cache.get(user_email, {}):
		        absence_list = user_absence_cache[user_email][date_str]
		        user_base_hours = user_daily_hours.get(user_email, {}).get(date_str, 8.0)
		
		        for absence in absence_list:
		            absence_date = frappe.utils.getdate(date_str)
		            from_date = frappe.utils.getdate(absence['from_date'])
		            to_date = frappe.utils.getdate(absence['to_date'])
		
		            absence_hours = 0.0
		            if absence_date == from_date:
		                absence_hours = float(absence.get('alfrom_hours') or 0)
		            elif absence_date == to_date:
		                absence_hours = float(absence.get('alto_hours') or 0)
		            else:
		                absence_hours = user_base_hours
		
		            if absence_hours >= user_base_hours:
		                return False
		
		    return True
		
		# Вспомогательная функция для расчета доступных часов
		def get_available_hours(date_str, user_email):
		    """Расчет доступных часов"""
		    if not is_working_day_optimized(date_str, user_email):
		        return 0.0
		
		    user_base_hours = user_daily_hours.get(user_email, {}).get(date_str, 8.0)
		
		    # Учитываем частичные отсутствия
		    if date_str in user_absence_cache.get(user_email, {}):
		        absence_list = user_absence_cache[user_email][date_str]
		        for absence in absence_list:
		            absence_date = frappe.utils.getdate(date_str)
		            from_date = frappe.utils.getdate(absence['from_date'])
		            to_date = frappe.utils.getdate(absence['to_date'])
		
		            if absence_date == from_date:
		                absence_hours = float(absence.get('alfrom_hours') or 0)
		                return max(0, user_base_hours - absence_hours)
		            elif absence_date == to_date:
		                absence_hours = float(absence.get('alto_hours') or 0)
		                return max(0, user_base_hours - absence_hours)
		
		    return user_base_hours
		
		# Кэш рабочих дней в месяце для оптимизации (больше не используется)
		# month_working_days_cache = {}  # ← УДАЛЕНО
		
		# ШАГ 1: Рассчитываем нагрузку для всех назначений (прямые назначения)
		for user_email, roles in assignments_by_user_role_task.items():
		
		    for role, tasks in roles.items():
		        # Инициализируем структуру для этой роли
		        if user_email not in results:
		            results[user_email] = {}
		
		        if role not in results[user_email]:
		            results[user_email][role] = {p['key']: 0.0 for p in periods}
		
		        role_result = results[user_email][role]
		
		        # Обрабатываем все задачи этой роли
		        for task_id, task_data in tasks.items():
		            # Создаем уникальный ключ для задачи
		            task_key = f"{user_email}_{role}_{task_id}"
		
		            # Инициализируем структуру для этой задачи
		            if task_key not in task_results:
		                task_results[task_key] = {p['key']: 0.0 for p in periods}
		
		            task_result = task_results[task_key]
		
		            for assignment in task_data['assignments']:
		                # Берем ПОЛНЫЙ период назначения, без обрезки периодом отображения
		                assignment_date_from = frappe.utils.getdate(assignment.date_from)
		                assignment_date_to = frappe.utils.getdate(assignment.date_to)
		
		                # Тип 1: В рабочих часах
		                if assignment.workload == 'В рабочих часах':
		                    total_assignment_hours = float(assignment.wl_value or 0)
		
		                    # Рассчитываем общие доступные часы во всем периоде назначения
		                    total_available_in_period = 0.0
		                    date_available_hours = {}
		
		                    current_date = assignment_date_from
		                    while current_date <= assignment_date_to:
		                        date_str = str(current_date)
		
		                        available_hours = get_available_hours(date_str, user_email)
		                        if available_hours > 0:
		                            total_available_in_period = total_available_in_period + available_hours
		                            date_available_hours[date_str] = available_hours
		                            workload_calculations = workload_calculations + 1
		
		                        current_date = frappe.utils.add_days(current_date, 1)
		
		                    if total_available_in_period > 0:
		                        # Распределяем нагрузку пропорционально доступным часам
		                        for date_str, available_hours_on_date in date_available_hours.items():
		                            if available_hours_on_date > 0:
		                                # Определяем период для этой даты
		                                target_date = frappe.utils.getdate(date_str)
		                                period_key = date_to_period_key.get(date_str)
		
		                                # Если дата не попадает ни в один период - пропускаем
		                                if not period_key:
		                                    continue
		
		                                daily_ratio = available_hours_on_date / total_available_in_period
		                                daily_hours = total_assignment_hours * daily_ratio
		
		                                # Добавляем к результатам роли
		                                role_result[period_key] = role_result.get(period_key, 0.0) + daily_hours
		
		                                # Добавляем к результатам задачи
		                                task_result[period_key] = task_result.get(period_key, 0.0) + daily_hours
		
		                # Тип 2: В % от фонда рабочих часов
		                elif assignment.workload == 'В % от фонда рабочих часов':
		                    percentage_value = float(assignment.wl_value or 0) / 100
		
		                    current_date = assignment_date_from
		                    while current_date <= assignment_date_to:
		                        date_str = str(current_date)
		
		                        available_hours = get_available_hours(date_str, user_email)
		                        if available_hours > 0:
		                            # Определяем период для этой даты
		                            target_date = frappe.utils.getdate(date_str)
		                            period_key = date_to_period_key.get(date_str)
		
		                            if period_key:
		                                daily_load = percentage_value * available_hours
		                                workload_calculations = workload_calculations + 1
		
		                                # Добавляем к результатам роли
		                                role_result[period_key] = role_result.get(period_key, 0.0) + daily_load
		
		                                # Добавляем к результатам задачи
		                                task_result[period_key] = task_result.get(period_key, 0.0) + daily_load
		
		                        current_date = frappe.utils.add_days(current_date, 1)
		
		                # Тип 3: В % от трудоемкости задачи (КАК В РЕФЕРЕНСЕ)
		                elif assignment.workload == 'В % от трудоемкости задачи':
		                    percentage_value = float(assignment.wl_value or 0) / 100
		
		                    task = assignment.task_id
		                    role_name = assignment.role
		
		                    # Группируем даты по месяцам в периоде назначения (КАК В РЕФЕРЕНСЕ)
		                    months_in_period = {}
		
		                    current_date = assignment_date_from
		                    while current_date <= assignment_date_to:
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
		
		                        # Проверяем, является ли день рабочим для пользователя (ТОЛЬКО в периоде назначения)
		                        if is_working_day_optimized(date_str, user_email):
		                            months_in_period[month_key]['working_days'] = months_in_period[month_key]['working_days'] + 1
		
		                        current_date = frappe.utils.add_days(current_date, 1)
		
		                    # Обрабатываем каждый месяц отдельно (КАК В РЕФЕРЕНСЕ)
		                    for month_key, month_info in months_in_period.items():
		                        year = month_info['year']
		                        month = month_info['month']
		                        plan_key = task + "_" + role_name + "_" + str(year) + "_" + str(month)
		
		                        if plan_key in monthly_plan_cache:
		                            monthly_plan_hours = monthly_plan_cache[plan_key]
		
		                            if monthly_plan_hours > 0 and month_info['working_days'] > 0:
		                                # База = плановые часы / рабочие дни ТОЛЬКО в периоде назначения (КАК В РЕФЕРЕНСЕ)
		                                base_daily_hours = monthly_plan_hours / month_info['working_days']
		
		                                # Распределяем нагрузку только на рабочие дни в этом месяце (КАК В РЕФЕРЕНСЕ)
		                                for date_str in month_info['dates']:
		                                    if is_working_day_optimized(date_str, user_email):
		                                        # Определяем период для этой даты
		                                        target_date = frappe.utils.getdate(date_str)
		                                        period_key = date_to_period_key.get(date_str)
		
		                                        if period_key:
		                                            daily_load = percentage_value * base_daily_hours
		
		                                            # Добавляем к результатам роли
		                                            role_result[period_key] = role_result.get(period_key, 0.0) + daily_load
		
		                                            # Добавляем к результатам задачи
		                                            task_result[period_key] = task_result.get(period_key, 0.0) + daily_load
		
		                                            workload_calculations = workload_calculations + 1
		
		                                current_date = frappe.utils.add_days(current_date, 1)
		
		# ШАГ 2: Аккумуляция нагрузки в иерархии задач
		logger("Starting task hierarchy accumulation...")
		
		# Копируем прямые результаты в иерархические
		hierarchical_task_results = task_results.copy()
		
		# Функция для рекурсивного сбора нагрузки от дочерних задач
		def accumulate_child_load(task_id, role, user_email, period_keys):
		    """Собирает нагрузку от всех дочерних задач для указанной роли и пользователя"""
		    if task_id not in tasks_dict:
		        return {key: 0.0 for key in period_keys}
		
		    task_info = tasks_dict[task_id]
		    accumulated = {key: 0.0 for key in period_keys}
		
		    # Если у задачи есть прямая загрузка, не аккумулируем от детей
		    if task_info['has_direct_load']:
		        return accumulated
		
		    # Рекурсивно собираем нагрузку от всех детей
		    for child_id in task_info['children']:
		        child_key = f"{user_email}_{role}_{child_id}"
		
		        # Добавляем прямую нагрузку ребенка (если есть)
		        if child_key in task_results:
		            child_load = task_results[child_key]
		            for key in period_keys:
		                accumulated[key] = accumulated.get(key, 0.0) + child_load.get(key, 0.0)
		
		        # Рекурсивно добавляем нагрузку от внуков
		        child_accumulated = accumulate_child_load(child_id, role, user_email, period_keys)
		        for key in period_keys:
		            accumulated[key] = accumulated.get(key, 0.0) + child_accumulated.get(key, 0.0)
		
		    return accumulated
		
		# Применяем аккумуляцию для ВСЕХ релевантных задач (включая родителей)
		period_keys = [p['key'] for p in periods]
		
		for user_email, roles in assignments_by_user_role_task.items():
		    for role, tasks in roles.items():
		        # Собираем ВСЕ task_id для этой роли, включая родителей
		        all_task_ids = set(tasks.keys())
		
		        # Добавляем всех родителей для каждой задачи
		        additional_parents = set()
		        for task_id in tasks.keys():
		            current_id = task_id
		            while current_id in tasks_dict and tasks_dict[current_id]['parent_task_id']:
		                parent_id = tasks_dict[current_id]['parent_task_id']
		                additional_parents.add(parent_id)
		                current_id = parent_id
		
		        all_task_ids.update(additional_parents)
		        logger(f"Роль {role}: задач с прямыми назначениями: {len(tasks.keys())}, всего задач в иерархии: {len(all_task_ids)}")
		
		        # Аккумулируем для каждой задачи в иерархии
		        for task_id in all_task_ids:
		            task_key = f"{user_email}_{role}_{task_id}"
		            task_info = tasks_dict.get(task_id, {})
		
		            # Если у задачи нет прямой загрузки, аккумулируем от детей
		            if not task_info.get('has_direct_load', False):
		                child_load = accumulate_child_load(task_id, role, user_email, period_keys)
		
		                # Обновляем результаты для этой задачи
		                if task_key not in hierarchical_task_results:
		                    hierarchical_task_results[task_key] = {key: 0.0 for key in period_keys}
		
		                for key in period_keys:
		                    hierarchical_task_results[task_key][key] = child_load.get(key, 0.0)
		
		                # Логируем для отладки
		                if any(child_load.values()):
		                    total = sum(child_load.values())
		                    logger(f"Аккумулировано {total:.1f} ч для задачи {task_info.get('task_subject', task_id)} (роль {role})")
		
		logger(f"Task hierarchy accumulation completed. Total task results: {len(hierarchical_task_results)}")
		
		end_time = frappe.utils.now_datetime()
		time_diff = end_time - start_time
		calculation_time = time_diff.total_seconds() * 1000
		
		logger(f"Calculation completed in {calculation_time:.2f} ms, {workload_calculations} calculations")
		
		# Логируем статистику по задачам для отладки
		logger(f"Task results calculated for {len(task_results)} tasks")
		
		# ========== 9. УДАЛЕН БЛОК ГАНТА ==========
		# Блок создания данных для Ганта полностью удален
		
		# ========== 10. ФОРМИРОВАНИЕ TREE DATA С ИЕРАРХИЕЙ ЗАДАЧ ==========
		
		tree_data = []
		
		# Функция для рекурсивного добавления задач в tree_data
		def add_task_to_tree(task_id, role, user_email, user_row_data, indent_level, parent_role_row):
		    """Рекурсивно добавляет задачу и всех её детей в tree_data"""
		    if task_id not in tasks_dict:
		        return
		
		    task_info = tasks_dict[task_id]
		    task_key = f"{user_email}_{role}_{task_id}"
		
		    # Получаем нагрузку для этой задачи (с учетом аккумуляции)
		    # Если у задачи есть прямая загрузка, используем её
		    # Если нет, используем аккумулированную от детей
		    if task_info['has_direct_load']:
		        # Если есть прямая загрузка, берем из task_results
		        task_periods = task_results.get(task_key, {})
		        logger(f"Задача {task_info['task_subject']}: используем прямую загрузку")
		    else:
		        # Если нет прямой загрузки, берем из hierarchical_task_results (аккумулированная)
		        task_periods = hierarchical_task_results.get(task_key, {})
		        if any(task_periods.values()):
		            total = sum(task_periods.values())
		            logger(f"Задача {task_info['task_subject']}: используем аккумулированную загрузку ({total:.1f} ч)")
		        else:
		            logger(f"Задача {task_info['task_subject']}: нет загрузки")
		
		    if not task_periods:
		        task_periods = {p['key']: 0.0 for p in periods}
		
		    # ФИЛЬТРАЦИЯ: Собираем только те дочерние задачи, у которых есть нагрузка для этой роли
		    children_with_load = []
		    if task_info['children']:
		        for child_id in task_info['children']:
		            child_key = f"{user_email}_{role}_{child_id}"
		
		            # Проверяем, есть ли у ребенка нагрузка (прямая или аккумулированная)
		            child_has_load = False
		
		            # Проверяем прямую нагрузку
		            if child_key in task_results and any(task_results[child_key].values()):
		                child_has_load = True
		            # Проверяем аккумулированную нагрузку
		            elif child_key in hierarchical_task_results and any(hierarchical_task_results[child_key].values()):
		                child_has_load = True
		            # Проверяем, есть ли у ребенка дети с нагрузкой (рекурсивно)
		            else:
		                child_info = tasks_dict.get(child_id, {})
		                if child_info.get('children'):
		                    # Быстрая проверка: есть ли хоть один потомок с нагрузкой
		                    for grandchild_id in child_info['children']:
		                        grandchild_key = f"{user_email}_{role}_{grandchild_id}"
		                        if grandchild_key in task_results and any(task_results[grandchild_key].values()):
		                            child_has_load = True
		                            break
		                        elif grandchild_key in hierarchical_task_results and any(hierarchical_task_results[grandchild_key].values()):
		                            child_has_load = True
		                            break
		
		            if child_has_load:
		                children_with_load.append(child_id)
		
		    # Если у задачи нет своей нагрузки и нет детей с нагрузкой - не показываем
		    has_own_load = any(task_periods.values())
		    if not has_own_load and not children_with_load:
		        return
		
		    # Создаем строку задачи
		    task_row = {
		        'participant': user_email,
		        'user_data': user_row_data,
		        'role': role,
		        'task_id': task_id,
		        'task_subject': task_info['task_subject'],
		        'indent': indent_level,
		        'expandable': len(children_with_load) > 0,  # Раскрываем только если есть дети с нагрузкой
		        'isTask': True,
		        'email': user_email,
		        'roleName': role,
		        'level': 'task',
		        'has_direct_load': task_info['has_direct_load']
		    }
		
		    # Данные задачи по периодам
		    task_total_hours = 0.0
		    for period in periods:
		        hours = task_periods.get(period['key'], 0.0)
		        task_row[period['key']] = f"{hours:.1f}"
		        task_total_hours = task_total_hours + hours
		
		    task_row['workload_total'] = f"{task_total_hours:.1f}"
		    tree_data.append(task_row)
		    logger(f"Добавлена задача: {task_info['task_subject']} (indent: {indent_level}, expandable: {len(children_with_load) > 0}, прямая загрузка: {task_info['has_direct_load']})")
		
		    # Рекурсивно добавляем только дочерние задачи с нагрузкой
		    if children_with_load:
		        for child_id in sorted(children_with_load):  # сортируем для стабильности
		            add_task_to_tree(child_id, role, user_email, user_row_data, indent_level + 1, parent_role_row)
		
		# Основной цикл по пользователям
		for user_email in users_list:
		    user_info = users_data[user_email]
		    user_roles = results.get(user_email, {})
		
		    # Строка пользователя (уровень 0)
		    user_row = {
		        'participant': user_email,
		        'user_data': {
		            'full_name': user_info['full_name'],
		            'user_image': user_info['user_image'],
		            'email': user_email
		        },
		        'indent': 0,
		        'expandable': len(user_roles) > 0,
		        'isUser': True,
		        'email': user_email,
		        'level': 'user'
		    }
		
		    # Общая нагрузка пользователя
		    user_total_hours = 0.0
		    for period in periods:
		        period_hours = 0.0
		        for role_data in user_roles.values():
		            period_hours = period_hours + role_data.get(period['key'], 0.0)
		
		        user_row[period['key']] = f"{period_hours:.1f}"
		        user_total_hours = user_total_hours + period_hours
		
		    user_row['workload_total'] = f"{user_total_hours:.1f}"
		    tree_data.append(user_row)
		    logger(f"Добавлен пользователь: {user_email}")
		
		    # Роли пользователя (уровень 1)
		    for role, role_data in user_roles.items():
		        # Находим ВСЕ задачи для этой роли, включая родительские
		        # Сначала собираем все task_id, которые есть в назначениях для этой роли
		        tasks_with_assignments = set(assignments_by_user_role_task.get(user_email, {}).get(role, {}).keys())
		
		        # Теперь нужно найти все родительские задачи, которые ведут к этим задачам
		        all_relevant_tasks = set(tasks_with_assignments)
		
		        # Для каждой задачи с назначением, добавляем всех её родителей
		        for task_id in tasks_with_assignments:
		            current_id = task_id
		            while current_id in tasks_dict and tasks_dict[current_id]['parent_task_id']:
		                parent_id = tasks_dict[current_id]['parent_task_id']
		                all_relevant_tasks.add(parent_id)
		                current_id = parent_id
		
		        logger(f"Роль {role}: задач с назначениями: {len(tasks_with_assignments)}, всего релевантных задач: {len(all_relevant_tasks)}")
		
		        # Если нет релевантных задач для этой роли, пропускаем роль
		        if not all_relevant_tasks:
		            continue
		
		        # Строка роли
		        role_row = {
		            'participant': user_email,
		            'user_data': user_row['user_data'],
		            'role': role,
		            'indent': 1,
		            'expandable': len(all_relevant_tasks) > 0,
		            'isRole': True,
		            'email': user_email,
		            'roleName': role,
		            'level': 'role'
		        }
		
		        # Нагрузка по роли
		        role_total_hours = 0.0
		        for period in periods:
		            hours = role_data.get(period['key'], 0.0)
		            role_row[period['key']] = f"{hours:.1f}"
		            role_total_hours = role_total_hours + hours
		
		        role_row['workload_total'] = f"{role_total_hours:.1f}"
		        tree_data.append(role_row)
		        logger(f"Добавлена роль: {role}")
		
		        # Находим корневые задачи для этой роли (те, у которых нет родителя или родитель не в all_relevant_tasks)
		        root_tasks_for_role = []
		        for task_id in all_relevant_tasks:
		            task_info = tasks_dict.get(task_id, {})
		            parent_id = task_info.get('parent_task_id')
		            # Если нет родителя или родитель не в нашем наборе релевантных задач - это корень
		            if not parent_id or parent_id not in all_relevant_tasks:
		                root_tasks_for_role.append(task_id)
		
		        # Сортируем корневые задачи для стабильного отображения
		        root_tasks_for_role.sort()
		        logger(f"Роль {role}: корневых задач: {len(root_tasks_for_role)} -> {[tasks_dict.get(t, {}).get('task_subject', t) for t in root_tasks_for_role]}")
		
		        # Рекурсивно добавляем задачи, начиная с корневых
		        for task_id in root_tasks_for_role:
		            add_task_to_tree(
		                task_id, 
		                role, 
		                user_email, 
		                user_row['user_data'], 
		                2,  # начальный отступ для задач
		                role_row
		            )
		
		logger(f"Generated tree data with {len(tree_data)} rows (including task hierarchy)")
		
		# ========== 11. ПОДГОТОВКА МЕТАДАННЫХ ==========
		
		# Подготавливаем праздники проекта для клиента
		project_holidays_for_client = []
		if project_holiday_list and project_holiday_list in holiday_lists_cache:
		    project_holidays_for_client = holiday_lists_cache[project_holiday_list]
		
		# ========== 12. ФИНАЛЬНЫЙ ОТВЕТ ==========
		
		return {
		    'tree_data': tree_data,
		    'task_results': task_results,           # ← добавить
		    'hierarchical_task_results': hierarchical_task_results,  # ← добавить
		    'periods': periods,
		    'users_count': len(users_list),
		    'tasks_count': len(unique_tasks),
		    'assignments_count': len(assignments_data),
		    'metadata': {
		        'project_holidays': project_holidays_for_client,
		        'user_holidays': user_holidays_for_client,
		        'user_absences': user_absences,
		        'user_daily_hours': user_daily_hours,
		        'monthly_plans_count': len(monthly_plan_cache),
		        'project_dates': {
		            'start_date': str(project_start_date),
		            'end_date': str(project_end_date)
		        },
		        'display_dates': {
		            'date_from': date_from,
		            'date_to': date_to
		        }
		    },
		    'message': f'Project workload data loaded in {int(calculation_time)} ms',
		    'performance': {
		        'calculation_time_ms': calculation_time,
		        'assignments': len(assignments_data),
		        'workload_calculations': workload_calculations
		        # 'month_working_days_cache_size': len(month_working_days_cache)  # ← УДАЛЕНО
		    },
		    'debug_info': {
		        'weekend_logic': 'ПРАВИЛЬНАЯ: выходные только через Holiday List с weekly_off=True',
		        'loading_types_supported': ['В рабочих часах', 'В % от фонда рабочих часов', 'В % от трудоемкости задачи'],
		        'project_weekly_off_dates_count': len(project_weekly_off_set),
		        'monthly_plans_loaded': len(monthly_plan_cache),
		        'structure': '3-level (user -> role -> task)'
		    }
		}
	except Exception as e:
		frappe.log_error("Error in get_project_workload_data", str(e))
		return {
			"tree_data": [],
			"periods": [],
			"users_count": 0,
			"tasks_count": 0,
			"assignments_count": 0,
			"error": str(e),
			"message": "Error loading project workload data",
		}
