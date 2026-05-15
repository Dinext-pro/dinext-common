# Copyright (c) 2026, Dinext
"""Детерминированные данные для PWR: сетка команды (V2) vs дерево проекта (V3)."""

from __future__ import annotations

import frappe

PREFIX = "ISS-2026-00865-PWR"
ROLE_NAME = f"{PREFIX} Role"
BUSINESS_USER = "Administrator"
SECOND_USER_EMAIL = "iss-2026-00865-pwr-2@example.com"
TASK_TYPE = "Stage"
WORKLOAD_TYPE = "В рабочих часах"
WORKLOAD_PERCENT_FUND = "В % от фонда рабочих часов"
# В коде V2/V3 строка без «ё» (как в select/options PWA).
WORKLOAD_PERCENT_TASK = "В % от трудоемкости задачи"

# Фиксированная «сегодняшняя» дата для сетки V2 (monkeypatch nowdate в тесте).
ANCHOR_MONDAY = "2026-05-04"
# Одна календарная неделя с включением субботы/воскресенья в интервале назначения.
WEEK_START = "2026-05-04"
WEEK_END = "2026-05-10"

# Сохраняем Worker.wholiday_list у Administrator между reset и восстановлением (см. _detach_*).
_PWR_ADMIN_WHOLIDAY_SAVED = False
_PWR_ADMIN_WHOLIDAY_VALUE: str | None = None


def _detach_admin_worker_holiday_list() -> None:
	"""Убирает календарь с Worker, чтобы V2 не подмешивал company HL в кейсах «без holiday_list на проекте»."""
	global _PWR_ADMIN_WHOLIDAY_SAVED, _PWR_ADMIN_WHOLIDAY_VALUE
	wname = frappe.db.get_value("Worker", {"wuser": BUSINESS_USER}, "name")
	if not wname:
		return
	if not _PWR_ADMIN_WHOLIDAY_SAVED:
		_PWR_ADMIN_WHOLIDAY_VALUE = frappe.db.get_value("Worker", wname, "wholiday_list")
		_PWR_ADMIN_WHOLIDAY_SAVED = True
	frappe.db.set_value("Worker", wname, "wholiday_list", None, update_modified=False)


def _restore_admin_worker_holiday_list_if_saved() -> None:
	global _PWR_ADMIN_WHOLIDAY_SAVED, _PWR_ADMIN_WHOLIDAY_VALUE
	if not _PWR_ADMIN_WHOLIDAY_SAVED:
		return
	wname = frappe.db.get_value("Worker", {"wuser": BUSINESS_USER}, "name")
	if wname:
		frappe.db.set_value("Worker", wname, "wholiday_list", _PWR_ADMIN_WHOLIDAY_VALUE, update_modified=False)
	_PWR_ADMIN_WHOLIDAY_SAVED = False
	_PWR_ADMIN_WHOLIDAY_VALUE = None


def _default_company() -> str | None:
	row = frappe.db.sql("select name from `tabCompany` limit 1", as_dict=True)
	return row[0].name if row else None


def _default_project_type_name() -> str | None:
	"""Первый доступный Project Type (на dev обычно есть «Внутренний» из fixtures)."""
	for cand in ("Внутренний", "Internal", "Коммерческий", "External"):
		if frappe.db.exists("Project Type", cand):
			return cand
	row = frappe.db.sql("select name from `tabProject Type` limit 1", as_dict=True)
	return row[0].name if row else None


def _default_project_payment_scheme_name() -> str | None:
	"""Первый доступный Project Payment Scheme."""
	for cand in ("Неоплачиваемый", "Время и затраты (T&M)", "Фикс. стоимость"):
		if frappe.db.exists("Project Payment Scheme", cand):
			return cand
	row = frappe.db.sql("select name from `tabProject Payment Scheme` limit 1", as_dict=True)
	return row[0].name if row else None


def owned_entities() -> dict[str, list[str]]:
	return {
		"Project": [f"project_name like {PREFIX}%"],
		"Task": [f"subject like {PREFIX}%"],
		"Project Workload Assignment": ["task in owned tasks"],
		"Project Work Efforts": ["pwe_task in owned tasks"],
		"Holiday List": [f"name like {PREFIX}%"],
		"Project Role": [ROLE_NAME],
		"User": [SECOND_USER_EMAIL],
		"User Group": [f"name like {PREFIX}%"],
		"Application For Leave": [f"alreasons like {PREFIX}%"],
	}


