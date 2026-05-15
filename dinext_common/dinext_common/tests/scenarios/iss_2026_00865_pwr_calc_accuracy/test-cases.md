# PWR: точность расчётов (V2 сетка команды vs V3 дерево проекта)

- issue: ISS-2026-00865
- site: `dev.dinext.localhost` (или текущий `--site` bench; не смешивать с `erp-dev.dinord.ru` без явного указания)
- owner_app: `dinext_common`
- dependent_apps:
  - `erpnext` (Project, Task, Holiday List)
  - `dinext_projects` (DocType Project Role, Project Work Efforts; для TC-09 — `Application For Leave`, `Worker`, `Type Of Leave` при наличии на сайте)
  - `project_workload_assignment` (DocType Project Workload Assignment)
- primary_surface: `Python`
- secondary_surfaces:
  - `Server Script` (тонкие обёртки `pwr_run_team_workload_grid` / `pwr_run_project_workload_tree` — регрессия после выкладки)
  - `Client Script` (агрегация/формат ячеек на UI — отдельный smoke, не дублирует математику ядра)
- scenario_dir: `frappe-bench/apps/dinext_common/dinext_common/dinext_common/tests/scenarios/iss_2026_00865_pwr_calc_accuracy/`
- data_helper: `data_setup.py`
- source_of_truth:
  - `dinext_common/dinext_common/project_workload/team_workload_grid.py` — `get_projects_workload_data_v2`
  - `dinext_common/dinext_common/project_workload/single_project_workload_tree.py` — `get_project_workload_data`
  - `dinext_common/project_workload_api.py` — whitelist `pwr_run_team_workload_grid` / `pwr_run_project_workload_tree`
  - Исторические Server Script (см. `.sandbox/local/server-script/api/`): **до этапа I** — `Get Projects Workload Data_Exp` (`get_projects_workload_data`); **ветка OLD** — `Get Projects Workload Data_Exp_OLD` (`get_projects_workload_data_old`, в SQL до сих пор `date_to >= CURDATE()`, не `nowdate()`); **до этапа II** — отключённые `PWR Legacy - … (Pre-Phase2)` (тот же `api_method`, что у тонких обёрток); **TC-10** фиксирует контракт уже перенесённого в Python V2 на фикстуре TC-01 (`fixtures/tc10_team_v2_golden.json`).
- sync_required: `no` (логика в Python-приложении; sandbox/fixtures для прогона не обязательны)
- run_targets:
  - `dinext_common.dinext_common.tests.scenarios.iss_2026_00865_pwr_calc_accuracy.test_pwr_calc_accuracy` (**16** тестовых методов: TC-01…TC-10, TC-04b, TC-05b, TC-12…TC-14).
  - **TC-11** — UI smoke вне `bench run-tests` (см. журнал). TC-10 — золотой JSON контракта Python V2; ручной A/B с `PWR Legacy` по-прежнему через переключение `disabled` (один `api_method` на активный скрипт).
- Команда прогона (backend-контейнер):  
  `docker exec "dinext-frappe-local-backend-1" bench --site dev.dinext.localhost run-tests --app dinext_common --module dinext_common.dinext_common.tests.scenarios.iss_2026_00865_pwr_calc_accuracy.test_pwr_calc_accuracy`
- actors:
  - setup_user: `Administrator` (создание/удаление тестовых документов)
  - business_user: `Administrator` (тот же пользователь в PWA)
  - ui_actor: только для TC-11 (UI smoke в браузере; не часть `bench run-tests`)
- runtime_inputs:
  - `frappe.utils.nowdate()` для V2: сетка периодов привязана к «сегодня»; в тестах фиксируется `patch(nowdate → ANCHOR_MONDAY)`.
  - `Task.project`, интервал PWA `date_from` / `date_to`, тип нагрузки `workload` / `wl_value`.
  - `Project.holiday_list` и строки `Holiday` с `weekly_off`.
  - Шаблоны Worker / Timesheet Template / часы по дням (если заданы у пользователя) — в минимальном сценарии не трогаем; при расхождении с prod расширить фикстуру.
  - `Application For Leave` (TC-09): статус «Согласовано», полный день; маркер в `alreasons` с префиксом сценария. На сайте должны импортироваться whitelisted-модули `dinext_projects.dinext_projects.permissions` и `dinext_projects.dinext_projects.model.workflow` (см. код в `apps/dinext_projects/.../dinext_projects/`).
  - `User Group` (TC-14): фильтр `user_group` в V2; в тесте группа только с `Administrator`, второй пользователь сценария исключён.
  - Для кейсов «без `holiday_list` на проекте» `data_setup` временно обнуляет `Worker.wholiday_list` у `Administrator` и восстанавливает значение в `reset_owned_data()`.
- reset_scope:
  - `Project`, `Task`, `Project Workload Assignment`, `Project Work Efforts` (по задачам сценария), `Holiday List`, `Project Role`, тестовый `User` `iss-2026-00865-pwr-2@example.com`, `User Group` и `Application For Leave` с префиксом сценария; при снятии флага сценария восстанавливается исходный `Worker.wholiday_list` у `Administrator` (если был сохранён).

