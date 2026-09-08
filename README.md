# Dinext Common

`dinext_common` — общее Frappe-приложение платформы Dinext. Оно устанавливается
в существующий [Bench](https://github.com/frappe/bench) с Frappe и ERPNext и
централизует сквозной брендинг, настройки сайта, переиспользуемое поведение
Desk, настраиваемые workspace-хабы, ленту What's New, подключаемые
frontend-библиотеки и подсистему очистки данных.

Приложение ставится на несколько сайтов вместе с другими приложениями Dinext.
Domain-приложения (`dinext_*`) потребляют его API и assets; само
`dinext_common` не сидирует доменные карточки хаба.

## Содержание

- [Обзор и границы ответственности](#обзор-и-границы-ответственности)
- [Возможности](#возможности)
- [Установка](#установка)
- [Использование](#использование)
- [Технологии](#технологии)
- [Конфигурация](#конфигурация)
- [Требования](#требования)
- [Разработка и сопровождение](#разработка-и-сопровождение)
- [Документация](#документация)
- [Благодарности](#благодарности)
- [История изменений](#история-изменений)
- [Структура репозитория](#структура-репозитория)
- [Схема взаимодействия](#схема-взаимодействия)
- [Лицензия](#лицензия)

## 📖 Обзор и границы ответственности

На практике приложение делает следующее:

- применяет общую конфигурацию сайта через fixtures: `Website Settings`,
  `Navbar Settings`, `Web Page`, `Data Cleanup Rules`, `Server Script`,
  `Custom HTML Block`;
- подключает общие Desk-ресурсы из `hooks.py`;
- курирует меню workspace: корневые `Dinext` и `Settings`, хабы с карточками,
  списками страниц и персональными списками DocType;
- публикует и синхронизирует ленту `Dinext News Feed` для Desk What's New;
- предоставляет стандартную тему сайта и брендинговые ресурсы Dinext;
- поставляет переиспользуемые JS/CSS-библиотеки, которые другие приложения
  подгружают по требованию;
- даёт инструмент Desk для предварительного анализа fixtures по всем
  установленным приложениям.

В экосистеме Dinext функциональность разделена между приложениями:

| Приложение | Ответственность |
| --- | --- |
| `dinext_common` | Брендинг, Desk UX, workspace-меню и хабы, News Feed, Fixture Analysis, очистка данных, общие JS/CSS, шаблон плана счетов Dinext. |
| Domain-приложения (`dinext_projects` и др.) | Свои DocType, workspace и карточки хаба. Регистрируют вклады через `dinext_common.setup.hub_catalog`. |
| ERPNext | Обязательная зависимость (`required_apps`). План счетов и Company переопределяются только для шаблона `Dinext`. |

Этот README — точка входа для установки и сопровождения. Общие agent-правила
Dinext не копируются сюда: см. [AGENTS.md](AGENTS.md).

## ✨ Возможности

- Общий брендинг Dinext для Desk и сайта через `app_logo_url`, `app_icon` и
  `website_context` в `dinext_common/hooks.py`.
- Настройка сайта через fixtures: `Website Settings`, `Navbar Settings`,
  `Data Cleanup Rules`, контент главной страницы, включённые `Server Script`,
  `Client Script`, `Custom Field` модуля `Dinext Common`, `Custom HTML Block`
  (`Dinext Hub`, `Dinext Settings Hub`), `Holiday List` «Праздники и выходные РФ».
- Курирование Desk workspace:
  - публичные корневые workspace `Dinext` и `Settings`;
  - скрытие public-workspace, не принадлежащих модулям `dinext_*`;
  - ERPNext `Home` остаётся скрытой записью, но не показывается в меню Desk
    (включая Workspace Manager) и не является landing: `/app/home` → `/app/dinext`;
  - вложение `Users`, `Tools`, `Integrations`, `Build`, `Website` под `Settings`;
  - назначение `Dinext` как `default_workspace` новым пользователям.
- **Dinext Hub** на workspace `Dinext`: навигационные карточки, списки **Frequent
  Pages** / **Recent Pages** над секциями и компактные персональные списки
  DocType (quick create, assigned, liked, attention).
- **Settings Hub** на workspace `Settings` (роли `System Manager` /
  `Workspace Manager`): дочерние workspace и карточки Configuration.
- Регистрация карточек, лимитов секций и DocType-вкладов из domain-приложений
  через `dinext_common.setup.hub_catalog`.
- **Dinext News Feed**: DocType-публикатор, guest API и ежедневная синхронизация
  local `Changelog Feed`; стандартная еженедельная загрузка changelog Frappe
  отключается.
- Глобальные улучшения Desk через `app_include_js` / `app_include_css`:
  - `workspace_slug_redirects.js` — редирект старых RU-slug workspace и
    `/app/home` → Dinext без boot-проверки цели (`set_route` в живом Desk);
  - `breadcrumbs_update.js`;
  - `listview_resize.js`;
  - `dinext-desk.js`;
  - `dashboard_filters_fix.js`;
  - `workspace_sidebar_hover.js` + `workspace_sidebar_hover.css`.
- `sticky-datatable.js` только для DocType `Project` через `doctype_js`.
- Стандартная тема сайта `Dinext Theme`.
- Подключаемые frontend-библиотеки: **DinextTable** (AG Grid 35 Community),
  Form Conflict Merge, `DinextCharts`, Frappe DataTable, HyperList, Frappe Gantt,
  ECharts.
- Страница Desk **Fixture Analysis** (`/app/fixture-analysis`).
- Настраиваемая ежедневная очистка данных через `Data Cleanup Rules` и шесть
  дочерних таблиц правил.
- Шаблон плана счетов **Dinext**: override `Company` и методов ERPNext для
  выбора CoA.

## 🚀 Установка

Приложение устанавливается в существующий Bench с Frappe и ERPNext. Используйте
фактический Git URL и ветку вашей поставки.

```bash
cd /path/to/your/bench
bench get-app <git-url> --branch <branch>
bench --site your-site.local install-app dinext_common
bench --site your-site.local migrate
```

После установки или обновления пересоберите assets, чтобы применились Desk-ресурсы:

```bash
bench build --app dinext_common
bench --site your-site.local clear-cache
```

После установки (`after_install`) и каждой миграции (`after_migrate`) приложение
дополнительно:

- вызывает `configure_workspace_menu()` — создаёт/обновляет корни `Dinext` и
  `Settings`, вкладывает дочерние Settings-workspace, подключает Custom HTML
  Blocks хабов, создаёт стандартные записи `Dinext Workspace Settings`
  (`Dinext`, `Settings`), мигрирует legacy `Настройки` → `Settings`;
- запускает `setup_dinext_news_feed()` — отключает встроенный Frappe changelog
  fetch и синхронизирует What's New.

При создании нового пользователя без `default_workspace` hook
`User.after_insert` назначает workspace `Dinext`. Маршруты `/app/home` и
`/app/workspaces/home` открывают `Dinext` без boot-проверки `slug_exists`
(в живом Desk через `frappe.set_route`, без перезагрузки страницы);
существующие `default_workspace` не меняются.

Если в развёртывании ещё нет брендинговых файлов Dinext, перед `bench build`
они должны лежать в `dinext_common/public/images/`:

- `DI_SQ_NBG.png`
- `DINEXT_2.png`
- `DINEXT_FAVICON.ico`

Если web-процесс запущен с Gunicorn `--preload`, после изменений Python
перезапустите web worker, иначе Desk продолжит отдавать старый код.

## 🛠️ Использование

### Брендинг и общий UI

После установки и миграции:

- в Desk используются логотип и favicon приложения Dinext из `hooks.py`;
- на сайте — splash-изображение Dinext и тема `Dinext Theme`;
- маршрут главной страницы задаётся fixture `Web Page` с route `homepage`;
- в меню Help навбара доступна ссылка на документацию `https://docs.dinext.ru`.

### Скрипты Desk

Приложение подключает общее поведение во все сессии Desk:

- `workspace_slug_redirects.js` перенаправляет устаревшие RU-slug workspace
  (например `/app/мои-задачи` → `/app/my-tasks`) после boot-проверки цели;
  `/app/home` и `/app/workspaces/home` открывают `Dinext` без `slug_exists`
  через `frappe.set_route` в живом Desk (без `location.replace`, чтобы
  сохранить session `frappe.route_history` / Recent Pages);
  `location.replace` только если `set_route` ещё нет;
  правит `localStorage.current_page`;
- `breadcrumbs_update.js` сохраняет контекст workspace в breadcrumbs и
  поддерживает копирование последнего элемента;
- `listview_resize.js` сохраняет ширины колонок списка в `localStorage`;
- `dinext-desk.js` настраивает диалог About и показывает версии установленных
  приложений;
- `dashboard_filters_fix.js` улучшает динамическую фильтрацию дашборда для
  `_assign` и `_liked_by`;
- `workspace_sidebar_hover.js` — icon-rail workspace-меню на всём Desk: на
  Workspaces кнопка sidebar переключает полный вид и полоску с иконками; на
  List/Form/прочих экранах свёрнутый rail показывается принудительно. При
  наведении меню временно открывается **поверх** контента (без сдвига основной
  колонки). Состояние свёртки на Workspaces хранится в `localStorage`. DOM
  меню всегда в `.row.layout-main > .layout-side-section` активной страницы.

Для DocType `Project` подключается `sticky-datatable.js` — виртуализированная
таблица с закреплением строк на базе `frappe-datatable.min.js` и `hyperlist.js`.

### Workspace sidebar hover-expand

По умолчанию функция **включена**. Отключение — через `site_config.json` сайта:

```json
{
  "dinext_workspace_sidebar_hover_expand": 0
}
```

Отсутствие ключа или значение `1` / `true` оставляет поведение включённым.
После изменения конфига выполните `bench --site your-site.local clear-cache`
и обновите Desk (или перелогиньтесь), чтобы подтянуть bootinfo.

Временное открытие по hover — fixed-overlay поверх рабочей области; ширина
основного экрана не меняется. Полное разворачивание по кнопке toggle (только
на Workspaces) по-прежнему занимает колонку в layout.

На Workspaces при свёрнутом sidebar к основной колонке добавляется небольшой
left padding (`--dinext-ws-rail-pad-left`), чтобы контент не прилипал к
icon-rail. На List/Form/Report и других экранах Desk свёрнутый workspace rail
монтируется в `.layout-side-section` текущей страницы (при необходимости
колонка создаётся). List/form sidebar остаётся рядом и не превращается в
icon-rail; кнопка toggle страницы управляет ими, не workspace-меню. На Form
сохранённого документа нативная form-sidebar открыта по умолчанию; у нового
несохранённого документа Frappe по-прежнему скрывает её до Save.

На мобильной ширине остаётся стандартный overlay Frappe.

### Dinext Hub и Settings Hub

На workspace `Dinext` отображается блок **Dinext Hub**, на workspace
`Settings` — **Dinext Settings Hub**. Оба блока — тонкие адаптеры: HTML задаёт
`data-settings-name`, script загружает
`/assets/dinext_common/js/workspace_hub.js` и вызывает
`dinext_common.workspace_hub.mount(root_element)`. Стили инжектятся в shadow
root из `/assets/dinext_common/css/workspace_hub.css`. Блоки подключаются при
`configure_workspace_menu()` на install и migrate.

Администраторы настраивают содержимое хаба через именованные записи DocType
**Dinext Workspace Settings** (запись: роли `System Manager` /
`Workspace Manager`; чтение хаба — для Desk User, если у записи не заданы
ограничивающие `roles`):

| Поле / таблица | Назначение |
| --- | --- |
| `settings_name` | Уникальный ключ записи (`Dinext`, `Settings` или ключ другого приложения). Имя документа совпадает с ключом. |
| `show_frequent_pages` / `show_recent_pages` | Чекбоксы секции **Page Lists** (по умолчанию включены). На записи **`Settings`** оба флага принудительно выключены при configure. |
| `roles` | Если заданы, API хаба отдаёт каталог только пользователям с одной из этих ролей. Для `Settings` по умолчанию: `System Manager`, `Workspace Manager`. |
| `items` (`Dinext Workspace Settings Item`) | Навигационные карточки: секция, тип (`Workspace` / `DocType` / `Report` / `Page` / `URL`), target, label, description, icon, enabled, optional `required_role`. |
| `sections` (`Dinext Workspace Settings Section`) | Лимит персональных списков (`list_limit`, по умолчанию **5**) и максимум колонок карточек (`card_columns`, по умолчанию **4**; для секций записи `Settings` — **5**). Если карточек меньше лимита, ряд занимает всю ширину. |
| `doctype_items` (`Dinext Workspace Settings DocType`) | Вклады DocType в секцию: quick create, assigned, liked, attention, JSON `attention_filter` и общий JSON `list_filter` для assigned/liked. |

Стандартные записи, создаваемые `dinext_common`:

- **`Dinext`** — каталог Dinext Hub. Domain-приложения регистрируют сюда
  карточки через `register_hub_*` (имя по умолчанию).
- **`Settings`** — каталог Settings Hub: секции Workspaces (`Users`, `Tools`,
  `Integrations`, `Build`, `Website`) и Configuration (пять Frappe core
  Singles: System Settings, Session Default Settings, Document Naming
  Settings, Log Settings, Global Search Settings). Frequent Pages и Recent
  Pages на этой записи выключены.

Другое приложение может:

- добавить строки в `Dinext` или `Settings` без нового Custom HTML Block —
  соответствующий хаб подхватит их;
- создать собственную именованную запись; чтобы показать её на Workspace,
  нужен тонкий Custom HTML Block с `data-settings-name="<имя>"` и widget в
  `Workspace.content`.

**Общий API** (`dinext_common.workspace_hub.get_workspace_hub(settings_name)`):

- возвращает только включённые карточки выбранной записи, доступные текущему
  пользователю по роли записи, `required_role` и правам на target;
- корневые поля `show_frequent_pages`, `show_recent_pages`, `page_list_limit`
  (сейчас **5**);
- под каждой секцией может показывать компактные персональные списки:
  - **Quick Create** — если есть право `create` (кнопки, не строки списка);
  - **Assigned** — открытые `ToDo`, назначенные пользователю, затем опциональный
    `list_filter`;
  - **Liked** — документы с `_liked_by` и тем же опциональным `list_filter`;
  - **Attention** — `frappe.get_list` по JSON `attention_filter` (пустой фильтр = все
    доступные документы в лимите). `list_filter` на Attention не действует.

Списки страниц **рисует клиент**, а не API:

| Список | Источник | Поведение |
| --- | --- | --- |
| Frequent Pages | `frappe.boot.frequently_visited_links` | До `page_list_limit` полезных маршрутов. |
| Recent Pages | сессионный `frappe.route_history` | Новые сверху, без дублей, без текущей workspace-страницы. |

Клиент рисует Frequent Pages и Recent Pages **двумя рядами pill-плашек**
(иконка + текст; hover — обводка через CSS-переменные Desk). **Recent Pages**
сверху, **Frequent Pages** ниже. Иконка Workspace берётся из
`frappe.boot.allowed_workspaces` (не из `frappe.workspaces`, где после открытия
Workspace поле `icon` пропадает). Подпись Workspace-плашки — только название
рабочего пространства, без слова «Workspace». Подпись Form-плашки — `title_field` документа
или `name` по Naming Rule, без префикса DocType; полный контекст остаётся в
tooltip. В списки попадают маршруты `Form` / `List` / `Tree` / `Workspaces` /
`query-report`. Пропускаются `setup-wizard`, `social`, `recorder` и формы
`new-*`. Пустые группы не показываются. При возврате на Workspaces без полной
перезагрузки хаб обновляется через `frappe.router.on("change")`. Списки не
переживают полный reload Desk дальше того, что есть в boot и сессии.

Карточка типа **Report** открывается как
`/app/query-report/{urlencoded имя отчёта}` (не slug): иначе Desk ищет
документ Report по slug и не находит `Task Epic Burndown`.

`get_dinext_hub` и `get_settings_hub` — совместимые обёртки для записей
`Dinext` и `Settings`.

Whitelisted методы хаба:

- `dinext_common.workspace_hub.get_workspace_hub`
- `dinext_common.workspace_hub.get_dinext_hub`
- `dinext_common.workspace_hub.get_settings_hub`

Колонки «Recently Opened» по DocType нет: Frappe не хранит Form-маршруты в
DocType `Route History`. Поле `show_recently_opened` с child DocType удалено.

### Регистрация Hub-карт из domain-приложений

Domain-приложения (`dinext_*`) регистрируют свои карточки и списки из
`after_install` / `after_migrate`. `dinext_common` **не** сидирует доменные
карточки — их добавляют владеющие apps.

```python
from dinext_common.setup.hub_catalog import (
	register_hub_doctype_items,
	register_hub_items,
	register_hub_sections,
	relocate_hub_item_section,
)

register_hub_items(
	[
		{
			"section": "My Work",
			"element_type": "Workspace",
			"target": "Мои задачи",
			"label": "My Tasks",
			"description": "Personal dashboard for assigned work.",
			"icon": "assign",
			"enabled": 1,
		}
	],
	source_app="dinext_projects",
)

register_hub_sections(
	[{"section": "My Work", "list_limit": 5}],
	source_app="dinext_projects",
)

register_hub_doctype_items(
	[
		{
			"section": "My Work",
			"document_type": "Task",
			"show_quick_create": 1,
			"show_assigned": 1,
			"show_liked": 1,
			"show_attention": 1,
			"attention_filter": '[["status","=","Open"]]',
			"list_filter": '[["type","!=","Issue"]]',
		}
	],
	source_app="dinext_projects",
)
```

Контракт идемпотентности:

- карточки: ключ `(element_type, target)` — существующие строки сохраняют
  правки администратора (label, description, icon, section, enabled, role);
  пустой icon может быть backfill'нут;
- секции: ключ `section` — `list_limit` и `card_columns` администратора не
  перезаписываются;
- DocType-вклады: ключ `(section, document_type, source_app)` — непустой
  `list_filter` и прочие флаги администратора не перезаписываются; пустой
  `list_filter` дозаполняется из регистрации; `show_assigned` и
  `show_quick_create` включаются односторонне (`0` → `1`), но не выключаются;
- неизвестные ключи вроде legacy `show_recently_opened` / `recent`
  игнорируются;
- `relocate_hub_item_section(...)` меняет только `section` у существующей
  карточки;
- все `register_hub_*` принимают `settings_name` (по умолчанию `"Dinext"`);
  ключи дедупликации действуют внутри выбранной записи.

Правила каталога Dinext Hub:

- **Project Management** — списки DocType только `Project` и
  `Project Portfolio` (Task и Issue остаются в My Work). У обоих вкладов
  включены Assigned и Quick Create. Gantt регистрирует карточку отчёта
  Task Epic Burndown и не регистрирует Task в этой секции.
- Стандартный `list_filter` (открытая работа, не Attention): Task —
  `type != Issue` и `status not in Completed/Cancelled`; Issue —
  `status in Open/Replied/On Hold`; Project — `status not in
  Completed/Cancelled`; Project Portfolio — `status = Активный`.
- **Scope & Governance** не наполняется: `dinext_project_scope`,
  `dinext_risk_management` и `dinext_project_stage_gate` больше не
  регистрируют карточки. Уже записанные ряды регистрация не удаляет.

### Dinext News Feed / What's New

Подсистема заменяет стандартную еженедельную агрегацию Frappe changelog
собственной лентой Dinext.

**Publisher** (обычно сайт документации, где ведётся контент):

- DocType `Dinext News Feed`: `title`, `app_name`, `link`,
  `posting_timestamp`, `is_published`;
- guest API `dinext_common.changelog_feed.get_published_feed` возвращает до 20
  опубликованных записей новее `since`.

**Consumer** (ERP/Desk сайты):

- hook `get_changelog_feed = dinext_common.changelog_feed.get_feed`;
- ежедневный scheduler `dinext_common.changelog_feed.sync_dinext_news_feed`;
- тот же setup вызывается из `after_install` и `after_migrate`;
- при успехе local `Changelog Feed` полностью заменяется данными publisher;
- при ошибке сети/HTTP local feed **не** очищается; ошибка пишется в Error Log.

URL publisher задаётся в `site_config.json` (по умолчанию
`https://docs.dinext.ru`):

```json
{
  "dinext_news_feed_url": "https://docs.dinext.ru"
}
```

Для работы ежедневной синхронизации нужны scheduler, workers и сетевой доступ
consumer-сайта к publisher URL.

### Fixture Analysis

Страница **Fixture Analysis** помогает проверить расхождение fixtures перед
импортом метаданных на сайт. Режим только чтения: база данных и fixture-файлы
не изменяются.

**Доступ:** роль `System Manager` (маршрут Desk `/app/fixture-analysis`). После
установки или обновления приложения выполните
`bench --site your-site.local migrate`, чтобы создался стандартный документ
Page, затем `bench build --app dinext_common`.

**Что сравнивается:**

- JSON fixtures в каждом установленном приложении (`hooks.fixtures` и
  `fixtures/*.json`);
- текущие записи в базе сайта с учётом фильтров fixtures, если они объявлены в
  `hooks.py`.

**Интерфейс:**

1. **Приложения и DocType** — сводные счётчики по приложению и DocType
   (`file_only`, `db_only`, `changed`, `equal`).
2. **Записи** — фильтр по статусу и поиск по имени записи или изменённым путям
   полей.
3. **Детали** — diff по полям; для длинного текста (например, поле `script` в
   `Client Script` / `Server Script`) — построчный diff с номерами строк и
   контекстом.

**Статусы записей:**

| Статус | Значение |
| --- | --- |
| `file_only` | Есть в fixture-файле, нет в БД (будет добавлена при импорте). |
| `db_only` | Есть в БД, нет в fixture-файле. |
| `changed` | Запись есть с обеих сторон, но значения полей различаются. |
| `equal` | Нет существенных отличий после игнорирования служебных полей метаданных. |

Для записей, которые есть в базе, используйте **Open in System**, чтобы перейти
к соответствующей форме Frappe (включая Single DocType).

**Whitelisted API** (используется страницей; та же роль `System Manager`):

- `dinext_common.fixture_analysis_api.get_fixture_analysis_overview`
- `dinext_common.fixture_analysis_api.get_fixture_analysis_records`
- `dinext_common.fixture_analysis_api.get_fixture_analysis_record_detail`

Реализация: `dinext_common/fixture_analysis_api.py` и
`dinext_common/dinext_common/fixture_analysis/` (`discovery.py`,
`diff_engine.py`, `service.py`, `formatters.py`).

### Очистка данных

Подсистема очистки настраивается через единственный документ
`Data Cleanup Rules`. Каждая дочерняя таблица задаёт, включена ли очистка,
сколько дней истории хранить, и фильтры по типу правила.

Типы правил:

- `Version Cleanup Rule`: по возрасту и опционально по reference DocType;
- `Comment Cleanup Rule`: по возрасту, типу комментария и опционально по
  reference DocType;
- `File Cleanup Rule`: по возрасту, типу файла, видимости, папке, размеру,
  привязанному DocType и полю;
- `Communication Cleanup Rule`: по возрасту, типу коммуникации, каналу и
  опционально по reference DocType;
- `Event Cleanup Rule`: по возрасту, категории, типу и статусу события;
- `Workflow Cleanup Rule`: по возрасту, опционально по reference DocType и
  статусу workflow.

Приложение также устанавливает из fixtures включённые Server Scripts:

- `Data Cleanup Daily` — ежедневное `Scheduler Event`;
- `Data Cleanup Version` — API-метод `dinext_common_data_cleanup_version`;
- `Data Cleanup Comment` — API-метод `dinext_common_data_cleanup_comment`;
- `Data Cleanup File` — API-метод `dinext_common_data_cleanup_file`;
- `Data Cleanup Communication` — API-метод `dinext_common_data_cleanup_communication`;
- `Data Cleanup Event` — API-метод `dinext_common_data_cleanup_event`;
- `Data Cleanup Workflow` — API-метод `dinext_common_data_cleanup_workflow`.

`Data Cleanup Daily` читает актуальный документ `Data Cleanup Rules` и ставит
в очередь `long` по одной длительной задаче очистки на каждую включённую
категорию. Скрипты очистки удаляют подходящие записи пакетами с периодическим
commit.

### Подключаемые библиотеки

Автоматически загружаются только библиотеки, нужные самому Dinext Common. Для
остальных предпочтительна ленивая загрузка через `frappe.require()` из
потребляющего приложения.

**DinextTable** — editable-таблица на AG Grid 35 Community. Документация ядра:
[`dinext_common/public/js/table/README.md`](dinext_common/public/js/table/README.md).

```javascript
frappe.require(["dinext-table.bundle.js"], () => {
	DinextTable.create({ container, data, columns, edit: true });
});
```

**Form Conflict Merge** подключается бандлом
`form-conflict-merge.bundle.js`; исходники — в
`dinext_common/public/js/form_conflict_merge/`. Потребляющее приложение
вызывает `dinext_common.formConflictMerge.install(...)`.

**DinextCharts** (`dinext_common/public/js/charts/dinext-charts-core.js`) лениво
загружает ECharts и даёт хелперы панелей, согласованных с темой Desk.

Прочие assets:

```javascript
frappe.require(
	[
		"/assets/dinext_common/js/frappe-gantt.umd.js",
		"/assets/dinext_common/css/frappe-gantt.css",
	],
	function () {
		// Use window.Gantt here.
	}
);
```

```javascript
frappe.require(["/assets/dinext_common/js/echarts.min.js"], function () {
	// Use window.echarts here.
});
```

### План счетов Dinext

`override_doctype_class` для `Company` и `override_whitelisted_methods` для
выбора CoA подставляют шаблон **Dinext** из
`dinext_common/setup/data/coa_importer_template.xlsx`, если компания не
копирует план счетов с существующей.

## 📦 Технологии

- **Backend:** Python 3.10+, Frappe Framework, ERPNext.
- **Frontend:** JavaScript для кастомизаций Desk; CSS/SCSS для общих стилей и
  темы сайта.
- **Таблицы:** AG Grid Community 35 (DinextTable).
- **Данные:** MariaDB или PostgreSQL через Frappe ORM.
- **Сборка пакета:** `flit_core` в `pyproject.toml`.
- **Качество кода:** pre-commit (`ruff`, `eslint`, `prettier`,
  `pre-commit-hooks`).

## 🔧 Конфигурация

Основная конфигурация — в `dinext_common/hooks.py`.

Ключевые hooks и настройки:

- `app_logo_url = "/assets/dinext_common/images/DI_SQ_NBG.png"`
- `app_icon = "/assets/dinext_common/images/DINEXT_FAVICON.ico"`
- `website_context` задаёт favicon и splash для публичного сайта
- `app_include_css` подключает `common.css` и `workspace_sidebar_hover.css`
- `app_include_js` подключает общие скрипты Desk глобально (включая
  `workspace_slug_redirects.js` и `workspace_sidebar_hover.js`)
- `extend_bootinfo = ["dinext_common.boot.extend_bootinfo"]` — передаёт флаг
  `dinext_workspace_sidebar_hover_expand` из `site_config` в Desk и убирает
  `Home` из `allowed_workspaces`
- `after_install = "dinext_common.install.after_install"`
- `after_migrate` — news feed setup и `configure_workspace_menu`
- `doc_events.User.after_insert` →
  `dinext_common.setup.workspace.set_default_workspace_for_new_user`
- `scheduler_events.daily` →
  `dinext_common.changelog_feed.sync_dinext_news_feed`
- `get_changelog_feed = "dinext_common.changelog_feed.get_feed"`
- `doctype_js = {"Project": "public/js/sticky-datatable.js"}`
- `has_permission` для `Dinext Workspace Settings`
- `override_doctype_class` / `override_whitelisted_methods` для CoA Dinext и
  фильтра `Home` в `get_workspace_sidebar_items`

Опции `site_config.json`:

```json
{
  "dinext_workspace_sidebar_hover_expand": 1,
  "dinext_news_feed_url": "https://docs.dinext.ru",
  "dinext_hidden_apps": ["erpnext", "hrms"]
}
```

- `dinext_workspace_sidebar_hover_expand` — включить/выключить hover-expand
  sidebar (по умолчанию включено);
- `dinext_news_feed_url` — base URL publisher News Feed; trailing slash
  снимается; пустое значение = `https://docs.dinext.ru`.
- `dinext_hidden_apps` — полный список имён приложений, скрываемых на странице
  `/apps` и в API списка приложений. Если ключ отсутствует, скрываются
  `erpnext` и `hrms`; значение `[]` не скрывает ни одного приложения. Имя
  соответствует `app_name`, например `crm`, а не видимому заголовку плитки.

После изменения `dinext_hidden_apps` выполните
`bench --site your-site.local migrate` — это назначит `dinext_common`
системным и пользовательским default app, если прежний default пуст или стал
скрытым. Затем выполните `bench --site your-site.local clear-cache` и
перезагрузите Desk. Явный default видимого приложения не перезаписывается.
При Gunicorn с `--preload` перезапустите web worker.

Этот репозиторий не объявляет собственных переменных окружения: параметры
сайта задаются стандартным механизмом Bench/Frappe.

Fixtures, экспортируемые приложением:

- `Website Settings`
- `Navbar Settings`
- `Data Cleanup Rules`
- записи `Web Page` с фильтром по модулю `Dinext Common`
- записи `Client Script` с фильтром по модулю `Dinext Common`
- записи `Server Script` с фильтром по модулю `Dinext Common` и `disabled = 0`
- записи `Custom Field` с фильтром по модулю `Dinext Common`
- `Custom HTML Block` с именами `Dinext Hub`, `Dinext Settings Hub`
- `Holiday List` с именем `Праздники и выходные РФ`

Поведение fixtures:

- `Website Settings` задаёт публичное имя приложения `Dinext`,
  `home_page` = `homepage`, отключает регистрацию, баннер и ссылку на
  `Dinext Theme`;
- `Navbar Settings` задаёт логотип и пункты меню: `Documentation`, `About`,
  `Мои замещения`;
- `Web Page` публикует динамическую главную по маршруту `homepage`;
- `Custom HTML Block` — тонкие адаптеры хабов Dinext / Settings
  (`data-settings-name` + `frappe.require` общего renderer);
- `Data Cleanup Rules` поставляется с правилами хранения по умолчанию: 90 дней
  для version, communication, event, file и workflow, 45 дней для
  специализированных правил comment.

Замечания по совместимости:

- приложение меняет глобальные объекты сайта (`Navbar Settings`,
  `Website Settings`);
- подключает JS в каждую сессию Desk;
- курирует public workspace menu и может скрывать workspace сторонних модулей;
- если другое приложение управляет теми же Single DocType или переопределяет
  то же поведение Desk, согласуйте владение fixtures и порядок загрузки assets.

После изменения workspace/feed-логики выполните
`bench --site your-site.local migrate`. После правок frontend assets —
`bench build --app dinext_common` и
`bench --site your-site.local clear-cache`. После изменения metadata
экспортируйте fixtures:

```bash
bench --site your-site.local export-fixtures
```

## ✅ Требования

- [Bench](https://github.com/frappe/bench) с установленным Frappe.
- Зависимость `required_apps = ["erpnext"]`.
- Python `>=3.10` (закреплено в `pyproject.toml`).
- Совместимые версии Frappe/ERPNext для используемой поставки Dinext.
- Node.js для `bench build`.
- Сайт, на котором можно установить `dinext_common`.
- Включённые scheduler и workers, если нужна автоматическая ежедневная очистка
  и синхронизация News Feed.
- Сетевой доступ consumer-сайта к URL publisher (`dinext_news_feed_url`) для
  What's New.
- Для локальных проверок: pre-commit; для JS-тестов таблиц — Node.js.

Для подсистемы очистки убедитесь, что очередь `long` обслуживается worker:
`Data Cleanup Daily` ставит все задачи очистки в `queue="long"`.

## 🤝 Разработка и сопровождение

Перед любым изменением пройдите обязательный OpenSpec lifecycle из
[AGENTS.md](AGENTS.md). Proposal, design, specs и tasks хранятся в central
Store `dinext-docs` (`openspec/config.yaml` указывает `store: dinext-docs`).
Локальные `openspec/specs` и `openspec/changes` в этом репозитории не
создаются.

Перед коммитами установите и включите pre-commit:

```bash
cd apps/dinext_common
pre-commit install
```

В репозитории настроены проверки:

- валидность JSON, TOML и YAML;
- порядок импортов и форматирование Python через `ruff`;
- форматирование JavaScript через `prettier`;
- линтинг JavaScript через `eslint`;
- базовая гигиена: конфликты слияния, отладочные операторы и т.п.

Дополнительные JS-тесты из корня приложения:

```bash
npm run test:dinext-table
npm run test:form-conflict-merge
```

Python-тесты workspace, news feed, boot, CoA и Fixture Analysis лежат в
`dinext_common/tests/`.

## 📄 Документация

- Документация продукта и платформы: [docs.dinext.ru](https://docs.dinext.ru)
- Navigation stub для агентов: [AGENTS.md](AGENTS.md)
- Точка входа конфигурации приложения: `dinext_common/hooks.py`
- Установка и post-install: `dinext_common/install.py`
- Bootinfo Desk: `dinext_common/boot.py`
- Курирование workspace: `dinext_common/setup/workspace.py`
- Регистрация Hub из domain apps: `dinext_common/setup/hub_catalog.py`
- API хабов: `dinext_common/workspace_hub.py`,
  `dinext_common/workspace_hub_lists.py`,
  `dinext_common/workspace_hub_models.py`
- News Feed publisher/consumer: `dinext_common/changelog_feed.py`
- DocType настроек хаба:
  `dinext_common/dinext_common/doctype/dinext_workspace_settings/`
- DocType новостей: `dinext_common/dinext_common/doctype/dinext_news_feed/`
- Custom HTML Blocks хабов: `dinext_common/fixtures/custom_html_block.json`
- Страница Desk Fixture Analysis:
  `dinext_common/dinext_common/page/fixture_analysis/`
- Backend Fixture Analysis: `dinext_common/dinext_common/fixture_analysis/`
- Схема DocType очистки:
  `dinext_common/dinext_common/doctype/data_cleanup_rules/`
- Определение темы сайта:
  `dinext_common/dinext_common/website_theme/dinext_theme/`
- DinextTable: `dinext_common/public/js/table/README.md`
- Переводы: `dinext_common/translations/ru.csv`
- Тесты: `dinext_common/tests/`

## ❤️ Благодарности

- Dinext — брендинг платформы, общие UX-соглашения и сценарии очистки
- Frappe Framework — платформа приложений, fixtures, hooks Desk и планировщик
- ERPNext — Company / Chart of Accounts, на которые опирается шаблон Dinext
- Встроенные библиотеки: AG Grid Community, Frappe DataTable, HyperList,
  Frappe Gantt, ECharts

## 📝 История изменений

Краткая сводка по текущему состоянию репозитория и недавним коммитам. Полный
журнал — в истории Git конкретной ветки.

### 2026-08-14

- Desk landing: ERPNext `Home` скрыт и исключён из меню (включая Workspace
  Manager); `/app/home` и `/app/workspaces/home` открывают `Dinext`.
- Frequent / Recent Pages — два ряда pill-плашек, Recent сверху; иконки
  Workspace из boot, подпись Workspace — только название; Form-подписи по
  `title_field` или `name`. На записи `Settings` оба чекбокса выключены, на
  `Dinext` остаются включёнными.
- Report-карточки хаба ведут на `/app/query-report/{имя отчёта}`.
- Каталог: Project Management без Task/Issue-списков от Gantt; Scope &
  Governance больше не регистрируется.
- Удалены DocType-колонка Recently Opened, поле `show_recently_opened` и
  whitelist `get_document_titles`.
- Quick Create остаётся кнопками; записи секционных списков — компактными
  строками.

### 2026-08-13

- Секции хаба: `card_columns` — максимум колонок сетки карточек (по умолчанию
  4, для `Settings` — 5); меньше карточек — ряд на всю ширину.
- `Dinext Workspace Settings` — именованные записи `Dinext` и `Settings`
  вместо Single; общий `get_workspace_hub` и renderer в
  `public/js/workspace_hub.js`.
- Settings Hub читает запись `Settings`; domain apps могут расширять
  стандартные записи без нового блока.
- `configure_workspace_menu` выполняется и на `after_migrate`.

### 2026-08-11 — 2026-08-12

- Workspace menu: корневые `Dinext` / `Settings`, скрытие non-Dinext public
  workspace, вложение Settings-детей, `default_workspace` для новых
  пользователей.
- Dinext Hub и Settings Hub: bilingual Custom HTML Blocks и configurable
  карточки через `Dinext Workspace Settings`.
- UI sidebar: left padding основной колонки Workspaces при свёрнутом rail.
- Dinext News Feed: publisher DocType + guest API, consumer sync What's New,
  отключение встроенного Frappe changelog fetch.
- Domain apps: идемпотентная регистрация карточек через `register_hub_items` /
  `register_hub_sections` / `register_hub_doctype_items`.
- Settings Hub: `Website` под Settings и секция Configuration.
- Compact Hub lists: персональные quick-create / assigned / liked / attention
  по секциям с лимитом.

## 🗂️ Структура репозитория

```text
dinext_common/
├── AGENTS.md                         # Navigation stub → central dinext-docs
├── README.md                         # Этот документ
├── license.txt                       # Лицензия MIT
├── pyproject.toml                    # Метаданные пакета, Python и ruff
├── package.json                      # npm-скрипты тестов JS
├── .pre-commit-config.yaml           # Локальные проверки
├── openspec/config.yaml              # Указатель на Store dinext-docs
├── scripts/                          # Сценарии Form Conflict Merge
└── dinext_common/
    ├── hooks.py                      # App configuration, fixtures, Desk hooks
    ├── install.py                    # after_install
    ├── boot.py                       # Desk bootinfo
    ├── changelog_feed.py             # News Feed publisher/consumer
    ├── workspace_hub.py              # Whitelisted API хабов
    ├── workspace_hub_lists.py        # Персональные списки DocType
    ├── workspace_hub_models.py       # TypedDict payload хаба
    ├── fixture_analysis_api.py       # Whitelisted API Fixture Analysis
    ├── modules.txt                   # Имя Desk-модуля
    ├── patches.txt                   # Список миграционных патчей
    ├── patches/                      # Миграция Single → named settings
    ├── fixtures/                     # Экспортированные Frappe metadata
    ├── translations/ru.csv           # Русские переводы
    ├── public/css/                   # Общие стили, hub, sidebar, AG Grid
    ├── public/js/                    # Desk JS, хаб, table, FCM, charts
    ├── public/images/                # Брендинг Dinext
    ├── setup/                        # Workspace menu, hub catalog, CoA
    ├── tests/                        # Python-тесты
    └── dinext_common/
        ├── doctype/                  # Settings, News Feed, cleanup, Workflow Task
        ├── fixture_analysis/         # Discovery и diff fixtures
        ├── page/fixture_analysis/    # Desk Page
        ├── workspace/                # Dinext, Settings
        └── website_theme/            # Dinext Theme
```

Основные части:

- `dinext_common/hooks.py` — метаданные приложения, экспорт fixtures, hooks
  Desk, install/migrate, news feed, JS для Project, пути брендинга.
- `dinext_common/install.py` — post-install: news feed + configure workspace
  menu.
- `dinext_common/setup/workspace.py` — курирование workspace menu и подключение
  hub blocks.
- `dinext_common/setup/hub_catalog.py` — регистрация карточек/секций/DocType-вкладов.
- `dinext_common/setup/company.py` и `chart_of_accounts.py` — шаблон CoA Dinext.
- `dinext_common/public/js/workspace_hub.js` — общий renderer хабов, включая
  списки страниц.
- `dinext_common/public/js/table/` — ядро DinextTable.
- `dinext_common/public/js/form_conflict_merge/` — слияние конфликтов формы.
- `openspec/config.yaml` — pointer на Store; не дублирует specs/changes.

Сгенерированные `public/dist/` в описание текущего устройства не входят.

## 🔗 Схема взаимодействия

Bench загружает `hooks.py`. Fixtures формируют metadata сайта, `after_install`
и `after_migrate` настраивают workspace-меню и News Feed. Domain-приложения
регистрируют карточки хаба в именованных записях настроек. Renderer хаба
добавляет списки страниц из boot и сессионной истории маршрутов.

### Установка и миграция

```mermaid
flowchart LR
  getApp["bench get-app"] --> installApp["bench install-app dinext_common"]
  installApp --> migrate["bench migrate"]
  migrate --> fixtures["Загрузка fixtures"]
  fixtures --> website["Website Settings"]
  fixtures --> navbar["Navbar Settings"]
  fixtures --> homepage["Web Page"]
  fixtures --> hubBlocks["Custom HTML Blocks"]
  fixtures --> cleanupRules["Data Cleanup Rules"]
  fixtures --> serverScripts["Server Scripts"]
  installApp --> afterInstall["after_install"]
  afterInstall --> workspaceMenu["configure_workspace_menu"]
  afterInstall --> newsSetup["setup_dinext_news_feed"]
  migrate --> afterMigrate["after_migrate"]
  afterMigrate --> newsSetup
  afterMigrate --> workspaceMenu
  migrate --> build["bench build"]
  build --> assets["Desk и website assets готовы"]
```

### Dinext Hub

```mermaid
flowchart LR
  install["after_install / after_migrate"] --> configure["configure_workspace_menu"]
  configure --> settings["Dinext Workspace Settings"]
  domainApps["domain apps hub_catalog"] --> settings
  settings --> hubApi["get_workspace_hub"]
  hubApi --> cards["permission-filtered cards"]
  hubApi --> lists["personal DocType lists"]
  hubApi --> flags["page-list flags"]
  cards --> deskHub["Hub renderer"]
  lists --> deskHub
  flags --> deskHub
  boot["frequently_visited_links"] --> deskHub
  history["route_history"] --> deskHub
```

### Dinext News Feed

```mermaid
flowchart LR
  publisher["Dinext News Feed DocType"] --> guestApi["get_published_feed"]
  guestApi --> fetch["consumer get_feed / sync"]
  fetch --> changelog["local Changelog Feed"]
  changelog --> desk["Desk Whats New"]
  installMigrate["install / migrate / daily"] --> sync["sync_dinext_news_feed"]
  sync --> fetch
```

### Fixture Analysis

```mermaid
flowchart LR
  user["Открыть /app/fixture-analysis"] --> overview["get_fixture_analysis_overview"]
  overview --> discover["Поиск приложений и fixture-записей"]
  discover --> compare["Сравнение fixture JSON и БД"]
  compare --> summary["Счётчики app / DocType / record"]
  user --> records["Выбор DocType и фильтров"]
  records --> detail["get_fixture_analysis_record_detail"]
  detail --> fieldDiff["Diff полей и текста"]
  detail --> openForm["Open in System, если запись в БД"]
```

### Ежедневная очистка

```mermaid
flowchart LR
  scheduler["Ежедневный scheduler"] --> dailyScript["Data Cleanup Daily"]
  dailyScript --> rulesDoc["Чтение Data Cleanup Rules"]
  rulesDoc --> versionJob["Очередь: version cleanup"]
  rulesDoc --> commentJob["Очередь: comment cleanup"]
  rulesDoc --> fileJob["Очередь: file cleanup"]
  rulesDoc --> communicationJob["Очередь: communication cleanup"]
  rulesDoc --> eventJob["Очередь: event cleanup"]
  rulesDoc --> workflowJob["Очередь: workflow cleanup"]
  versionJob --> longQueue["Worker очереди long"]
  commentJob --> longQueue
  fileJob --> longQueue
  communicationJob --> longQueue
  eventJob --> longQueue
  workflowJob --> longQueue
  longQueue --> dataStore["Пакетное удаление старых записей"]
```

## 📜 Лицензия

MIT. Текст — в [license.txt](license.txt).