def reset_owned_data() -> None:
	_restore_admin_worker_holiday_list_if_saved()
	for leave_name in frappe.get_all(
		"Application For Leave",
		filters={"alreasons": ["like", f"{PREFIX}%"]},
		pluck="name",
		ignore_permissions=True,
	):
		frappe.delete_doc("Application For Leave", leave_name, force=True, ignore_permissions=True)

	for ug_name in frappe.get_all(
		"User Group",
		filters={"name": ["like", f"{PREFIX}%"]},
		pluck="name",
		ignore_permissions=True,
	):
		frappe.delete_doc("User Group", ug_name, force=True, ignore_permissions=True)

	task_names = frappe.get_all(
		"Task",
		filters={"subject": ["like", f"{PREFIX}%"]},
		pluck="name",
		order_by="lft desc",
		ignore_permissions=True,
	)
	if task_names:
		for pwe in frappe.get_all(
			"Project Work Efforts",
			filters={"pwe_task": ["in", task_names]},
			pluck="name",
			ignore_permissions=True,
		):
			frappe.delete_doc("Project Work Efforts", pwe, force=True, ignore_permissions=True)

	for task_name in task_names:
		for pwa in frappe.get_all(
			"Project Workload Assignment",
			filters={"task": task_name},
			pluck="name",
			ignore_permissions=True,
		):
			frappe.delete_doc("Project Workload Assignment", pwa, force=True, ignore_permissions=True)
		frappe.delete_doc("Task", task_name, force=True, ignore_permissions=True)

	for proj in frappe.get_all(
		"Project",
		filters={"project_name": ["like", f"{PREFIX}%"]},
		pluck="name",
		ignore_permissions=True,
	):
		frappe.delete_doc("Project", proj, force=True, ignore_permissions=True)

	for hl in frappe.get_all(
		"Holiday List",
		filters={"name": ["like", f"{PREFIX}%"]},
		pluck="name",
		ignore_permissions=True,
	):
		frappe.delete_doc("Holiday List", hl, force=True, ignore_permissions=True)

	if frappe.db.exists("User", SECOND_USER_EMAIL):
		frappe.delete_doc("User", SECOND_USER_EMAIL, force=True, ignore_permissions=True)

	if frappe.db.exists("Project Role", ROLE_NAME):
		frappe.delete_doc("Project Role", ROLE_NAME, force=True, ignore_permissions=True)