## Status Legend

- ⚪ не составлен runnable-артефакт в текущем модуле или не входит в `run_targets`
- 🟡 runnable есть, успешный прогон **не** зафиксирован в журнале ниже
- 🟢 последний зафиксированный прогон успешен (журнал + `bench run-tests` по модулю из `run_targets`)
- 🔴 последний зафиксированный прогон с падением

## Известная гипотеза по багу «часы на выходные»

- Если у **проекта не задан `holiday_list`** или в списке **нет** записей на календарные субботы/воскресенья, то в `team_workload_grid.is_working_day_cached` суббота и воскресенье остаются **рабочими днями** для знаменателя распределения «В рабочих часах» — часы попадают и в колонки выходных (daily).
- В форме **одного проекта** у пользователя часто уже выбран проект с заполненным `holiday_list` (как в production), поэтому визуально V3 «корректен», а общий отчёт по команде с другим набором фильтров / без праздничного календаря — «размазывает» иначе.
- Строки `Holiday` с `weekly_off=1` попадают в SQL и в `holiday_date_sets` в V2; дата из этого множества считается нерабочей так же, как «жёсткий» праздник. В V3 используется разбор `project_holidays_set` / `project_weekly_off_set` — при расхождении с V2 TC-02 должен подсветить расхождение на одних и тех же данных.
- Референс по истории: см. `source_of_truth` (этап I vs II vs `Exp_OLD`); **TC-10** — регрессионный золотой контракт Python V2 на фикстуре TC-01, не полное JSON-равенство со старыми скриптами.

## Test Cases

Статусы 🟢/🔴 обновляются при записи результата в **Журнал прогона** (команда из блока `run_targets` выше или эквивалентный `/test-it`).

- 🟢 TC-01: Parity суммарных часов V2 vs V3 без `holiday_list` на проекте
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc01_*`, `prepare_case_hours_without_project_holiday_list`
  - last_run: 2026-05-07 — `dev.dinext.localhost`, `bench run-tests` модуль PWR — OK

- 🟢 TC-02: Выходные (сб/вс) без доли при `weekly_off` в Holiday List
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc02_*`, `prepare_case_hours_with_weekend_holiday_list`
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-02b: Без `holiday_list` — на выходных **ожидается** ненулевая доля (контроль инварианта)
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc02b_*`
  - notes: документирует ожидаемое поведение без календаря выходных на проекте при снятом `Worker.wholiday_list` в фикстуре.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-03: Parity по **ежедневным** ячейкам V2 vs V3 в окне назначения
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc03_*`
  - assert: max |ячейка V2 − ячейка V3| по дням `WEEK_START…WEEK_END` &lt; 0.15 ч.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-04: «В % от фонда рабочих часов» — V2 vs V3 (50%, неделя без HL; эталон ~28 ч, допуск ±0.75 ч)
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc04_*`, `prepare_case_percent_fund_without_holiday_list`
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-04b: «В % от трудоемкости задачи» + `Project Work Efforts` (май 160 ч, 50% → ~80 ч; V2≈V3)
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc04b_*`, `prepare_case_percent_task_effort`
  - notes: нужны `dinext_projects` (PWE) и `Fiscal Year` на интервал `WEEK_START`…`WEEK_END`; иначе `skipTest`.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK (на bench с PWE и FY)

