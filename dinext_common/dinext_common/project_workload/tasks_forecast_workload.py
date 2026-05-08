# Copyright (c) 2026, Dinext
"""Прогноз PWE и распределение нагрузки PWA по задачам проекта (API get_tasks_forecast_and_workload)."""

import frappe

def run_get_tasks_forecast_and_workload(fd):
	"""fd — dict или frappe._dict с полями project, periods, view_options."""
	if fd is None:
		fd = {}
	if not isinstance(fd, frappe._dict):
		fd = frappe._dict(fd)
	return _tasks_forecast_impl(fd)

# Флаг для включения/отключения детального логирования

ENABLE_DETAILED_LOG = True

def debug_log(message):

    """Логирует сообщение только если детальное логирование включено"""

    if ENABLE_DETAILED_LOG:

        frappe.log(message)

def _tasks_forecast_impl(fd):

    """Получает все задачи с прогнозом (PWE) и нагрузкой (PWA)"""

    

    project = fd.get('project')

    periods = fd.get('periods')

    view_options = fd.get('view_options', 'Прогноз и факт')

    

    debug_log("=== STEP 1: PARAMETERS ===")

    debug_log(f"Project: {project}")

    debug_log(f"Periods received: {periods is not None}")

    debug_log(f"View options: {view_options}")

    

    if not project:

        return {

            'tasks': [],

            'tasks_details': {},

            'error': 'No project specified'

        }

    

    # ========== 1. ПОЛУЧАЕМ ПЕРИОДЫ ==========

    debug_log("=== STEP 2: GET PERIODS ===")

    

    if not periods or not isinstance(periods, list):

        debug_log("No periods provided, generating from project dates")

        

        Project = frappe.qb.DocType('Project')

        project_data = (

            frappe.qb.from_(Project)

            .select(Project.expected_start_date, Project.expected_end_date)

            .where(Project.name == project)

            .limit(1)

        ).run(as_dict=True)

        

        if not project_data:

            return {

                'tasks': [],

                'tasks_details': {},

                'error': 'Project not found',

            }

        project_data = project_data[0]

        

        if not project_data.get('expected_start_date'):

            return {

                'tasks': [],

                'tasks_details': {},

                'error': 'Project start date not set'

            }

        

        start = frappe.utils.getdate(project_data.get('expected_start_date'))

        end = frappe.utils.getdate(project_data.get('expected_end_date') or frappe.utils.add_months(start, 12))

        

        periods = []

        current = frappe.utils.getdate(f"{start.year}-{start.month:02d}-01")

        end_first = frappe.utils.getdate(f"{end.year}-{end.month:02d}-01")

        

        while current <= end_first:

            next_month = frappe.utils.add_months(current, 1)

            next_month_start = frappe.utils.getdate(f"{next_month.year}-{next_month.month:02d}-01")

            is_past = next_month_start <= frappe.utils.getdate(frappe.utils.nowdate())

            

            periods.append({

                'year': current.year,

                'month': current.month,

                'is_past': is_past

            })

            current = frappe.utils.add_months(current, 1)

        

        debug_log(f"Generated {len(periods)} periods")

    else:

        debug_log(f"Received {len(periods)} periods")

        

    # ========== ФИЛЬТРАЦИЯ ПЕРИОДОВ ПО view_options ==========

    debug_log("=== STEP 2.5: FILTER PERIODS BY view_options ===")

    

    periods_to_check = []

    if view_options == "Только факт":

        # Не проверяем ничего

        periods_to_check = []

    elif view_options == "Только прогноз":

        # Проверяем ВСЕ периоды

        periods_to_check = periods

    else:  # "Прогноз и факт"

        # Проверяем только текущий и будущие периоды

        periods_to_check = [p for p in periods if not p.get('is_past', False)]

    

    debug_log(f"  view_options: {view_options}")

    debug_log(f"  periods before filter: {len(periods)}")

    debug_log(f"  periods after filter: {len(periods_to_check)}")

    

    periods = periods_to_check

    

    if not periods:

        return {

            'tasks': [],

            'tasks_details': {},

            'total_tasks': 0

        }

    

    # ========== 2. ПОЛУЧАЕМ ПРОГНОЗНЫЕ ДАННЫЕ (PWE) ==========

    debug_log("=== STEP 3: GET FORECAST DATA (PWE) ===")

    

    PWE = frappe.qb.DocType('Project Work Efforts')

    PWEA = frappe.qb.DocType('Project Work Efforts Amount')

    

    pwe_query = (

        frappe.qb.from_(PWE)

        .left_join(PWEA)

        .on(PWEA.parent == PWE.name)

        .select(

            PWE.pwe_task.as_('task'),

            PWE.pwe_project_role.as_('role'),

            PWEA.pwea_year.as_('year'),

            PWEA.pwea_month.as_('month'),

            PWEA.pwea_expected.as_('forecast_hours')

        )

        .where(PWE.pwe_project == project)

        .where(PWEA.pwea_expected.isnotnull())

        .where(PWEA.pwea_expected > 0)

    )

    

    pwe_list = pwe_query.run(as_dict=True)

    debug_log(f"Raw PWE records found: {len(pwe_list)}")

    

    forecast_cache = {}

    for row in pwe_list:

        if row.get('year') and row.get('month'):

            month = int(row.get('month'))

            key = f"{row.get('task')}_{row.get('role')}_{row.get('year')}_{month}"

            forecast_cache[key] = float(row.get('forecast_hours', 0))

    

    debug_log(f"Forecast cache size: {len(forecast_cache)}")

    

    # ========== 3. ПОЛУЧАЕМ ВСЕ НАЗНАЧЕНИЯ (PWA) ==========

    debug_log("=== STEP 4: GET ASSIGNMENTS (PWA) ===")

    

    if periods:

        min_date = f"{periods[0]['year']}-{periods[0]['month']:02d}-01"

        max_date = frappe.utils.get_last_day(f"{periods[-1]['year']}-{periods[-1]['month']:02d}-01")

    else:

        min_date = "2000-01-01"

        max_date = "2100-12-31"

    

    debug_log(f"Date range for assignments: {min_date} to {max_date}")

    

    PWA = frappe.qb.DocType('Project Workload Assignment')

    Task = frappe.qb.DocType('Task')

    User = frappe.qb.DocType('User')

    Worker = frappe.qb.DocType('Worker')

    TimesheetTemplate = frappe.qb.DocType('Timesheet Template')

    

    assignments_query = (

        frappe.qb.from_(PWA)

        .inner_join(Task)

        .on(Task.name == PWA.task)

        .left_join(User)

        .on(User.name == PWA.user)

        .left_join(Worker)

        .on(Worker.wuser == PWA.user)

        .left_join(TimesheetTemplate)

        .on(TimesheetTemplate.name == Worker.wtimesheet_template)

        .select(

            PWA.name,

            PWA.task,

            Task.subject.as_('task_subject'),

            PWA.role,

            PWA.user,

            User.full_name.as_('user_full_name'),

            PWA.workload,

            PWA.wl_value,

            PWA.date_from,

            PWA.date_to,

            Worker.wholiday_list,

            Worker.wtimesheet_template,

            TimesheetTemplate.hours_on_date,

            TimesheetTemplate.tt_working_hours_on_date

        )

        .where(Task.project == project)

        .where(PWA.date_from.isnotnull())

        .where(PWA.date_to.isnotnull())

        .where(PWA.date_to >= min_date)

        .where(PWA.date_from <= max_date)

    )

    

    assignments = assignments_query.run(as_dict=True)

    debug_log(f"Assignments found: {len(assignments)}")

    

    if not assignments:

        debug_log("No assignments found")

        return {

            'tasks': [],

            'tasks_details': {}

        }

    

    # ========== 4. ПОЛУЧАЕМ ВСПОМОГАТЕЛЬНЫЕ ДАННЫЕ ==========

    debug_log("=== STEP 5: GET AUXILIARY DATA ===")

    

    # 4.1 Holiday lists

    Project = frappe.qb.DocType('Project')

    project_holiday_result = (

        frappe.qb.from_(Project)

        .select(Project.holiday_list)

        .where(Project.name == project)

        .limit(1)

    ).run(as_dict=True)

    project_holiday_list = project_holiday_result[0].get('holiday_list') if project_holiday_result else None

    debug_log(f"Project holiday list: {project_holiday_list}")

    

    all_holiday_lists = set()

    user_holiday_lists = {}

    

    if project_holiday_list:

        all_holiday_lists.add(project_holiday_list)

    

    for a in assignments:

        if a.get('wholiday_list'):

            all_holiday_lists.add(a.get('wholiday_list'))

            user_holiday_lists[a.get('user')] = a.get('wholiday_list')

    

    debug_log(f"Total unique holiday lists: {len(all_holiday_lists)}")

    

    # 4.2 Загружаем праздники

    holidays_cache = {}

    if all_holiday_lists:

        Holiday = frappe.qb.DocType('Holiday')

        holidays = (

            frappe.qb.from_(Holiday)

            .select(

                Holiday.parent.as_('list_name'),

                Holiday.holiday_date,

                Holiday.weekly_off

            )

            .where(Holiday.parent.isin(list(all_holiday_lists)))

        ).run(as_dict=True)

        debug_log(f"Total holiday records loaded: {len(holidays)}")

        

        for h in holidays:

            list_name = h.get('list_name')

            if list_name not in holidays_cache:

                holidays_cache[list_name] = {

                    'dates': set(),

                    'weekly_off_dates': set()

                }

            date_str = str(h.get('holiday_date'))

            holidays_cache[list_name]['dates'].add(date_str)

            if h.get('weekly_off'):

                holidays_cache[list_name]['weekly_off_dates'].add(date_str)

    

    # 4.3 Загружаем отсутствия

    users = list(set(a.get('user') for a in assignments if a.get('user')))

    debug_log(f"Unique users: {len(users)}")

    

    absences_cache = {}

    if users:

        ApplicationForLeave = frappe.qb.DocType('Application For Leave')

        absences = (

            frappe.qb.from_(ApplicationForLeave)

            .select(

                ApplicationForLeave.lauser.as_('user'),

                ApplicationForLeave.alfrom_date,

                ApplicationForLeave.alto_date,

                ApplicationForLeave.altype_of_leave,

                ApplicationForLeave.alfrom_hours,

                ApplicationForLeave.alto_hours

            )

            .where(ApplicationForLeave.lauser.isin(users))

            .where(ApplicationForLeave.status == 'Согласовано')

            .where(ApplicationForLeave.alfrom_date.isnotnull())

            .where(ApplicationForLeave.alto_date.isnotnull())

        ).run(as_dict=True)

        debug_log(f"Total absence records: {len(absences)}")

        

        for a in absences:

            user = a.get('user')

            if user not in absences_cache:

                absences_cache[user] = []

            absences_cache[user].append(a)

    

    # 4.4 Загружаем переопределения рабочих часов

    working_hours_overrides = {}

    template_refs = set(a.get('tt_working_hours_on_date') for a in assignments if a.get('tt_working_hours_on_date'))

    debug_log(f"Unique working hours templates: {len(template_refs)}")

    

    if template_refs:

        WorkingHoursTable = frappe.qb.DocType('Working Hours Table')

        overrides = (

            frappe.qb.from_(WorkingHoursTable)

            .select(

                WorkingHoursTable.parent.as_('ref_name'),

                WorkingHoursTable.wht_date,

                WorkingHoursTable.wht_hours

            )

            .where(WorkingHoursTable.parent.isin(list(template_refs)))

            .where(WorkingHoursTable.parentfield == 'hod_working_hours_table')

            .where(WorkingHoursTable.parenttype == 'Working Hours On Date')

        ).run(as_dict=True)

        debug_log(f"Working hours overrides: {len(overrides)}")

        

        for o in overrides:

            ref_name = o.get('ref_name')

            if ref_name not in working_hours_overrides:

                working_hours_overrides[ref_name] = {}

            if o.get('wht_date'):

                working_hours_overrides[ref_name][str(o.get('wht_date'))] = float(o.get('wht_hours') or 0)

    

    # 4.5 Базовая норма часов

    base_hours_by_user = {}

    for a in assignments:

        if a.get('user') and a.get('user') not in base_hours_by_user:

            base_hours_by_user[a.get('user')] = float(a.get('hours_on_date') or 8.0)

    debug_log(f"Base hours set for {len(base_hours_by_user)} users")

    

    # ========== 5. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

    

    def is_working_day(date_str, user):

        if project_holiday_list and project_holiday_list in holidays_cache:

            hc = holidays_cache[project_holiday_list]

            if date_str in hc['dates'] and date_str not in hc['weekly_off_dates']:

                return False

        user_holiday_list = user_holiday_lists.get(user)

        if user_holiday_list and user_holiday_list in holidays_cache:

            hc = holidays_cache[user_holiday_list]

            if date_str in hc['dates'] and date_str not in hc['weekly_off_dates']:

                return False

        if user in absences_cache:

            date_obj = frappe.utils.getdate(date_str)

            for absence in absences_cache[user]:

                from_date = frappe.utils.getdate(absence.get('alfrom_date'))

                to_date = frappe.utils.getdate(absence.get('alto_date'))

                if from_date <= date_obj <= to_date:

                    if date_obj == from_date and absence.get('alfrom_hours'):

                        if float(absence.get('alfrom_hours')) >= 8:

                            return False

                    elif date_obj == to_date and absence.get('alto_hours'):

                        if float(absence.get('alto_hours')) >= 8:

                            return False

                    else:

                        return False

        return True

    

    def get_available_hours(date_str, user):

        if not is_working_day(date_str, user):

            return 0.0

        base_hours = base_hours_by_user.get(user, 8.0)

        for a in assignments:

            if a.get('user') == user and a.get('tt_working_hours_on_date'):

                overrides = working_hours_overrides.get(a.get('tt_working_hours_on_date'), {})

                if date_str in overrides:

                    base_hours = overrides[date_str]

                    break

        if user in absences_cache:

            date_obj = frappe.utils.getdate(date_str)

            for absence in absences_cache[user]:

                from_date = frappe.utils.getdate(absence.get('alfrom_date'))

                to_date = frappe.utils.getdate(absence.get('alto_date'))

                if from_date <= date_obj <= to_date:

                    if date_obj == from_date and absence.get('alfrom_hours'):

                        return max(0, base_hours - float(absence.get('alfrom_hours')))

                    elif date_obj == to_date and absence.get('alto_hours'):

                        return max(0, base_hours - float(absence.get('alto_hours')))

        return base_hours

    

    def get_working_days_in_period(assignment, period_start, period_end):

        calc_start = max(frappe.utils.getdate(assignment.get('date_from')), period_start)

        calc_end = min(frappe.utils.getdate(assignment.get('date_to')), period_end)

        if calc_start > calc_end:

            return 0

        working_days = 0

        current = calc_start

        while current <= calc_end:

            if is_working_day(str(current), assignment.get('user')):

                working_days += 1

            current = frappe.utils.add_days(current, 1)

        return working_days

    

    def calculate_effort_percentage_workload(assignment, period, forecast_hours):

        if not forecast_hours or forecast_hours <= 0:

            return 0

        percentage = float(assignment.get('wl_value') or 0) / 100

        period_start = frappe.utils.getdate(f"{period['year']}-{period['month']:02d}-01")

        period_end = frappe.utils.get_last_day(period_start)

        working_days = get_working_days_in_period(assignment, period_start, period_end)

        if working_days == 0:

            return 0

        base_daily = forecast_hours / working_days

        return percentage * base_daily * working_days

    

    # ========== 6. СБОР ВСЕХ ДАННЫХ ПО ЗАДАЧАМ ==========

    debug_log("=== STEP 6: COLLECT TASKS DATA ===")

    

    tasks_map = {}

    tasks_details = {}

    

    # СНАЧАЛА: собираем все прогнозы по задачам из forecast_cache

    debug_log("  Collecting forecasts from PWE...")

    for key, forecast_hours in forecast_cache.items():

        parts = key.split('_')

        if len(parts) >= 4:

            task = '_'.join(parts[:-3])

            role = parts[-3]

            year = int(parts[-2])

            month = int(parts[-1])

            

            if task not in tasks_map:

                tasks_map[task] = {

                    'task': task,

                    'task_subject': task,

                    'total_forecast': 0,

                    'total_assigned': 0

                }

            tasks_map[task]['total_forecast'] = tasks_map[task]['total_forecast'] + forecast_hours

            

            if task not in tasks_details:

                tasks_details[task] = {}

            if role not in tasks_details[task]:

                tasks_details[task][role] = {}

            period_key = f"{year}-{month}"

            tasks_details[task][role][period_key] = {

                'forecast_hours': forecast_hours,

                'users': {}

            }

            

            debug_log(f"    Added forecast for {task}/{role}/{period_key}: +{forecast_hours}")

    

    # Добавляем task_subject для задач

    for a in assignments:

        if a.get('task') in tasks_map and tasks_map[a.get('task')]['task_subject'] == a.get('task'):

            tasks_map[a.get('task')]['task_subject'] = a.get('task_subject') or a.get('task')

    

    # Затем: собираем нагрузку из PWA

    debug_log("  Collecting workload from PWA...")

    period_counter = 0

    task_role_counter = 0

    checked_counter = 0

    

    for period in periods:

        period_counter += 1

        period_start = frappe.utils.getdate(f"{period['year']}-{period['month']:02d}-01")

        period_end = frappe.utils.get_last_day(period_start)

        period_key = f"{period['year']}-{period['month']}"

        

        debug_log(f"Processing period {period_counter}/{len(periods)}: {period['year']}-{period['month']}")

        

        # Группируем назначения по (task, role)

        grouped = {}

        for a in assignments:

            assign_start = frappe.utils.getdate(a.get('date_from'))

            assign_end = frappe.utils.getdate(a.get('date_to'))

            if period_end >= assign_start and period_start <= assign_end:

                key = (a.get('task'), a.get('role') or '')

                if key not in grouped:

                    grouped[key] = []

                grouped[key].append(a)

        

        debug_log(f"  Task-role combinations in this period: {len(grouped)}")

        

        for (task, role), assigns in grouped.items():

            task_role_counter += 1

            

            forecast_key = f"{task}_{role}_{period['year']}_{period['month']}"

            forecast_hours = forecast_cache.get(forecast_key, 0)

            

            if task not in tasks_map:

                tasks_map[task] = {

                    'task': task,

                    'task_subject': assigns[0].get('task_subject') if assigns[0].get('task_subject') else task,

                    'total_forecast': 0,

                    'total_assigned': 0

                }

            

            # Добавляем прогноз (если его еще нет)

            if tasks_map[task]['total_forecast'] == 0 and forecast_hours > 0:

                tasks_map[task]['total_forecast'] = tasks_map[task]['total_forecast'] + forecast_hours

            

            period_assigned = 0

            

            for assignment in assigns:

                checked_counter += 1

                workload_type = assignment.get('workload')

                percentage = float(assignment.get('wl_value') or 0)

                

                # Инициализируем структуру

                if task not in tasks_details:

                    tasks_details[task] = {}

                if role not in tasks_details[task]:

                    tasks_details[task][role] = {}

                if period_key not in tasks_details[task][role]:

                    tasks_details[task][role][period_key] = {

                        'forecast_hours': forecast_hours,

                        'users': {}

                    }

                

                # Для типа "В % от трудоемкости задачи"

                if workload_type == 'В % от трудоемкости задачи':

                    if forecast_hours > 0:

                        assigned = calculate_effort_percentage_workload(assignment, period, forecast_hours)

                    else:

                        assigned = 0

                else:

                    assign_start = frappe.utils.getdate(assignment.get('date_from'))

                    assign_end = frappe.utils.getdate(assignment.get('date_to'))

                    

                    # Общее количество рабочих дней в назначении

                    total_working_days = 0

                    current = assign_start

                    while current <= assign_end:

                        if is_working_day(str(current), assignment.get('user')):

                            total_working_days += 1

                        current = frappe.utils.add_days(current, 1)

                    

                    # Количество рабочих дней в текущем периоде

                    period_working_days = 0

                    current = max(assign_start, period_start)

                    period_end_date = min(assign_end, period_end)

                    while current <= period_end_date:

                        if is_working_day(str(current), assignment.get('user')):

                            period_working_days += 1

                        current = frappe.utils.add_days(current, 1)

                    

                    ratio = period_working_days / total_working_days if total_working_days > 0 else 0

                    

                    if workload_type == 'В рабочих часах':

                        total_hours = float(assignment.get('wl_value') or 0)

                        assigned = total_hours * ratio

                    elif workload_type == 'В % от фонда рабочих часов':

                        percentage_value = float(assignment.get('wl_value') or 0) / 100

                        period_available = 0

                        current = max(assign_start, period_start)

                        while current <= min(assign_end, period_end):

                            if is_working_day(str(current), assignment.get('user')):

                                period_available += get_available_hours(str(current), assignment.get('user'))

                            current = frappe.utils.add_days(current, 1)

                        assigned = percentage_value * period_available

                    else:

                        continue

                

                if assigned > 0:

                    period_assigned = period_assigned + assigned

                    

                    user_email = assignment.get('user')

                    

                    if user_email not in tasks_details[task][role][period_key]['users']:

                        tasks_details[task][role][period_key]['users'][user_email] = {

                            'assigned_hours': 0,

                            'workload_type': workload_type,

                            'percentage': percentage

                        }

                    

                    current_hours = tasks_details[task][role][period_key]['users'][user_email]['assigned_hours']

                    tasks_details[task][role][period_key]['users'][user_email]['assigned_hours'] = current_hours + assigned

            

            # Обновляем total_assigned

            if task not in tasks_map:

                tasks_map[task] = {

                    'task': task,

                    'task_subject': task,

                    'total_forecast': 0,

                    'total_assigned': 0

                }

            tasks_map[task]['total_assigned'] = tasks_map[task]['total_assigned'] + period_assigned

            

            debug_log(f"    Added workload for {task}/{role}/{period_key}: +{period_assigned} hours total")

    

    # ========== 7. ФОРМИРУЕМ ОТВЕТ ==========

    debug_log("=== STEP 7: RESULTS ===")

    debug_log(f"Total periods processed: {period_counter}")

    debug_log(f"Total task-role combinations processed: {task_role_counter}")

    debug_log(f"Total assignments calculations: {checked_counter}")

    debug_log(f"Total tasks with data: {len(tasks_map)}")

    

    tasks_aggregated = []

    for task_id, task_data in tasks_map.items():

        tasks_aggregated.append({

            'task': task_data['task'],

            'task_subject': task_data['task_subject'],

            'total_forecast': round(task_data['total_forecast'], 2),

            'total_assigned': round(task_data['total_assigned'], 2)

        })

    

    frappe.log(f"Tasks with forecast/workload: {len(tasks_aggregated)}")

    

    return {

        'tasks': tasks_aggregated,

        'tasks_details': tasks_details,

        'total_tasks': len(tasks_aggregated)

    }