def ensure_project_role() -> str:
	if not frappe.db.exists("Project Role", ROLE_NAME):
		frappe.get_doc(
			{
				"doctype": "Project Role",
				"role_name": ROLE_NAME,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
	return ROLE_NAME


def _create_holiday_list_for_weekend_rows(company: str) -> str:
	"""Два дня (сб/вс) в диапазоне WEEK_* с weekly_off=1 — как в production Holiday List."""
	name = f"{PREFIX}-HL-WEEKEND"
	if frappe.db.exists("Holiday List", name):
		return name
	doc = frappe.get_doc(
		{
			"doctype": "Holiday List",
			"name": name,
			"holiday_list_name": name,
			"company": company,
			"from_date": WEEK_START,
			"to_date": WEEK_END,
			"holidays": [
				{
					"holiday_date": "2026-05-09",
					"description": f"{PREFIX} Sat weekly_off",
					"weekly_off": 1,
				},
				{
					"holiday_date": "2026-05-10",
					"description": f"{PREFIX} Sun weekly_off",
					"weekly_off": 1,
				},
			],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_project(company: str, holiday_list: str | None) -> str:
	# На bench с dinext_projects у Project autoname = prompt — без явного name insert падает.
	project_name = f"{PREFIX} Project"
	project_id = f"{PREFIX}-PRJ"
	existing = frappe.get_all(
		"Project",
		filters={"project_name": project_name},
		limit=1,
		pluck="name",
		ignore_permissions=True,
	)
	if existing:
		pname = existing[0]
		if holiday_list:
			frappe.db.set_value("Project", pname, "holiday_list", holiday_list, update_modified=False)
		return pname

	pt = _default_project_type_name()
	pps = _default_project_payment_scheme_name()
	if not pt or not pps:
		frappe.throw(
			"В базе нет Project Type или Project Payment Scheme — сценарий PWR не может создать Project "
			"(ожидаются fixtures dinext_projects или аналог)."
		)

	p = frappe.get_doc(
		{
			"doctype": "Project",
			"name": project_id,
			"project_name": project_name,
			"project_type": pt,
			"custom_payment_scheme": pps,
			"company": company,
			"status": "Open",
			"expected_start_date": WEEK_START,
			"expected_end_date": WEEK_END,
			"holiday_list": holiday_list,
		}
	)
	p.insert(ignore_permissions=True)
	return p.name


def _create_task(project_name: str, subject_suffix: str) -> str:
	subject = f"{PREFIX} {subject_suffix}"
	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"status": "Open",
			"type": TASK_TYPE,
			"project": project_name,
			"exp_start_date": WEEK_START,
			"exp_end_date": WEEK_END,
			"is_group": 0,
		}
	)
	task.insert(ignore_permissions=True)
	return task.name


def _create_pwa(task: str, wl_value: float, *, workload: str | None = None, user: str | None = None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Project Workload Assignment",
			"task": task,
			"role": ensure_project_role(),
			"user": user or BUSINESS_USER,
			"task_dates": 1,
			"date_from": WEEK_START,
			"date_to": WEEK_END,
			"workload": workload or WORKLOAD_TYPE,
			"wl_value": wl_value,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def prepare_case_hours_without_project_holiday_list(wl_hours: float = 40.0) -> dict[str, str]:
	"""Проект без holiday_list: оба движка должны согласоваться по сумме (± float)."""
	reset_owned_data()
	_detach_admin_worker_holiday_list()
	company = _default_company()
	if not company:
		frappe.throw("Нет Company в базе — сценарий не может создать Project")
	ensure_project_role()
	project = _create_project(company, holiday_list=None)
	task = _create_task(project, "Leaf week")
	pwa = _create_pwa(task, wl_hours)
	return {
		"company": company,
		"project": project,
		"task": task,
		"pwa": pwa,
		"holiday_list": "",
	}


def prepare_case_percent_fund_without_holiday_list(wl_percent: float = 50.0) -> dict[str, str]:
	"""«В % от фонда рабочих часах»: без holiday_list все календарные дни 8 ч × доля — для недели 7×8×(p/100)."""
	reset_owned_data()
	_detach_admin_worker_holiday_list()
	company = _default_company()
	if not company:
		frappe.throw("Нет Company в базе — сценарий не может создать Project")
	ensure_project_role()
	project = _create_project(company, holiday_list=None)
	task = _create_task(project, "Leaf week pct")
	pwa = _create_pwa(task, wl_percent, workload=WORKLOAD_PERCENT_FUND)
	return {
		"company": company,
		"project": project,
		"task": task,
		"pwa": pwa,
		"holiday_list": "",
	}


def prepare_case_hours_with_weekend_holiday_list(wl_hours: float = 40.0) -> dict[str, str]:
	"""Проект + Holiday List: сб/вс с weekly_off — часы не должны «размазываться» на выходные."""
	reset_owned_data()
	company = _default_company()
	if not company:
		frappe.throw("Нет Company в базе — сценарий не может создать Project")
	ensure_project_role()
	hl = _create_holiday_list_for_weekend_rows(company)
	project = _create_project(company, holiday_list=hl)
	task = _create_task(project, "Leaf week HL")
	pwa = _create_pwa(task, wl_hours)
	return {
		"company": company,
		"project": project,
		"task": task,
		"pwa": pwa,
		"holiday_list": hl,
	}


def _pick_fiscal_year_for_assignment_window() -> str | None:
	"""Fiscal Year, пересекающийся с WEEK_START..WEEK_END (май 2026)."""
	rows = frappe.db.sql(
		"""
		select name from `tabFiscal Year`
		where year_start_date <= %(end)s and year_end_date >= %(start)s
		limit 1
		""",
		{"start": WEEK_START, "end": WEEK_END},
	)
	if not rows:
		return None
	return rows[0][0]


def ensure_second_test_user() -> str:
	if frappe.db.exists("User", SECOND_USER_EMAIL):
		return SECOND_USER_EMAIL
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": SECOND_USER_EMAIL,
			"first_name": "PWR",
			"last_name": "Test2",
			"enabled": 1,
			"send_welcome_email": 0,
			"new_password": "Test-Pwr-00000",
		}
	)
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	return SECOND_USER_EMAIL


def prepare_case_percent_task_effort(
	wl_percent: float = 50.0,
	*,
	plan_hours_may: float = 160.0,
) -> dict[str, str]:
	"""PWE с планом на май + PWA «В % от трудоемкости задачи» (ожидаемая сумма ≈ plan × wl/100 за полный охват месяца в диапазоне)."""
	if not frappe.db.exists("DocType", "Project Work Efforts"):
		frappe.throw("DocType Project Work Efforts не установлен — пропустите TC-04b на этом bench")

	reset_owned_data()
	company = _default_company()
	if not company:
		frappe.throw("Нет Company в базе — сценарий не может создать Project")
	fy = _pick_fiscal_year_for_assignment_window()
	if not fy:
		frappe.throw("Нет Fiscal Year на интервал теста — пропустите TC-04b или создайте FY в ERPNext")
	ensure_project_role()
	project = _create_project(company, holiday_list=None)
	task = _create_task(project, "Leaf task effort")
	pwe = frappe.get_doc(
		{
			"doctype": "Project Work Efforts",
			"pwe_project": project,
			"pwe_task": task,
			"pwe_project_role": ROLE_NAME,
			"pwe_amount": [
				{
					"pwea_year": fy,
					"pwea_month": 5,
					"pwea_plan": plan_hours_may,
				}
			],
		}
	)
	pwe.insert(ignore_permissions=True)
	pwa = _create_pwa(task, wl_percent, workload=WORKLOAD_PERCENT_TASK)
	return {
		"company": company,
		"project": project,
		"task": task,
		"pwa": pwa,
		"pwe": pwe.name,
		"fiscal_year": fy,
		"holiday_list": "",
	}


def prepare_case_two_users_hours_for_pagination(
	admin_hours: float = 40.0,
	second_hours: float = 20.0,
) -> dict[str, str]:
	"""Два пользователя, одна задача, два PWA — для суммирования user_totals по страницам."""
	reset_owned_data()
	company = _default_company()
	if not company:
		frappe.throw("Нет Company в базе — сценарий не может создать Project")
	ensure_project_role()
	ensure_second_test_user()
	project = _create_project(company, holiday_list=None)
	task = _create_task(project, "Shared two users")
	pwa1 = _create_pwa(task, admin_hours, user=BUSINESS_USER)
	pwa2 = _create_pwa(task, second_hours, user=SECOND_USER_EMAIL)
	return {
		"company": company,
		"project": project,
		"task": task,
		"pwa_admin": pwa1,
		"pwa_second": pwa2,
		"second_user": SECOND_USER_EMAIL,
		"holiday_list": "",
	}


LEAVE_MARK_TC09 = f"{PREFIX} TC-09 full day"
USER_GROUP_NAME = f"{PREFIX}-UG"


def try_create_application_for_leave_tc09(
	leave_day: str = "2026-05-06",
) -> str | None:
	"""Один полный день отпуска «Согласовано» для Worker текущего BUSINESS_USER. Возвращает имя документа или None."""
	if not frappe.db.exists("DocType", "Application For Leave"):
		return None
	worker = frappe.db.get_value("Worker", {"wuser": BUSINESS_USER}, "name")
	tol_list = frappe.get_all("Type Of Leave", limit=1, pluck="name")
	if not worker or not tol_list:
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Application For Leave",
			"alworker": worker,
			"status": "Согласовано",
			"altype_of_leave": tol_list[0],
			"alfrom_date": leave_day,
			"alto_date": leave_day,
			"alfrom_hours": "8",
			"alto_hours": "8",
			"alreasons": LEAVE_MARK_TC09,
		}
	)
	# validate + Server Script на AFL (напр. afl_calculate_hours) ожидают заполненный календарь Worker;
	# в PWR-сценарии `prepare_case_hours_without_project_holiday_list` временно снимает `wholiday_list`.
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	return doc.name


def prepare_case_user_group_excludes_second_user() -> dict[str, str]:
	"""Два PWA (40+20 ч), User Group только с Administrator — второй пользователь отфильтровывается."""
	ctx = prepare_case_two_users_hours_for_pagination(40.0, 20.0)
	if frappe.db.exists("User Group", USER_GROUP_NAME):
		frappe.delete_doc("User Group", USER_GROUP_NAME, force=True, ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "User Group",
			"name": USER_GROUP_NAME,
			"user_group_members": [{"user": BUSINESS_USER}],
		}
	).insert(ignore_permissions=True)
	ctx["user_group"] = USER_GROUP_NAME
	return ctx


def reset():
	reset_owned_data()