- 🟢 TC-05: `mode=user_totals` (первая страница) = `mode=full` по `workload_total` для одного пользователя
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc05_*`
  - notes: пагинация с двумя пользователями — TC-05b.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-05b: Два пользователя — сумма `user_totals` (limit=1, offset 0+1) = сумма пользователей в `full`
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc05b_*`, `prepare_case_two_users_hours_for_pagination`
  - notes: создаётся второй User `iss-2026-00865-pwr-2@example.com`.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-06: Недельный `view_type=weekly`: `workload_total` пользователя ≈ 40 ч
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc06_*`
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-07: `mode=user_projects` + `detail_user` — только строки проектов (`_isProject`), без строки пользователя
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc07_*`
  - notes: соответствует `return_user_rows = (mode != 'user_projects')` в `team_workload_grid`.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-08: Whitelist `pwr_run_team_workload_grid` через `frappe.local.form_dict` = прямой `run_get_projects_workload_data_v2`
  - surface: `Python` + **secondary** точка как у Server Script | actor: `business_user`
  - artifacts: `test_tc08_*`
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-12: Месячный `view_type=monthly` (V2): `workload_total` ≈ 40 ч
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc12_*`
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-13: Whitelist `pwr_run_project_workload_tree` = прямой `run_get_project_workload_data`
  - surface: `Python` + secondary Server Script | actor: `business_user`
  - artifacts: `test_tc13_*`
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-09: Согласованный полный день отпуска — на дату отпуска почти нет часов в daily; сумма по неделе ≈ 40; V2≈V3
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc09_*`, `try_create_application_for_leave_tc09`
  - notes: требуется `Application For Leave`, `Worker` у `Administrator`, хотя бы один `Type Of Leave`; иначе `skipTest`. Вставка с `ignore_validate`: read-only `status` и Server Script на AFL (напр. расчёт часов) несовместимы с обнулённым `Worker.wholiday_list` в том же сценарии PWR. Whitelisted-модули: `dinext_projects.dinext_projects.permissions`, `dinext_projects.dinext_projects.model.workflow`.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-10: Золотой контракт ответа **Python V2** (`run_get_projects_workload_data_v2`) на фикстуре TC-01
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc10_v2_response_contract_golden`, `fixtures/tc10_team_v2_golden.json`
  - notes: не дублирует «скрипт до этапа I» (`Get Projects Workload Data_Exp` / `get_projects_workload_data` — другой метод и форма ответа). `Get Projects Workload Data_Exp_OLD` (`get_projects_workload_data_old`) — отдельный `api_method`, но в SQL фильтр `date_to >= CURDATE()` не согласован с `patch(nowdate)` в юнит-тестах, поэтому автоматический паритет с OLD в модуль **не** вынесен; для ручной сверки выровняйте дату БД или замените в OLD-скрипте на `frappe.utils.nowdate()`. Отключённые `PWR Legacy - … (Pre-Phase2)` — снимок до этапа II (см. `.sandbox/local/server-script/api/legacy-pre-phase2/README.md`).
  - last_run: 2026-05-14 — `dev.dinext.localhost`, модуль PWR — OK

- 🟢 TC-11: UI smoke — отчёт в браузере (`Projects Workload Report`)
  - surface: `UI smoke` | actor: `ui_actor` (фактически: Cursor Browser MCP, вкладка пользователя)
  - artifacts: Desk `http://dev.dinext.localhost:8080/app/projects-workload-report`
  - last_run: 2026-05-14 — smoke OK: форма открыта, фильтры User/Project/User Group, период Quarter; сетка с колонками и ячейками `N.Nh N%`; переключение Weekly → Daily → Monthly без падения UI; кнопка обновления ↻; кнопка «Показать еще 20» в режиме Monthly (пагинация). Консоль: `socket.io Invalid origin` (ожидаемо при origin через :8080), множественные `Error: <path> attribute d` (SVG/графики), предупреждение moment — **не блокировали** отображение таблицы.

- 🟢 TC-14: Фильтр `user_group` (V2): только пользователи из группы — в `full` одна user-строка ~40 ч; в `user_totals` `total_users=1`
  - surface: `Python` | actor: `business_user`
  - artifacts: `test_tc14_*`, `prepare_case_user_group_excludes_second_user`
  - notes: создаётся `User Group` с именем `ISS-2026-00865-PWR-UG` (только `Administrator`); второй пользователь с PWA не попадает в выборку.
  - last_run: 2026-05-07 — `dev.dinext.localhost`, модуль PWR — OK

## Primary test artifacts

- `test_pwr_calc_accuracy.py` — TC-01 … TC-10, TC-04b, TC-05b, TC-12, TC-13, TC-14
- `fixtures/tc10_team_v2_golden.json` — эталон TC-10
- `data_setup.py` — reset и prepare-*

## Журнал прогона `/test-it`

| дата | агент | результат | примечание |
|------|--------|-----------|-------------|
| 2026-05-07 | shell subagent | не выполнено | Docker daemon на хосте недоступен (`docker_engine` pipe). Статусы TC-01…TC-13 остаются 🟡 до реального `bench run-tests`. |
| 2026-05-07 | agent | OK (15/15) | До добавления TC-10: `bench run-tests` по модулю на `dev.dinext.localhost` (~53 с). |
| 2026-05-14 | agent | OK (16/16) | TC-10: `test_tc10_v2_response_contract_golden` + `fixtures/tc10_team_v2_golden.json`; уточнены линейки `Exp` / `Exp_OLD` / `PWR Legacy`; `bench run-tests` PWR на `dev.dinext.localhost`. |
| 2026-05-14 | agent + Cursor Browser | OK (TC-11) | UI smoke `Projects Workload Report` на `http://dev.dinext.localhost:8080/app/projects-workload-report`: сетка, фильтры, смена Weekly/Daily/Monthly, refresh, «Показать еще 20». Детали в TC-11 `last_run`. |

## Side effects повторного прогона

- После теста `tearDown` вызывает `reset_owned_data()` — тестовые документы удаляются.
- Если тест упал до `tearDown`, могут остаться строки с префиксом `ISS-2026-00865-PWR`; повторный запуск prepare/reset их подчистит.
- Логи `frappe.log` / `frappe.log_error` от V2 (PERF_TRACE) увеличивают шум Error Log на сайте — при массовом CI при необходимости заглушить perf в тестовом профиле.
