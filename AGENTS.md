# AGENTS.MD - Руководство по разработке приложений на Frappe Framework

## Оглавление

1. [Введение](#1-введение)
2. [Быстрый старт](#2-быстрый-старт)
3. [Структура приложения](#3-структура-приложения)
4. [Разработка DocTypes](#4-разработка-doctypes)
5. [Серверная разработка (Python)](#5-серверная-разработка-python)
6. [Клиентская разработка (JavaScript)](#6-клиентская-разработка-javascript)
7. [API и веб-сервисы](#7-api-и-веб-сервисы)
8. [Система отчетов](#8-система-отчетов)
9. [Фоновые задачи и планировщик](#9-фоновые-задачи-и-планировщик)
10. [Тестирование](#10-тестирование)
11. [Миграции и патчи](#11-миграции-и-патчи)
12. [Лучшие практики](#12-лучшие-практики)

---

## 1. Введение

Frappe Framework - это full-stack веб-фреймворк на Python и JavaScript для создания бизнес-приложений. Он использует метаданные-ориентированную архитектуру, где DocTypes определяют структуру данных, UI и права доступа.

### Основные концепции

- **Multi-tenancy**: Один код обслуживает множество изолированных сайтов
- **Document ORM**: Объектно-ориентированный доступ к данным через класс Document
- **Metadata-driven**: Определения DocType контролируют схему БД, UI и права
- **Apps**: Модульная архитектура с возможностью установки нескольких приложений
- **Hooks**: Система расширения функциональности без изменения ядра

### Архитектура фреймворка

Frappe следует слоистой архитектуре:
- **WSGI Application** - точка входа HTTP-запросов
- **Core Framework Layer** - инициализация контекста, локальные переменные, hooks
- **Data Layer** - Document ORM, Meta, базовые классы
- **Database Layer** - абстракция базы данных (MariaDB/PostgreSQL)
- **Request Handlers** - обработчики API, форм и веб-страниц

---

## 2. Быстрый старт

### 2.1 Создание нового приложения

Используйте команду `bench` для создания нового приложения:

```bash
cd frappe-bench
bench new-app my_custom_app
```

Команда запросит следующую информацию:
- **App Title** - название приложения
- **App Description** - описание
- **App Publisher** - автор/издатель
- **App Email** - контактный email
- **App License** - лицензия (MIT, GPL, и т.д.)
- **Create GitHub Workflow** - создать CI/CD workflow
- **Branch Name** - название основной ветки

### 2.2 Установка приложения на сайт

```bash
bench --site sitename.local install-app my_custom_app
```

### 2.3 Структура созданного приложения

Команда `make_boilerplate` создает следующую структуру:

```
my_custom_app/
├── my_custom_app/           # Основной модуль приложения
│   ├── __init__.py         # Версия приложения
│   ├── hooks.py            # Конфигурация hooks
│   ├── patches.txt         # Список патчей миграции
│   ├── config/             # Конфигурация Desk
│   ├── public/             # Статические файлы (JS/CSS)
│   ├── templates/          # Jinja2 ExampleCustomer08
│   ├── www/                # Веб-страницы
│   └── my_custom_app/      # Первый модуль
├── pyproject.toml          # Python зависимости и метаданные
├── .pre-commit-config.yaml # Pre-commit hooks для качества кода
├── .gitignore              # Git ignore файл
├── license.txt             # Текст лицензии
└── README.md               # Документация
```

---

## 3. Структура приложения

### 3.1 Файл hooks.py

Это центральный файл конфигурации приложения. Здесь определяются все расширения фреймворка:

Основные категории hooks:

#### Метаданные приложения
- `app_name`, `app_title`, `app_publisher`, `app_description`, `app_email`, `app_license`

#### Assets (JS/CSS)
- `app_include_js` - JS для Desk (используйте только для библиотек, нужных на всех страницах)
- `app_include_css` - CSS для Desk (используйте только для стилей, нужных на всех страницах)
- `web_include_js` - JS для веб-страниц
- `web_include_css` - CSS для веб-страниц

**Важно:** Для большинства случаев предпочтительна динамическая загрузка через `frappe.require()` (см. раздел 6.4) вместо статической загрузки через эти хуки.

#### События документов
```python
doc_events = {
    "User": {
        "before_insert": "my_app.user.before_insert",
        "after_insert": "my_app.user.after_insert",
        "validate": "my_app.user.validate",
    },
    "*": {  # Все DocTypes
        "on_update": "my_app.common.on_update"
    }
}
```

#### Планировщик задач
```python
scheduler_events = {
    "daily": ["my_app.tasks.daily_task"],
    "hourly": ["my_app.tasks.hourly_task"],
    "cron": {
        "0 0 * * *": ["my_app.tasks.midnight_task"]
    }
}
```

#### Права доступа
- `permission_query_conditions` - дополнительные условия запросов
- `has_permission` - кастомная логика проверки прав

### 3.2 Конфигурация pyproject.toml

Определяет метаданные пакета Python, зависимости и настройки инструментов разработки (ruff, pre-commit):

---

## 4. Разработка DocTypes

### 4.1 Создание DocType

Всегда создаем новый DocType в системе с использованием MCP-инструмента create_document. Предварительно необходимо сгенерировать документацию по самому DocType. 

**КРИТИЧЕСКОЕ ПРАВИЛО: В созданном DocType НИКОГДА не указываем индикатор "Custom". Поле name никогда не создаем кастомное, если можно использовать стандартное.**

**КРИТИЧЕСКОЕ ПРАВИЛО: JSON файлы для DocType НИКОГДА не создаются вручную.** DocType создаются ТОЛЬКО через MCP-инструмент `mcp_erpnext_create_document` с `doctype="DocType"`. JSON файлы DocType создаются автоматически Frappe при создании через MCP и последующей миграции. Не предлагайте создание JSON файлов как альтернативный подход.

**Требования перед созданием DocType:**
- Убедитесь, что Developer Mode включен: `bench --site sitename.local set-config developer_mode 1`
- Если Developer Mode не включен, MCP-инструмент вернет ошибку "Not in Developer Mode!"

### 4.2 Controller класс

**КРИТИЧЕСКОЕ ПРАВИЛО: Файлы контроллеров DocType НИКОГДА не создаются вручную без явной команды пользователя.**

Frappe автоматически генерирует базовые контроллеры при создании DocType через UI или миграцию. Создавайте или редактируйте контроллеры только когда:
- Пользователь явно запросил создание/редактирование контроллера
- Необходимо добавить кастомную логику (методы validate, on_update и т.д.)

**ИСКЛЮЧЕНИЕ: Создание DocType через MCP требует предварительного создания базовых контроллеров.**

Когда DocType создается через MCP (не через UI), возникает проблема "курицы и яйца":
- DocType создан в базе данных через MCP
- Миграция (`bench --site sitename.local migrate`) не может выполниться, потому что Python не может импортировать модуль контроллера
- Ошибка: `ImportError: No module named 'app.module.doctype.doctype_name.doctype_name'`

**Решение:** Перед выполнением миграции создайте минимальные файлы контроллера:
```python
# app/module/doctype/doctype_name/__init__.py
# Copyright (c) 2026, App and contributors
# For license information, please see license.txt

# app/module/doctype/doctype_name/doctype_name.py
# Copyright (c) 2026, App and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

class DocTypeName(Document):
	pass
```

После создания базовых контроллеров выполните миграцию, которая завершит настройку DocType.

**Если контроллер отсутствует и DocType не работает после миграции**, это обычно означает, что требуется выполнить миграцию повторно (`bench --site sitename.local migrate`), а не создавать файл вручную.

**Пример контроллера (создается только по явной команде):**

```python
import frappe
from frappe.model.document import Document

class MyDocType(Document):
    def validate(self):
        # Валидация перед сохранением
        pass
    
    def before_insert(self):
        # Действия перед вставкой
        pass
    
    def after_insert(self):
        # Действия после вставки
        pass
    
    def on_update(self):
        # Действия при обновлении
        pass
    
    def on_submit(self):
        # Действия при подтверждении (если is_submittable=1)
        pass
    
    def on_cancel(self):
        # Действия при отмене
        pass
    
    def on_trash(self):
        # Действия перед удалением
        pass
```
### 4.3 Создание записей данных

**КРИТИЧЕСКОЕ ПРАВИЛО: Всегда создаем новые записи данных в системе с использованием MCP-инструмента `mcp_erpnext_create_document`.**

Когда пользователь явно указывает использование MCP-инструментов (например, "С использованием MCP-инструментов"), НЕ используйте Python API (`frappe.get_doc().insert()`) - используйте MCP-инструмент `mcp_erpnext_create_document`.

**Важные особенности MCP-инструмента:**
- Значение `0` для числовых полей может интерпретироваться как отсутствие значения при создании документа. Если требуется создать запись с `value=0`, создайте запись с временным значением (например, `value=1`), затем обновите через `mcp_erpnext_update_document` на `value=0`.
- Перед созданием записей рекомендуется получить информацию о DocType через `mcp_erpnext_get_doctype_info` для проверки обязательных полей и структуры.

**Пример создания записи через MCP:**
```python
# Сначала получаем информацию о DocType
mcp_erpnext_get_doctype_info(doctype="Risk Level")

# Создаем запись
mcp_erpnext_create_document(
    doctype="Risk Level",
    data={
        "name": "Критический",
        "value": 20,
        "enabled": 1,
        "color_light_theme": "#CB2929",
        "color_dark_theme": "#f20707"
    }
)
```

### 4.4 Document ORM API

**ПРИМЕЧАНИЕ:** Python API используется только для внутренней логики приложения, не для создания записей по запросу пользователя, если не указано иное.

Основные операции с документами: 

**Создание документа:**
```python
# Несколько способов создания
doc = frappe.get_doc({"doctype": "My DocType", "title": "Example"})
doc.insert()

# Или через kwargs
doc = frappe.get_doc(doctype="My DocType", title="Example")
doc.insert()
```

**Загрузка документа:**
```python
doc = frappe.get_doc("My DocType", "DOC-001")
```

**Обновление:**
```python
doc.title = "Updated Title"
doc.save()
```

**Удаление:**
```python
frappe.delete_doc("My DocType", "DOC-001")
```

### 4.5 Жизненный цикл документа

Последовательность вызовов при `doc.insert()`:
1. `_set_defaults()` - установка значений по умолчанию
2. `set_user_and_timestamp()` - установка owner, creation
3. `check_permission("create")` - проверка прав
4. `run_method("before_insert")` - hook перед вставкой
5. `set_new_name()` - генерация имени
6. `validate()` - валидация
7. `db_insert()` - вставка в БД
8. Вставка дочерних таблиц
9. `run_method("after_insert")` - hook после вставки

### 4.6 Meta система

Класс `Meta` предоставляет доступ к метаданным DocType:

```python
meta = frappe.get_meta("My DocType")

# Информация о полях
for field in meta.fields:
    print(f"{field.fieldname}: {field.fieldtype}")

# Получить конкретное поле
email_field = meta.get_field("email")

# Проверка типа DocType
if meta.issingle:
    # Одиночный DocType
    pass

if meta.istable:
    # Дочерняя таблица
    pass

# Получить все поля-таблицы
table_fields = meta.get_table_fields()
```

---

## 5. Серверная разработка (Python)

### 5.1 Доступ к базе данных 

**Выполнение SQL запросов:**

```python
# Простой запрос
results = frappe.db.sql("SELECT name FROM tabUser WHERE enabled = %s", (1,))

# С именованными параметрами
results = frappe.db.sql("""
    SELECT name, email 
    FROM tabUser 
    WHERE enabled = %(enabled)s
""", {"enabled": 1}, as_dict=True)

# Query Builder
from frappe.query_builder import DocType
User = DocType("User")
query = frappe.qb.from_(User).select(User.name, User.email).where(User.enabled == 1)
results = query.run(as_dict=True)
```

**Простые операции:**

```python
# Получить значение
email = frappe.db.get_value("User", "user@example.com", "email")

# Получить несколько значений
user_data = frappe.db.get_value("User", "user@example.com", 
                                ["name", "email", "full_name"], as_dict=True)

# Проверить существование
if frappe.db.exists("User", "user@example.com"):
    pass

# Установить значение
frappe.db.set_value("User", "user@example.com", "enabled", 0)

# Получить список
users = frappe.db.get_list("User", 
                           filters={"enabled": 1},
                           fields=["name", "email"],
                           order_by="creation desc",
                           limit=10)
```

### 5.2 DatabaseQuery для сложных запросов 

```python
from frappe.model.db_query import DatabaseQuery

query = DatabaseQuery("User")
results = query.execute(
    fields=["name", "email", "full_name"],
    filters={"enabled": 1, "user_type": "System User"},
    or_filters={"name": ["like", "%admin%"]},
    order_by="creation desc",
    limit_page_length=20,
    limit_start=0,
    as_dict=True
)
```

### 5.3 Управление транзакциями 

```python
# Ручное управление транзакциями
frappe.db.begin()
try:
    doc.insert()
    frappe.db.commit()
except Exception:
    frappe.db.rollback()
    raise

# Savepoints
frappe.db.savepoint("my_savepoint")
try:
    # операции
    frappe.db.release_savepoint("my_savepoint")
except Exception:
    frappe.db.rollback_savepoint("my_savepoint")

# Callback managers
frappe.db.before_commit.add(lambda: print("Before commit"))
frappe.db.after_commit.add(lambda: print("After commit"))
```

### 5.4 Глобальный контекст (frappe.local)

Доступ к глобальным объектам запроса:

```python
# Текущий сайт
site = frappe.local.site

# Конфигурация сайта
db_name = frappe.local.conf.db_name

# Текущий пользователь
user = frappe.session.user  # или frappe.local.session.user

# Параметры запроса
params = frappe.form_dict  # или frappe.local.form_dict

# База данных
db = frappe.db  # или frappe.local.db

# Флаги управления
if frappe.flags.in_test:
    # Код для тестирования
    pass
```

---

## 6. Клиентская разработка (JavaScript)

### 6.1 Клиентские скрипты для форм

Используйте `frappe.ui.form.on()` для добавления логики к формам:

```javascript
frappe.ui.form.on('My DocType', {
    // При загрузке формы
    refresh: function(frm) {
        // Добавить кнопку
        frm.add_custom_button(__('Custom Action'), function() {
            // Действие
        });
        
        // Изменить поле
        frm.set_value('field_name', 'value');
        
        // Скрыть/показать поле
        frm.toggle_display('field_name', true);
        
        // Сделать поле обязательным
        frm.toggle_reqd('field_name', true);
    },
    
    // При изменении поля
    field_name: function(frm) {
        // Логика при изменении поля
    },
    
    // Перед сохранением
    validate: function(frm) {
        // Валидация на клиенте
    },
    
    // Перед отправкой
    before_submit: function(frm) {
        // Действия перед submit
    },
    
    // После сохранения
    after_save: function(frm) {
        // Действия после сохранения
    }
});

// События дочерних таблиц
frappe.ui.form.on('Child Table DocType', {
    // При добавлении строки
    child_table_fieldname_add: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        // Логика для новой строки
    },
    
    // При удалении строки
    child_table_fieldname_remove: function(frm, cdt, cdn) {
        // Логика при удалении
    },
    
    // При изменении поля в строке
    field_name: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        // Логика для изменения поля в строке
    }
});
```

**API грида и форм:** При обращении к объектам `grid`, `frm.fields_dict`, `grid_rows` и т.п. сверяйте имена свойств (например, `grid_custom_buttons`, а не `grid_toolbar`) с исходным кодом Frappe (`frappe/public/js/frappe/form/grid.js`, `grid_row.js`), а не только с планами или примерами из других приложений.

### 6.2 Вызов серверных методов

```javascript
// Вызов whitelisted метода
frappe.call({
    method: 'my_app.api.my_method',
    args: {
        param1: 'value1',
        param2: 'value2'
    },
    callback: function(r) {
        if (!r.exc) {
            console.log(r.message);
        }
    }
});

// Вызов метода документа
frappe.call({
    method: 'my_method',
    doc: frm.doc,
    callback: function(r) {
        frm.reload_doc();
    }
});

// Получить значение
frappe.db.get_value('DocType', 'name', 'fieldname', function(r) {
    console.log(r.message.fieldname);
});

// Получить список
frappe.db.get_list('DocType', {
    fields: ['name', 'field1'],
    filters: {'field1': 'value'},
    limit: 10
}).then(records => {
    console.log(records);
});
```

### 6.3 Диалоги и UI компоненты

```javascript
// Простой диалог
frappe.msgprint('Сообщение пользователю');
frappe.msgprint({
    title: __('Заголовок'),
    message: __('Сообщение'),
    indicator: 'green'
});

// Диалог с полями
let dialog = new frappe.ui.Dialog({
    title: __('Заголовок диалога'),
    fields: [
        {
            fieldtype: 'Data',
            fieldname: 'name',
            label: __('Name'),
            reqd: 1
        },
        {
            fieldtype: 'Select',
            fieldname: 'status',
            label: __('Status'),
            options: ['Open', 'Closed'],
            default: 'Open'
        }
    ],
    primary_action: function(values) {
        console.log(values);
        dialog.hide();
    },
    primary_action_label: __('Submit')
});
dialog.show();

// Подтверждение
frappe.confirm('Вы уверены?', function() {
    // Действие при подтверждении
});

// Prompt
frappe.prompt({
    fieldtype: 'Data',
    label: __('Enter Value'),
    fieldname: 'value'
}, function(values) {
    console.log(values.value);
}, __('Enter Value'));
```

### 6.4 Динамическая загрузка библиотек

**КРИТИЧЕСКОЕ ПРАВИЛО: По возможности ссылки на JS или CSS-файлы не прописываем статично в хуки, а делаем динамическую загрузку через `frappe.require()`.**

Используйте `frappe.require()` для динамической загрузки JavaScript и CSS библиотек вместо статической загрузки через `app_include_js` или `app_include_css` в `hooks.py`.

**Преимущества динамической загрузки:**
- Ленивая загрузка: библиотека загружается только когда нужна
- Лучшая производительность: не загружает библиотеки на всех страницах
- Гибкость: можно загружать библиотеки условно
- Стандартный подход Frappe

**Пример загрузки одиночного JS файла:**

```javascript
// Загрузка ECharts из локального файла
function loadECharts() {
    if (window.echarts) return Promise.resolve();
    return new Promise(function(resolve, reject) {
        frappe.require(['/assets/dinext_projects/js/echarts.min.js'], function() {
            if (window.echarts) {
                resolve();
            } else {
                reject(new Error('Failed to load ECharts'));
            }
        });
    });
}

// Использование
frappe.ui.form.on('My DocType', {
    refresh: function(frm) {
        loadECharts().then(function() {
            // ECharts загружен и доступен как window.echarts
            let chart = echarts.init(document.getElementById('chart'));
            chart.setOption({ /* ... */ });
        });
    }
});
```

**Пример загрузки нескольких файлов:**

```javascript
frappe.require([
    '/assets/dinext_projects/js/library1.js',
    '/assets/dinext_projects/css/library1.css'
], function() {
    // Оба файла загружены
    initializeLibrary();
});
```

**Пример загрузки с использованием async/await:**

```javascript
async function loadLibrary() {
    if (window.myLibrary) return;
    
    await new Promise((resolve, reject) => {
        frappe.require(['/assets/dinext_projects/js/my-library.js'], function() {
            if (window.myLibrary) {
                resolve();
            } else {
                reject(new Error('Library not loaded'));
            }
        });
    });
}

// Использование
async function initFeature() {
    await loadLibrary();
    window.myLibrary.init();
}
```

**Когда использовать статическую загрузку в hooks.py:**
- Библиотека нужна на всех страницах приложения
- Библиотека критична для работы приложения
- Библиотека должна быть доступна глобально с самого начала

**Когда использовать динамическую загрузку:**
- Библиотека нужна только в определенных формах или страницах
- Библиотека большая и не всегда используется
- Библиотека загружается условно в зависимости от данных

### 6.5 Создание страниц

Создайте файл `my_app/my_app/www/my_page.py`:

```python
import frappe

def get_context(context):
    context.title = "My Page"
    context.data = frappe.db.get_list("DocType")
    return context
```

Создайте шаблон `my_app/my_app/www/my_page.html`:

```html
{% extends "templates/web.html" %}

{% block page_content %}
<h1>{{ title }}</h1>
<ul>
    {% for item in data %}
    <li>{{ item.name }}</li>
    {% endfor %}
</ul>
{% endblock %}
```

---

## 7. API и веб-сервисы

### 7.1 Создание API endpoints 

Используйте декоратор `@frappe.whitelist()` для создания API методов:

```python
# В my_app/api.py
import frappe

@frappe.whitelist()
def my_api_method(param1, param2):
    """API метод доступный через /api/method/my_app.api.my_api_method"""
    # Проверка прав
    if not frappe.has_permission("DocType", "read"):
        frappe.throw("No permission")
    
    result = {
        "status": "success",
        "data": process_data(param1, param2)
    }
    return result

@frappe.whitelist(allow_guest=True)
def public_api_method():
    """API метод доступный без аутентификации"""
    return {"message": "Public data"}

@frappe.whitelist(methods=['POST'])
def post_only_method():
    """Метод только для POST запросов"""
    data = frappe.local.form_dict
    return {"received": data}
```

Вызов API:
```bash
# С аутентификацией
curl -X POST http://site/api/method/my_app.api.my_api_method \
  -H "Authorization: token api_key:api_secret" \
  -d '{"param1": "value1", "param2": "value2"}'

# Для гостей
curl http://site/api/method/my_app.api.public_api_method
```

### 7.2 REST API для DocTypes

Frappe автоматически генерирует REST API для всех DocTypes:

```bash
# GET - получить список
GET /api/resource/User?fields=["name","email"]&filters=[["enabled","=",1]]

# GET - получить документ
GET /api/resource/User/user@example.com

# POST - создать документ
POST /api/resource/User
{"email": "new@example.com", "first_name": "Administrator"}

# PUT - обновить документ
PUT /api/resource/User/user@example.com
{"enabled": 0}

# DELETE - удалить документ
DELETE /api/resource/User/user@example.com
```

### 7.3 Обработка запросов

Последовательность обработки запроса:
1. `init_request()` - инициализация контекста запроса
2. `validate_auth()` - проверка аутентификации
3. Маршрутизация к обработчику (API/Handler/Web)
4. Выполнение метода
5. Формирование ответа
6. `after_response` hooks
7. `frappe.destroy()` - очистка

---

## 8. Система отчетов

### 8.1 Query Report

Создайте Report DocType с типом "Query Report":

```sql
SELECT 
    name,
    email,
    creation
FROM tabUser
WHERE enabled = 1
AND creation >= %(from_date)s
ORDER BY creation DESC
```

Определите фильтры в JS файле (`report.js`):

```javascript
frappe.query_reports["My Report"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "reqd": 1
        }
    ]
};
```

### 8.2 Script Report

Создайте Python файл для Script Report:

```python
# my_app/my_app/report/my_script_report/my_script_report.py
import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "name",
            "label": "Name",
            "fieldtype": "Link",
            "options": "User",
            "width": 150
        },
        {
            "fieldname": "email",
            "label": "Email",
            "fieldtype": "Data",
            "width": 200
        }
    ]

def get_data(filters):
    conditions = ""
    if filters.get("enabled"):
        conditions = "AND enabled = 1"
    
    return frappe.db.sql(f"""
        SELECT name, email
        FROM tabUser
        WHERE 1=1 {conditions}
    """, as_dict=1)
```

JavaScript конфигурация:

```javascript
// my_script_report.js
frappe.query_reports["My Script Report"] = {
    "filters": [
        {
            "fieldname": "enabled",
            "label": __("Enabled Only"),
            "fieldtype": "Check",
            "default": 1
        }
    ],
    
    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname == "email" && data.enabled == 0) {
            value = `<span style="color: red;">${value}</span>`;
        }
        return value;
    }
};
``` [17](#0-16) 

---

## 9. Фоновые задачи и планировщик

### 9.1 Постановка задач в очередь [18](#0-17) 

```python
import frappe

# Простая постановка в очередь
frappe.enqueue(
    method='my_app.tasks.long_running_task',
    queue='long',  # 'short', 'default', 'long'
    timeout=3600,  # секунды
    is_async=True,
    job_name='My Long Task',
    param1='value1',
    param2='value2'
)

# Отложенная задача
frappe.enqueue(
    method='my_app.tasks.scheduled_task',
    queue='default',
    enqueue_after_commit=True,  # После commit транзакции
    at_front=False  # В конец очереди
)

# С callback
def callback_function(job):
    print(f"Job {job.id} completed")

frappe.enqueue(
    method='my_app.tasks.my_task',
    queue='default',
    on_success=callback_function
)
```

### 9.2 Планировщик задач

Определите задачи в `hooks.py`:

```python
scheduler_events = {
    # Каждый час
    "hourly": [
        "my_app.tasks.hourly_task"
    ],
    
    # Каждый день в полночь
    "daily": [
        "my_app.tasks.daily_cleanup"
    ],
    
    # Каждую неделю
    "weekly": [
        "my_app.tasks.weekly_report"
    ],
    
    # Каждый месяц
    "monthly": [
        "my_app.tasks.monthly_summary"
    ],
    
    # Cron выражения
    "cron": {
        "0 9 * * *": [  # Каждый день в 9:00
            "my_app.tasks.morning_task"
        ],
        "*/15 * * * *": [  # Каждые 15 минут
            "my_app.tasks.frequent_task"
        ]
    }
}
```

Реализация задач:

```python
# my_app/tasks.py
import frappe

def hourly_task():
    """Задача выполняется каждый час"""
    frappe.logger().info("Hourly task executed")
    # Логика задачи

def daily_cleanup():
    """Ежедневная очистка"""
    frappe.db.sql("""
        DELETE FROM `tabSessions`
        WHERE lastupdate < DATE_SUB(NOW(), INTERVAL 7 DAY)
    """)
    frappe.db.commit()
```

### 9.3 Запуск планировщика

```bash
# Запустить планировщик
bench enable-scheduler

# Проверить статус
bench scheduler status

# Запустить воркеры
bench worker --queue short
bench worker --queue default
bench worker --queue long
```

---

## 10. Тестирование

### 10.1 Структура тестов 

Создайте тестовый файл в модуле DocType:

```python
# my_app/my_app/doctype/my_doctype/test_my_doctype.py
import frappe
import unittest

class TestMyDocType(unittest.TestCase):
    def setUp(self):
        """Настройка перед каждым тестом"""
        # Создать тестовые данные
        pass
    
    def tearDown(self):
        """Очистка после каждого теста"""
        frappe.db.rollback()
    
    def test_validation(self):
        """Тест валидации"""
        doc = frappe.get_doc({
            "doctype": "My DocType",
            "title": "Test"
        })
        doc.insert()
        self.assertEqual(doc.title, "Test")
    
    def test_permission(self):
        """Тест прав доступа"""
        frappe.set_user("test@example.com")
        self.assertRaises(
            frappe.PermissionError,
            frappe.get_doc,
            "My DocType",
            "DOC-001"
        )
    
    def test_api_method(self):
        """Тест API метода"""
        from my_app.api import my_api_method
        result = my_api_method("param1", "param2")
        self.assertEqual(result["status"], "success")
    
    @classmethod
    def setUpClass(cls):
        """Настройка перед всеми тестами класса"""
        pass
    
    @classmethod
    def tearDownClass(cls):
        """Очистка после всех тестов класса"""
        pass
```

### 10.2 Запуск тестов

```bash
# Запустить все тесты приложения
bench --site sitename.local run-tests --app my_app

# Запустить тесты конкретного модуля
bench --site sitename.local run-tests --module my_app.tests.test_module

# Запустить тесты конкретного DocType
bench --site sitename.local run-tests --doctype "My DocType"

# С подробным выводом
bench --site sitename.local run-tests --app my_app --verbose

# Покрытие кода
bench --site sitename.local run-tests --app my_app --coverage
```

### 10.3 Фикстуры и тестовые данные

```python
# Создание тестовых данных
def make_test_records():
    if not frappe.db.exists("My DocType", "TEST-001"):
        doc = frappe.get_doc({
            "doctype": "My DocType",
            "name": "TEST-001",
            "title": "Test Record"
        })
        doc.insert(ignore_permissions=True)

# Использование в тестах
def setUp(self):
    make_test_records()
```

### 10.4 Continuous Integration

При создании приложения с опцией `create_github_workflow=True` создается workflow для автоматического тестирования.

---

## 11. Миграции и патчи

### 11.1 Создание патчей

Патчи используются для изменения данных при миграции:

```python
# my_app/my_app/patches/v1_0/update_status.py
import frappe

def execute():
    """
    Обновить статус всех документов My DocType
    """
    frappe.db.sql("""
        UPDATE `tabMy DocType`
        SET status = 'Active'
        WHERE status IS NULL
    """)
    frappe.db.commit()
```

Добавьте патч в `patches.txt`: 

```
[pre_model_sync]
# Патчи до синхронизации схемы

[post_model_sync]
my_app.patches.v1_0.update_status
my_app.patches.v1_0.migrate_data
```

### 11.2 Изменение схемы

При изменении DocType JSON файла, запустите миграцию:

```bash
bench --site sitename.local migrate
```

Процесс миграции:
1. Выполняет `pre_model_sync` патчи
2. Синхронизирует схему БД с DocType JSON
3. Выполняет `post_model_sync` патчи
4. Запускает `after_migrate` hooks

### 11.3 Fixtures

Для экспорта стандартных данных используйте fixtures в `hooks.py`:

```python
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            ["name", "in", [
                "User-custom_field"
            ]]
        ]
    },
    {
        "doctype": "Property Setter",
        "filters": [
            ["doc_type", "=", "User"]
        ]
    }
]
```

**Фильтр актуальности для скриптов:** при экспорте Client Script и Server Script обязательно добавляйте фильтр по признаку «активен», чтобы в фикстуры не попадали отключённые скрипты:
- **Client Script** — поле `enabled`: только включённые — `["enabled", "=", 1]`
- **Server Script** — поле `disabled`: только не отключённые — `["disabled", "=", 0]`

Пример:
```python
{
    "doctype": "Client Script",
    "filters": [
        ["module", "in", ["Dinext Projects"]],
        ["enabled", "=", 1]
    ]
},
{
    "doctype": "Server Script",
    "filters": [
        ["module", "in", ["Dinext Projects"]],
        ["disabled", "=", 0]
    ]
}
```

**КРИТИЧЕСКОЕ ПРАВИЛО: Файлы фикстур НИКОГДА не создаваются и не редактируются вручную.**

Экспорт фикстур выполняется ТОЛЬКО через команду bench:
```bash
# В WSL окружении (Windows):
wsl
cd /home/username/frappe/bench-name
bench --site sitename.local export-fixtures
```

**Важно:**
- **Экспорт fixtures перезаписывает файлы полностью.** Если вы вручную изменили файл фикстуры (например, исправили `insert_after` для Custom Field), эти изменения будут потеряны при следующем `bench export-fixtures`. Вносите изменения в системе через MCP-инструменты или UI, затем выполняйте `bench export-fixtures` для синхронизации файлов с системой.
- Файлы фикстур (например, `fixtures/doctype_name.json`) создаются автоматически командой `bench export-fixtures`
- Если команда не может быть выполнена через терминал (например, из-за проблем с WSL), предоставьте пользователю точные инструкции для ручного выполнения
- НИКОГДА не создавайте файлы фикстур вручную, даже если команда не может быть выполнена автоматически
- При работе с WSL из Windows: сначала выполните команду `wsl`, затем перейдите в нужную директорию, затем выполните команду bench
- Если экспорт фикстур невозможен автоматически, предоставьте пользователю команду для выполнения, но не создавайте файл вручную

**Перед экспортом фикстур:**
- Убедитесь, что DocType добавлен в список `fixtures` в `hooks.py`:
```python
fixtures = [
    "DocType Name 1",
    "DocType Name 2",
    # ... другие DocType
]
```
- Команда `bench export-fixtures` экспортирует только те DocType, которые указаны в списке `fixtures` в `hooks.py`
- Если DocType не добавлен в список, он не будет экспортирован, даже если содержит данные

**Редактирование кода в фикстурах (Server Script и др.):**
- В исключительных случаях код в фикстуре (например, поле `script` у Server Script) правят напрямую в JSON. После любых правок такого кода **обязательно проверяйте, что код компилируется**: при миграции Frappe вызывает `validate_python_code`; синтаксическая ошибка приведёт к падению `bench migrate`.
- В Python блоки `try` и `except` должны быть на одном уровне отступов; лишний отступ у `except` вызывает `SyntaxError: invalid syntax`.
- При правке кода, хранящегося в JSON (экранированные `\n`, `\t`), надёжнее загрузить JSON, изменить распарсенную строку и сохранить файл (например, скриптом на Python), чем искать и заменять экранированные последовательности в сыром файле.

### 11.4 Чтение системных объектов метаданных

**КРИТИЧЕСКОЕ ПРАВИЛО: Актуальный код клиентских или серверных скриптов всегда смотрим в системе (используем MCP-инструменты). И только если инструменты не доступны или данных в системе нет, то смотрим данные в файлах фикстуры. Аналогично смотрим данные кастомных полей - всегда в первую очередь смотрим в системе с использованием MCP!**

**Принцип источника истины:**
- Системные объекты Frappe (Client Script, Server Script, Custom Field, Property Setter, Print Format и т.д.) могут быть изменены напрямую в системе через UI или API
- Файлы фикстур (`fixtures/*.json`) могут быть устаревшими, так как они синхронизируются только при выполнении `bench export-fixtures`
- **Система всегда является источником истины** для актуального состояния метаданных

**Протокол чтения системных объектов:**

1. **Всегда сначала используйте MCP-инструменты:**
   ```python
   # Для Client Script
   mcp_erpnext_get_document(doctype="Client Script", name="Script Name")
   mcp_erpnext_search_doctype(doctype="Client Script", query="search term")
   
   # Для Custom Field
   mcp_erpnext_get_document(doctype="Custom Field", name="DocType-fieldname")
   mcp_erpnext_search_doctype(doctype="Custom Field", query="fieldname")
   
   # Для Server Script
   mcp_erpnext_get_document(doctype="Server Script", name="Script Name")
   ```

2. **Используйте фикстуры только как fallback:**
   - Если MCP-инструменты недоступны
   - Если объект не найден в системе (новый объект, еще не созданный)
   - Если нужно сравнить текущее состояние с экспортированным

3. **При обновлении системных объектов:**
   - Всегда обновляйте через MCP-инструменты (`mcp_erpnext_update_document`). Если MCP недоступен — вносите изменения в системе через `bench execute` (например: `frappe.get_doc(doctype, name)`; изменить поля; `doc.save()`; `frappe.db.commit()`), затем выполните `bench export-fixtures`.
   - После изменений в системе явно выполните `bench export-fixtures` — фикстуры не обновляются сами.
   - НЕ редактируйте файлы фикстур напрямую — правки перезапишутся при экспорте.

**Примеры системных объектов, требующих MCP-первого подхода:**
- `Client Script` - клиентские скрипты для форм и списков
- `Server Script` - серверные скрипты и API методы
- `Custom Field` - кастомные поля DocType
- `Property Setter` - изменения свойств полей
- `Print Format` - форматы печати
- `Workflow` - рабочие процессы
- `Report` - пользовательские отчеты
- `Dashboard Chart` - графики дашбордов

**Почему это критично:**
- Пользователи могут изменять скрипты и поля через UI, не синхронизируя фикстуры
- Работа с устаревшими данными из фикстур приводит к неправильным изменениям
- MCP-инструменты всегда возвращают актуальное состояние системы

---

## 12. Лучшие практики

### 12.1 Организация кода

**Модульная структура:**
```
my_app/
├── my_app/
│   ├── __init__.py
│   ├── hooks.py
│   ├── api.py              # Публичные API методы
│   ├── tasks.py            # Фоновые задачи
│   ├── utils.py            # Утилиты
│   ├── module_name/        # Модуль
│   │   ├── __init__.py
│   │   └── doctype/
│   │       └── doctype_name/
│   │           ├── doctype_name.py
│   │           ├── doctype_name.json
│   │           ├── doctype_name.js
│   │           └── test_doctype_name.py
```

### 12.2 Безопасность

**Проверка прав:**
```python
# Всегда проверяйте права перед операциями
if not frappe.has_permission("DocType", "write", doc):
    frappe.throw("No permission", frappe.PermissionError)

# Используйте ignore_permissions только в обоснованных случаях
doc.save(ignore_permissions=True)  # Осторожно!
```

**SQL Injection:**
```python
# ПЛОХО - уязвимо к SQL injection
frappe.db.sql(f"SELECT * FROM tabUser WHERE name = '{user_input}'")

# ХОРОШО - используйте параметры
frappe.db.sql("SELECT * FROM tabUser WHERE name = %s", (user_input,))
```

**XSS защита:**
```python
# Экранируйте пользовательский ввод
from frappe.utils import cstr, escape_html
safe_text = escape_html(user_input)
```

### 12.3 Производительность

**Оптимизация запросов:**
```python
# ПЛОХО - N+1 запросов
users = frappe.get_all("User", fields=["name"])
for user in users:
    email = frappe.db.get_value("User", user.name, "email

### Citations

**File:** README.md 
```markdown
## Frappe Framework
Full-stack web application framework that uses Python and MariaDB on the server side and a tightly integrated client side library. Built for ERPNext.

## Philosophy

> The best code is the one that is not written

Started in 2005, Frappe Framework was inspired by the Semantic Web. The "big idea" behind semantic web was of a framework that not only described how information is shown (like headings, body etc), but also what it means, like name, address etc.

By creating a web framework that allowed for easy definition of metadata, it made building complex applications easy. Applications usually designed around how users interact with a system, but not based on semantics of the underlying system. Applications built on semantics end up being much more consistent and extensible. 

The first application built on Framework was ERPNext, a beast with more than 700 object types. Framework is not for the light hearted - it is not the first thing you might want to learn if you are beginning to learn web programming, but if you are ready to do real work, then Framework is the right tool for the job.

### Key Features

- **Full-Stack Framework**: Frappe covers both front-end and back-end development, allowing developers to build complete applications using a single framework.

- **Built-in Admin Interface**: Provides a pre-built, customizable admin dashboard for managing application data, reducing development time and effort.

- **Role-Based Permissions**: Comprehensive user and role management system to control access and permissions within the application.

- **REST API**: Automatically generated RESTful API for all models, enabling easy integration with other systems and services.

- **Customizable Forms and Views**: Flexible form and view customization using server-side scripting and client-side JavaScript.
```

**File:** frappe/utils/boilerplate.py (L23-32)
```python
def make_boilerplate(dest, app_name, no_git=False):
	if not os.path.exists(dest):
		print("Destination directory does not exist")
		return

	# app_name should be in snake_case
	app_name = frappe.scrub(app_name)
	hooks = _get_user_inputs(app_name)
	_create_app_boilerplate(dest, hooks, no_git=no_git)

```

**File:** frappe/utils/boilerplate.py (L136-213)
```python
def _create_app_boilerplate(dest, hooks, no_git=False):
	frappe.create_folder(
		os.path.join(dest, hooks.app_name, hooks.app_name, frappe.scrub(hooks.app_title)),
		with_init=True,
	)
	frappe.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "templates"), with_init=True)
	frappe.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "www"))
	frappe.create_folder(
		os.path.join(dest, hooks.app_name, hooks.app_name, "templates", "pages"), with_init=True
	)
	frappe.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "templates", "includes"))
	frappe.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "config"), with_init=True)
	frappe.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "public", "css"))
	frappe.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "public", "js"))

	# add .gitkeep file so that public folder is committed to git
	# this is needed because if public doesn't exist, bench build doesn't symlink the apps assets
	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "public", ".gitkeep"), "w") as f:
		f.write("")

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "__init__.py"), "w") as f:
		f.write(frappe.as_unicode(init_template))

	with open(os.path.join(dest, hooks.app_name, "pyproject.toml"), "w") as f:
		f.write(frappe.as_unicode(pyproject_template.format(**hooks)))

	with open(os.path.join(dest, hooks.app_name, ".pre-commit-config.yaml"), "w") as f:
		f.write(frappe.as_unicode(precommit_template.format(**hooks)))

	license_body = get_license_text(license_name=hooks.app_license)
	with open(os.path.join(dest, hooks.app_name, "license.txt"), "w") as f:
		f.write(frappe.as_unicode(license_body))

	with open(
		os.path.join(dest, hooks.app_name, hooks.app_name, frappe.scrub(hooks.app_title), ".frappe"), "w"
	) as f:
		f.write("")

	from frappe.deprecation_dumpster import boilerplate_modules_txt

	boilerplate_modules_txt(dest, hooks.app_name, hooks.app_title)

	# These values could contain quotes and can break string declarations
	# So escaping them before setting variables in setup.py and hooks.py
	for key in ("app_publisher", "app_description", "app_license"):
		hooks[key] = hooks[key].replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "hooks.py"), "w") as f:
		f.write(frappe.as_unicode(hooks_template.format(**hooks)))

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "patches.txt"), "w") as f:
		f.write(frappe.as_unicode(patches_template.format(**hooks)))

	app_directory = os.path.join(dest, hooks.app_name)

	copy_from_frappe(".editorconfig", app_directory)
	copy_from_frappe(".eslintrc", app_directory)

	if hooks.create_github_workflow:
		_create_github_workflow_files(dest, hooks)
		hooks.readme_ci_section = readme_ci_section
	else:
		hooks.readme_ci_section = ""

	with open(os.path.join(dest, hooks.app_name, "README.md"), "w") as f:
		f.write(frappe.as_unicode(readme_template.format(**hooks)))

	if not no_git:
		with open(os.path.join(dest, hooks.app_name, ".gitignore"), "w") as f:
			f.write(frappe.as_unicode(gitignore_template.format(app_name=hooks.app_name)))

		# initialize git repository
		app_repo = git.Repo.init(app_directory, initial_branch=hooks.branch_name)
		app_repo.git.add(A=True)
		app_repo.index.commit("feat: Initialize App")

	print(f"'{hooks.app_name}' created at {app_directory}")

```

**File:** frappe/utils/boilerplate.py (L228-238)
```python
PATCH_TEMPLATE = textwrap.dedent(
	'''
	import frappe

	def execute():
		"""{docstring}"""

		# Write your patch here.
		pass
'''
)
```

**File:** frappe/utils/boilerplate.py (L338-397)
```python
pyproject_template = """[project]
name = "{app_name}"
authors = [
    {{ name = "{app_publisher}", email = "{app_email}"}}
]
description = "{app_description}"
requires-python = ">=3.10"
readme = "README.md"
dynamic = ["version"]
dependencies = [
    # "frappe~=15.0.0" # Installed and managed by bench.
]

[build-system]
requires = ["flit_core >=3.4,<4"]
build-backend = "flit_core.buildapi"

# These dependencies are only installed when developer mode is enabled
[tool.bench.dev-dependencies]
# package_name = "~=1.1.0"

[tool.ruff]
line-length = 110
target-version = "py310"

[tool.ruff.lint]
select = [
    "F",
    "E",
    "W",
    "I",
    "UP",
    "B",
    "RUF",
]
ignore = [
    "B017", # assertRaises(Exception) - should be more specific
    "B018", # useless expression, not assigned to anything
    "B023", # function doesn't bind loop variable - will have last iteration's value
    "B904", # raise inside except without from
    "E101", # indentation contains mixed spaces and tabs
    "E402", # module level import not at top of file
    "E501", # line too long
    "E741", # ambiguous variable name
    "F401", # "unused" imports
    "F403", # can't detect undefined names from * import
    "F405", # can't detect undefined names from * import
    "F722", # syntax error in forward type annotation
    "W191", # indentation contains tabs
    "UP030", # Use implicit references for positional format fields (translations)
    "UP031", # Use format specifiers instead of percent format
    "UP032", # Use f-string instead of `format` call (translations)
]
typing-modules = ["frappe.types.DF"]

[tool.ruff.format]
quote-style = "double"
indent-style = "tab"
docstring-code-format = true
"""
```

**File:** frappe/utils/boilerplate.py (L399-646)
```python
hooks_template = """app_name = "{app_name}"
app_title = "{app_title}"
app_publisher = "{app_publisher}"
app_description = "{app_description}"
app_email = "{app_email}"
app_license = "{app_license}"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{{
# 		"name": "{app_name}",
# 		"logo": "/assets/{app_name}/logo.png",
# 		"title": "{app_title}",
# 		"route": "/{app_name}",
# 		"has_permission": "{app_name}.api.permission.has_app_permission"
# 	}}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/{app_name}/css/{app_name}.css"
# app_include_js = "/assets/{app_name}/js/{app_name}.js"

# include js, css files in header of web template
# web_include_css = "/assets/{app_name}/css/{app_name}.css"
# web_include_js = "/assets/{app_name}/js/{app_name}.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "{app_name}/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {{"doctype": "public/js/doctype.js"}}
# webform_include_css = {{"doctype": "public/css/doctype.css"}}

# include js in page
# page_js = {{"page" : "public/js/file.js"}}

# include js in doctype views
# doctype_js = {{"doctype" : "public/js/doctype.js"}}
# doctype_list_js = {{"doctype" : "public/js/doctype_list.js"}}
# doctype_tree_js = {{"doctype" : "public/js/doctype_tree.js"}}
# doctype_calendar_js = {{"doctype" : "public/js/doctype_calendar.js"}}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "{app_name}/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {{
# 	"Role": "home_page"
# }}

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {{
# 	"methods": "{app_name}.utils.jinja_methods",
# 	"filters": "{app_name}.utils.jinja_filters"
# }}

# Installation
# ------------

# before_install = "{app_name}.install.before_install"
# after_install = "{app_name}.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "{app_name}.uninstall.before_uninstall"
# after_uninstall = "{app_name}.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "{app_name}.utils.before_app_install"
# after_app_install = "{app_name}.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "{app_name}.utils.before_app_uninstall"
# after_app_uninstall = "{app_name}.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "{app_name}.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {{
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }}
#
# has_permission = {{
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {{
# 	"*": {{
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}}
# }}

# Scheduled Tasks
# ---------------

# scheduler_events = {{
# 	"all": [
# 		"{app_name}.tasks.all"
# 	],
# 	"daily": [
# 		"{app_name}.tasks.daily"
# 	],
# 	"hourly": [
# 		"{app_name}.tasks.hourly"
# 	],
# 	"weekly": [
# 		"{app_name}.tasks.weekly"
# 	],
# 	"monthly": [
# 		"{app_name}.tasks.monthly"
# 	],
# }}

# Testing
# -------

# before_tests = "{app_name}.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {{
# 	"Task": "{app_name}.custom.task.CustomTaskMixin"
# }}

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {{
# 	"frappe.desk.doctype.event.event.get_events": "{app_name}.event.get_events"
# }}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {{
# 	"Task": "{app_name}.task.get_dashboard_data"
# }}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["{app_name}.utils.before_request"]
# after_request = ["{app_name}.utils.after_request"]

# Job Events
# ----------
# before_job = ["{app_name}.utils.before_job"]
# after_job = ["{app_name}.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{{
# 		"doctype": "{{doctype_1}}",
# 		"filter_by": "{{filter_by}}",
# 		"redact_fields": ["{{field_1}}", "{{field_2}}"],
# 		"partial": 1,
# 	}},
# 	{{
# 		"doctype": "{{doctype_2}}",
# 		"filter_by": "{{filter_by}}",
# 		"partial": 1,
# 	}},
# 	{{
# 		"doctype": "{{doctype_3}}",
# 		"strict": False,
# 	}},
# 	{{
# 		"doctype": "{{doctype_4}}"
# 	}}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"{app_name}.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {{
# 	"Logging DocType Name": 30  # days to retain logs
# }}

"""
```

**File:** frappe/utils/boilerplate.py (L705-812)
```python
github_workflow_template = """name: CI

on:
  push:
    branches:
      - {branch_name}
  pull_request:

concurrency:
  group: {branch_name}-{app_name}-${{{{ github.event.number }}}}
  cancel-in-progress: true

jobs:
  tests:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
    name: Server

    services:
      redis-cache:
        image: redis:alpine
        ports:
          - 13000:6379
      redis-queue:
        image: redis:alpine
        ports:
          - 11000:6379
      mariadb:
        image: mariadb:10.6
        env:
          MYSQL_ROOT_PASSWORD: root
        ports:
          - 3306:3306
        options: --health-cmd="mariadb-admin ping" --health-interval=5s --health-timeout=2s --health-retries=3

    steps:
      - name: Clone
        uses: actions/checkout@v3

      - name: Find tests
        run: |
          echo "Finding tests"
          grep -rn "def test" > /dev/null

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: 18
          check-latest: true

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{{{ runner.os }}}}-pip-${{{{ hashFiles('**/*requirements.txt', '**/pyproject.toml', '**/setup.py', '**/setup.cfg') }}}}
          restore-keys: |
            ${{{{ runner.os }}}}-pip-
            ${{{{ runner.os }}}}-

      - name: Get yarn cache directory path
        id: yarn-cache-dir-path
        run: 'echo "dir=$(yarn cache dir)" >> $GITHUB_OUTPUT'

      - uses: actions/cache@v4
        id: yarn-cache
        with:
          path: ${{{{ steps.yarn-cache-dir-path.outputs.dir }}}}
          key: ${{{{ runner.os }}}}-yarn-${{{{ hashFiles('**/yarn.lock') }}}}
          restore-keys: |
            ${{{{ runner.os }}}}-yarn-

      - name: Install MariaDB Client
        run: |
          sudo apt update
          sudo apt-get install mariadb-client

      - name: Setup
        run: |
          pip install frappe-bench
          bench init --skip-redis-config-generation --skip-assets --python "$(which python)" ~/frappe-bench
          mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "SET GLOBAL character_set_server = 'utf8mb4'"
          mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "SET GLOBAL collation_server = 'utf8mb4_unicode_ci'"

      - name: Install
        working-directory: /home/runner/frappe-bench
        run: |
          bench get-app {app_name} $GITHUB_WORKSPACE
          bench setup requirements --dev
          bench new-site --db-root-password root --admin-password admin test_site
          bench --site test_site install-app {app_name}
          bench build
        env:
          CI: 'Yes'

      - name: Run Tests
        working-directory: /home/runner/frappe-bench
        run: |
          bench --site test_site set-config allow_tests true
          bench --site test_site run-tests --app {app_name}
        env:
          TYPE: server
"""
```

**File:** frappe/utils/boilerplate.py (L814-819)
```python
patches_template = """[pre_model_sync]
# Patches added in this section will be executed before doctypes are migrated
# Read docs to understand patches: https://frappeframework.com/docs/v14/user/en/database-migrations

[post_model_sync]
# Patches added in this section will be executed after doctypes are migrated"""
```

**File:** hooks.md (L3-10)
```markdown
#### Application Name and Details

1. `app_name` - slugified name e.g. "frappe"
1. `app_title` - full title name e.g. "Frappe"
1. `app_publisher`
1. `app_description`
1. `app_version`

```

**File:** hooks.md (L17-24)
```markdown
#### Javascript / CSS Builds

1. `app_include_js` - include in "app"
1. `app_include_css` - assets/frappe/css/splash.css

1. `web_include_js` - assets/js/frappe-web.min.js
1. `web_include_css` - assets/css/frappe-web.css

```

**File:** hooks.md (L33-36)
```markdown
#### Permissions

1. `permission_query_conditions:[doctype]` - method to return additional query conditions at time of report / list etc.
1. `has_permission:[doctype]` - method to call permissions to check at individual level
```

**File:** frappe/model/document.py (L50-143)
```python
@overload
def get_doc(document: "Document", /) -> "Document":
	pass


@overload
def get_doc(doctype: str, /) -> _SingleDocument:
	"""Retrieve Single DocType from DB, doctype must be positional argument."""
	pass


@overload
def get_doc(doctype: str, name: str, /, *, for_update: bool | None = None) -> "Document":
	"""Retrieve DocType from DB, doctype and name must be positional argument."""
	pass


@overload
def get_doc(**kwargs: dict) -> "_NewDocument":
	"""Initialize document from kwargs.
	Not recommended. Use `frappe.new_doc` instead."""
	pass


@overload
def get_doc(documentdict: dict) -> "_NewDocument":
	"""Create document from dict.
	Not recommended. Use `frappe.new_doc` instead."""
	pass


@simple_singledispatch
def get_doc(*args, **kwargs) -> "Document":
	"""Return a `frappe.model.Document` object.

	:param arg1: Document dict or DocType name.
	:param arg2: [optional] document name.
	:param for_update: [optional] select document for update.

	There are multiple ways to call `get_doc`

	        # will fetch the latest user object (with child table) from the database
	        user = get_doc("User", "test@example.com")

	        # create a new object
	        user = get_doc({
	                "doctype":"User"
	                "email_id": "test@example.com",
	                "roles: [
	                        {"role": "System Manager"}
	                ]
	        })

	        # create new object with keyword arguments
	        user = get_doc(doctype='User', email_id='test@example.com')

	        # select a document for update
	        user = get_doc("User", "test@example.com", for_update=True)
	"""
	if not args and kwargs:
		return get_doc_from_dict(kwargs)
	else:
		raise ValueError("First non keyword argument must be a string or dict")


@get_doc.register(BaseDocument)
def _basedoc(doc: BaseDocument, *args, **kwargs) -> "Document":
	return doc


@get_doc.register(str)
def get_doc_str(doctype: str, name: str | None = None, **kwargs) -> "Document":
	# if no name: it's a single
	controller = get_controller(doctype)
	if controller:
		return controller(doctype, name, **kwargs)

	raise ImportError(doctype)


@get_doc.register(MappingProxyType)  # global test record
def get_doc_from_mapping_proxy(data: MappingProxyType, **kwargs) -> "Document":
	return get_doc_from_dict(dict(data), **kwargs)


@get_doc.register(dict)
def get_doc_from_dict(data: dict[str, Any], **kwargs) -> "Document":
	if "doctype" not in data:
		raise ValueError('"doctype" is a required key')
	controller = get_controller(data["doctype"])
	if controller:
		return controller(**data)
	raise ImportError(data["doctype"])

```

**File:** frappe/model/document.py (L380-469)
```python
	def insert(
		self,
		ignore_permissions=None,
		ignore_links=None,
		ignore_if_duplicate=False,
		ignore_mandatory=None,
		set_name=None,
		set_child_names=True,
	) -> "Self":
		"""Insert the document in the database (as a new document).
		This will check for user permissions and execute `before_insert`,
		`validate`, `on_update`, `after_insert` methods if they are written.

		:param ignore_permissions: Do not check permissions if True.
		:param ignore_links: Do not check validity of links if True.
		:param ignore_if_duplicate: Do not raise error if a duplicate entry exists.
		:param ignore_mandatory: Do not check missing mandatory fields if True.
		:param set_name: Name to set for the document, if valid.
		:param set_child_names: Whether to set names for the child documents.
		"""
		if self.flags.in_print:
			return self

		self.flags.notifications_executed = []

		if ignore_permissions is not None:
			self.flags.ignore_permissions = ignore_permissions

		if ignore_links is not None:
			self.flags.ignore_links = ignore_links

		if ignore_mandatory is not None:
			self.flags.ignore_mandatory = ignore_mandatory

		self.set("__islocal", True)

		self._set_defaults()
		self.set_user_and_timestamp()
		self.set_docstatus()
		self.check_if_latest()
		self._validate_links()
		self.check_permission("create")
		self.run_method("before_insert")
		self.set_new_name(set_name=set_name, set_child_names=set_child_names)
		self.set_parent_in_children()
		self.validate_higher_perm_levels()

		self.flags.in_insert = True
		self.run_before_save_methods()
		self._validate()
		self.set_docstatus()
		self.flags.in_insert = False

		# run validate, on update etc.

		# parent
		if getattr(self.meta, "issingle", 0):
			self.update_single(self.get_valid_dict())
		else:
			self.db_insert(ignore_if_duplicate=ignore_if_duplicate)

		# children
		if not getattr(self.meta, "is_virtual", False):
			for d in self.get_all_children():
				d.db_insert()

		self.reset_computed_child_tables()
		self.run_method("after_insert")
		self.flags.in_insert = True

		if self.get("amended_from"):
			self.validate_amended_from()
			self.copy_attachments_from_amended_from()

		relink_mismatched_files(self)
		self.run_post_save_methods()
		self.flags.in_insert = False

		# delete __islocal
		if hasattr(self, "__islocal"):
			delattr(self, "__islocal")

		# clear unsaved flag
		if hasattr(self, "__unsaved"):
			delattr(self, "__unsaved")

		if not (frappe.flags.in_migrate or frappe.local.flags.in_install or frappe.flags.in_setup_wizard):
			if frappe.get_cached_value("User", frappe.session.user, "follow_created_documents"):
				follow_document(self.doctype, self.name, frappe.session.user)
		return self
```

**File:** frappe/database/database.py (L182-340)
```python
	def sql(
		self,
		query: Query,
		values: QueryValues = EmptyQueryValues,
		*,
		as_dict=0,
		as_list=0,
		debug=0,
		ignore_ddl=0,
		auto_commit=0,
		update=None,
		explain=False,
		run=True,
		pluck=False,
		as_iterator=False,
	):
		"""Execute a SQL query and fetch all rows.

		:param query: SQL query.
		:param values: Tuple / List / Dict of values to be escaped and substituted in the query.
		:param as_dict: Return as a dictionary.
		:param as_list: Always return as a list.
		:param debug: Print query and `EXPLAIN` in debug log.
		:param ignore_ddl: Catch exception if table, column missing.
		:param auto_commit: Commit after executing the query.
		:param update: Update this dict to all rows (if returned `as_dict`).
		:param run: Return query without executing it if False.
		:param pluck: Get the plucked field only.
		:param explain: Print `EXPLAIN` in error log.
		:param as_iterator: Returns iterator over results instead of fetching all results at once.
		        This should be used with unbuffered cursor as default cursors used by pymysql and postgres
		        buffer the results internally. See `Database.unbuffered_cursor`.
		Examples:

		        # return customer names as dicts
		        frappe.db.sql("select name from tabCustomer", as_dict=True)

		        # return names beginning with a
		        frappe.db.sql("select name from tabCustomer where name like %s", "a%")

		        # values as dict
		        frappe.db.sql("select name from tabCustomer where name like %(name)s and owner=%(owner)s",
		                {"name": "a%", "owner":"Administrator"})

		"""
		if isinstance(query, QueryBuilder):
			frappe.log("Use run method to execute SQL queries generated by Query Builder")

		debug = debug or getattr(self, "debug", False)
		query = str(query)

		if not run:
			return query

		query_type = get_query_type(query)

		if explain:
			if debug and query_type == "select":
				self.explain_query(query, values)
			return

		# remove whitespace / indentation from start and end of query
		# and replace ifnull in query with coalesce
		query = IFNULL_PATTERN.sub("coalesce(", query.strip())

		if not self._conn:
			self.connect()

		# in transaction validations
		self.check_transaction_status(query, query_type)
		self.clear_db_table_cache(query_type)

		if auto_commit:
			self.commit()

		if debug:
			time_start = time()

		if values == EmptyQueryValues:
			values = None
		elif not isinstance(values, ALLOWED_TYPES_FOR_VALUES):
			values = (values,)

		query, values = self._transform_query(query, values)

		if trace_id := get_trace_id():
			query += f" /* FRAPPE_TRACE_ID: {trace_id} */"

		try:
			self.execute_query(query, values)
		except Exception as e:
			if self.is_syntax_error(e):
				frappe.log(f"Syntax error in query:\n{query} {values or ''}")

			elif self.is_deadlocked(e):
				raise frappe.QueryDeadlockError(e) from e

			elif self.is_timedout(e):
				raise frappe.QueryTimeoutError(e) from e

			elif self.is_read_only_mode_error(e):
				frappe.throw(
					_(
						"Site is running in read only mode for maintenance or site update, this action can not be performed right now. Please try again later."
					),
					title=_("In Read Only Mode"),
					exc=frappe.InReadOnlyMode,
				)

			# TODO: added temporarily
			elif self.db_type == "postgres":
				traceback.print_stack()
				frappe.log(f"Error in query:\n{e}")
				raise

			elif isinstance(e, self.ProgrammingError):
				if frappe.conf.developer_mode:
					traceback.print_stack()
					frappe.log(f"Error in query:\n{query, values}")
				raise

			if not (
				ignore_ddl
				and (self.is_missing_column(e) or self.is_table_missing(e) or self.cant_drop_field_or_key(e))
			):
				raise

		self.log_query(query, query_type, values, debug)
		if debug:
			time_end = time()
			frappe.log(f"Execution time: {(time_end - time_start) * 1000:.3f} ms")

		if auto_commit:
			self.commit()

		if not self._cursor.description:
			return ()

		if as_iterator:
			return self._return_as_iterator(pluck=pluck, as_dict=as_dict, as_list=as_list, update=update)

		last_result = self._transform_result(self._cursor.fetchall())
		if pluck:
			last_result = [r[0] for r in last_result]
			self._clean_up()
			return last_result

		# scrub output if required
		if as_dict:
			last_result = self.fetch_as_dict(last_result)
			if update:
				for r in last_result:
					r.update(update)

		elif as_list:
			last_result = self.convert_to_lists(last_result)

		self._clean_up()
		return last_result
```

**File:** frappe/database/database.py (L1077-1163)
```python
		        "field2": "value2",
		        ...
		    },
		    "docname2": {
		        "field1": "value1",
		        "field2": "value2",
		        ...
		    },
		}
		```

		---

		Query will be built as:
		```sql
		UPDATE `tabItem`
		SET `status` = CASE
		    WHEN `name` = 'Item-1' THEN 'Close'
		    WHEN `name` = 'Item-2' THEN 'Open'
		    WHEN `name` = 'Item-3' THEN 'Close'
		    WHEN `name` = 'Item-4' THEN 'Cancelled'
		    ELSE `status`
		end,
		`description` = CASE
		    WHEN `name` = 'Item-1' THEN 'This is the first task'
		    WHEN `name` = 'Item-2' THEN 'This is the second task'
		    WHEN `name` = 'Item-3' THEN 'This is the third task'
		    WHEN `name` = 'Item-4' THEN 'This is the fourth task'
		    ELSE `description`
		end
		WHERE  `name` IN ( 'Item-1', 'Item-2', 'Item-3', 'Item-4' )
		```
		"""
		if not doc_updates:
			return

		dt = frappe.qb.DocType(doctype)
		update_query = frappe.qb.update(dt)

		conditions = {}
		docnames = list(doc_updates.keys())

		for docname, row in doc_updates.items():
			for field, value in row.items():
				# CASE
				if field not in conditions:
					conditions[field] = Case()

				# WHEN
				conditions[field].when(dt.name == docname, value)

		for field in conditions:
			# ELSE
			update_query = update_query.set(dt[field], conditions[field].else_(dt[field]))

		if modified_dict:
			for column, value in modified_dict.items():
				update_query = update_query.set(dt[column], value)

		update_query.where(dt.name.isin(docnames)).run(debug=debug)

	def set_global(self, key, val, user="__global"):
		"""Save a global key value. Global values will be automatically set if they match fieldname."""
		self.set_default(key, val, user)

	def get_global(self, key, user="__global"):
		"""Return a global key value."""
		return self.get_default(key, user)

	def get_default(self, key, parent="__default"):
		"""Return default value as a list if multiple or single."""
		d = self.get_defaults(key, parent)
		return (isinstance(d, list) and d[0]) or d

	@staticmethod
	def set_default(key, val, parent="__default", parenttype=None):
		"""Sets a global / user default value."""
		frappe.defaults.set_default(key, val, parent, parenttype)

	@staticmethod
	def add_default(key, val, parent="__default", parenttype=None):
		"""Append a default value for a key, there can be multiple default values for a particular key."""
		frappe.defaults.add_default(key, val, parent, parenttype)

	@staticmethod
	def get_defaults(key=None, parent="__default"):
		"""Get all defaults"""
```

**File:** frappe/model/db_query.py (L73-245)
```python
class DatabaseQuery:
	def __init__(self, doctype, user=None):
		self.doctype = doctype
		self.tables = []
		self.link_tables = []
		self.linked_table_aliases = {}
		self.linked_table_counter = Counter()
		self.conditions = []
		self.or_conditions = []
		self.fields = None
		self.user = user or frappe.session.user
		self.ignore_ifnull = False
		self.flags = frappe._dict()
		self.reference_doctype = None
		self.permission_map = {}
		self.shared = []
		self._fetch_shared_documents = False
		self._metas = {}

	@cached_property
	def doctype_meta(self):
		return self.get_meta(self.doctype)

	def get_meta(self, doctype: str):
		if doctype not in self._metas:
			self._metas[doctype] = frappe.get_meta(doctype)
		return self._metas[doctype]

	@property
	def query_tables(self):
		return self.tables + [d.table_alias for d in self.link_tables]

	def execute(
		self,
		fields=None,
		filters: FilterSignature | str | None = None,
		or_filters: FilterSignature | None = None,
		docstatus=None,
		group_by=None,
		order_by=DefaultOrderBy,
		limit_start=False,
		limit_page_length=None,
		as_list=False,
		with_childnames=False,
		debug=False,
		ignore_permissions=False,
		user=None,
		with_comment_count=False,
		join="left join",
		distinct=False,
		start=None,
		page_length=None,
		limit=None,
		ignore_ifnull=False,
		save_user_settings=False,
		save_user_settings_fields=False,
		update=None,
		user_settings=None,
		reference_doctype=None,
		run=True,
		strict=True,
		pluck=None,
		ignore_ddl=False,
		*,
		parent_doctype=None,
	) -> list:
		self.user = user or frappe.session.user

		if not ignore_permissions:
			self.check_read_permission(self.doctype, parent_doctype=parent_doctype)

		# filters and fields swappable
		# its hard to remember what comes first
		if isinstance(fields, dict) or (fields and isinstance(fields, list) and isinstance(fields[0], list)):
			# if fields is given as dict/list of list, its probably filters
			filters, fields = fields, filters

		elif fields and isinstance(filters, list) and len(filters) > 1 and isinstance(filters[0], str):
			# if `filters` is a list of strings, its probably fields
			filters, fields = fields, filters

		if fields:
			self.fields = fields
		else:
			self.fields = [f"`tab{self.doctype}`.`{pluck or 'name'}`"]

		if start:
			limit_start = start
		if page_length:
			limit_page_length = page_length
		if limit:
			limit_page_length = limit
		if as_list and not isinstance(self.fields, (Sequence | str)) and len(self.fields) > 1:
			frappe.throw(_("Fields must be a list or tuple when as_list is enabled"))

		self.filters: Filters
		self.or_filters: Filters
		for k, _filters in {
			"filters": filters or Filters(),
			"or_filters": or_filters or Filters(),
		}.items():
			if isinstance(_filters, str):
				_filters = json.loads(_filters)
			if not isinstance(_filters, Filters):
				_filters = Filters(_filters, doctype=self.doctype)
			setattr(self, k, _filters)

		self.docstatus = docstatus or []
		self.group_by = group_by
		self.order_by = order_by
		self.limit_start = cint(limit_start)
		self.limit_page_length = cint(limit_page_length) if limit_page_length else None
		self.with_childnames = with_childnames
		self.debug = debug
		self.join = join
		self.distinct = distinct
		self.as_list = as_list
		self.ignore_ifnull = ignore_ifnull
		self.flags.ignore_permissions = ignore_permissions
		self.update = update
		self.user_settings_fields = copy.deepcopy(self.fields)
		self.run = run
		self.strict = strict
		self.ignore_ddl = ignore_ddl
		self.parent_doctype = parent_doctype

		# for contextual user permission check
		# to determine which user permission is applicable on link field of specific doctype
		self.reference_doctype = reference_doctype or self.doctype

		if user_settings:
			self.user_settings = json.loads(user_settings)

		if is_virtual_doctype(self.doctype):
			from frappe.model.base_document import get_controller

			controller = get_controller(self.doctype)
			if not hasattr(controller, "get_list"):
				return []

			self.parse_args()
			kwargs = {
				"as_list": as_list,
				"with_comment_count": with_comment_count,
				"save_user_settings": save_user_settings,
				"save_user_settings_fields": save_user_settings_fields,
				"pluck": pluck,
				"parent_doctype": parent_doctype,
			} | self.__dict__
			return frappe.call(controller.get_list, args=kwargs, **kwargs)

		self.columns = self.get_table_columns()

		# no table & ignore_ddl, return
		if not self.columns:
			return []

		result = self.build_and_run()

		if sbool(with_comment_count) and not as_list and self.doctype:
			self.add_comment_count(result)

		if save_user_settings:
			self.save_user_settings_fields = save_user_settings_fields
			self.update_user_settings()

		if pluck:
			return [d[pluck] for d in result]

		if self.doctype and result:
			result = self.mask_fields(result)

		return result
```

**File:** frappe/__init__.py (L73-142)
```python
controllers: dict[str, type] = {}
lazy_controllers: dict[str, type] = {}
local = Local()
cache: Optional["RedisWrapper"] = None
client_cache: Optional["ClientCache"] = None
STANDARD_USERS = ("Guest", "Administrator")

# this global may be subsequently changed by frappe.tests.utils.toggle_test_mode()
in_test = False

_dev_server = int(sbool(os.environ.get("DEV_SERVER", False)))

if _dev_server:
	warnings.simplefilter("always", DeprecationWarning)
	warnings.simplefilter("always", PendingDeprecationWarning)


# local-globals
ConfType: TypeAlias = _dict[str, Any]  # type: ignore[no-any-explicit]
# TODO: make session a dataclass instead of undtyped _dict
SessionType: TypeAlias = _dict[str, Any]  # type: ignore[no-any-explicit]
# TODO: implement dataclass
LogMessageType: TypeAlias = _dict[str, Any]  # type: ignore[no-any-explicit]
# TODO: implement dataclass
# holds job metadata if the code is run in a background job context
JobMetaType: TypeAlias = _dict[str, Any]  # type: ignore[no-any-explicit]
ResponseDict: TypeAlias = _dict[str, Any]  # type: ignore[no-any-explicit]
FlagsDict: TypeAlias = _dict[str, Any]  # type: ignore[no-any-explicit]
FormDict: TypeAlias = _dict[str, str]

db: LocalProxy[Union["PyMariaDBDatabase", "MariaDBDatabase", "PostgresDatabase", "SQLiteDatabase"]] = local(
	"db"
)
qb: LocalProxy[Union["MariaDB", "Postgres", "SQLite"]] = local("qb")
conf: LocalProxy[ConfType] = local("conf")
form_dict: LocalProxy[FormDict] = local("form_dict")
form = form_dict
request: LocalProxy["Request"] = local("request")
job: LocalProxy[JobMetaType] = local("job")
response: LocalProxy[ResponseDict] = local("response")
session: LocalProxy[SessionType] = local("session")
user: LocalProxy[str] = local("user")
flags: LocalProxy[FlagsDict] = local("flags")

error_log: LocalProxy[list[dict[str, str]]] = local("error_log")
debug_log: LocalProxy[list[str]] = local("debug_log")
message_log: LocalProxy[list[LogMessageType]] = local("message_log")

lang: LocalProxy[str] = local("lang")

if TYPE_CHECKING:  # pragma: no cover
	# trick because some type checkers fail to follow "RedisWrapper", etc (written as string literal)
	# trough a generic wrapper; seems to be a bug
	db: PyMariaDBDatabase | MariaDBDatabase | PostgresDatabase | SQLiteDatabase
	qb: MariaDB | Postgres
	conf: ConfType
	form_dict: FormDict
	request: Request
	job: JobMetaType
	response: ResponseDict
	session: SessionType
	user: str
	flags: FlagsDict

	error_log: list[dict[str, str]]
	debug_log: list[str]
	message_log: list[LogMessageType]

	lang: str

```

**File:** frappe/__init__.py (L420-476)
```python
def whitelist(allow_guest=False, xss_safe=False, methods=None):
	"""
	Decorator for whitelisting a function and making it accessible via HTTP.
	Standard request will be `/api/method/[path.to.method]`

	:param allow_guest: Allow non logged-in user to access this method.
	:param methods: Allowed http method to access the method.

	Use as:

	        @frappe.whitelist()
	        def myfunc(param1, param2):
	                pass
	"""

	if not methods:
		methods = ["GET", "POST", "PUT", "DELETE"]

	def innerfn(fn):
		from frappe.utils.typing_validations import validate_argument_types

		global whitelisted, guest_methods, xss_safe_methods, allowed_http_methods_for_whitelisted_func

		# validate argument types if request is present or in test context
		fn = validate_argument_types(fn, apply_condition=_in_request_or_test)

		whitelisted.add(fn)
		allowed_http_methods_for_whitelisted_func[fn] = methods

		if allow_guest:
			guest_methods.add(fn)

			if xss_safe:
				xss_safe_methods.add(fn)

		return fn

	return innerfn


def is_whitelisted(method):
	from frappe.utils import sanitize_html

	is_guest = session["user"] == "Guest"
	if method not in whitelisted or (is_guest and method not in guest_methods):
		summary = _("You are not permitted to access this resource. Login to access")
		detail = _("Function {0} is not whitelisted.").format(bold(f"{method.__module__}.{method.__name__}"))
		msg = f"<details><summary>{summary}</summary>{detail}</details>"
		throw(msg, PermissionError, title=_("Method Not Allowed"))

	if is_guest and method not in xss_safe_methods:
		# strictly sanitize form_dict
		# escapes html characters like <> except for predefined tags like a, b, ul etc.
		for key, value in form_dict.items():
			if isinstance(value, str):
				form_dict[key] = sanitize_html(value)

```

**File:** frappe/app.py (L96-140)
```python
@after_response_wrapper
@Request.application
def application(request: Request):
	response = None

	try:
		init_request(request)

		validate_auth()

		if request.method == "OPTIONS":
			response = Response()

		elif frappe.form_dict.cmd:
			from frappe.deprecation_dumpster import deprecation_warning

			deprecation_warning(
				"unknown",
				"v17",
				f"{frappe.form_dict.cmd}: Sending `cmd` for RPC calls is deprecated, call REST API instead `/api/method/cmd`",
			)
			frappe.handler.handle()
			response = frappe.utils.response.build_response("json")

		elif request.path.startswith("/api/"):
			response = frappe.api.handle(request)

		elif request.path.startswith("/backups"):
			response = frappe.utils.response.download_backup(request.path)

		elif request.path.startswith("/private/files/"):
			response = frappe.utils.response.download_private_file(request.path)

		elif request.path.startswith("/.well-known/") and request.method == "GET":
			response = handle_wellknown(request.path)

		elif request.method in ("GET", "HEAD", "POST"):
			response = get_response()

		else:
			raise NotFound

	except Exception as e:
		response = e.get_response(request.environ) if isinstance(e, HTTPException) else handle_exception(e)
		if db := getattr(frappe.local, "db", None):
```

**File:** frappe/core/doctype/report/report.py (L1-50)
```python
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
import datetime
import json
import threading

import frappe
import frappe.desk.query_report
from frappe import _, scrub
from frappe.core.doctype.custom_role.custom_role import get_custom_allowed_roles
from frappe.core.doctype.page.page import delete_custom_role
from frappe.desk.reportview import append_totals_row
from frappe.model.document import Document
from frappe.modules import make_boilerplate
from frappe.modules.export_file import export_to_files
from frappe.utils import cint, cstr
from frappe.utils.safe_exec import check_safe_sql_query, safe_exec


class Report(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.core.doctype.has_role.has_role import HasRole
		from frappe.core.doctype.report_column.report_column import ReportColumn
		from frappe.core.doctype.report_filter.report_filter import ReportFilter
		from frappe.types import DF

		add_total_row: DF.Check
		add_translate_data: DF.Check
		columns: DF.Table[ReportColumn]
		disabled: DF.Check
		filters: DF.Table[ReportFilter]
		is_standard: DF.Literal["No", "Yes"]
		javascript: DF.Code | None
		json: DF.Code | None
		letter_head: DF.Link | None
		module: DF.Link | None
		prepared_report: DF.Check
		query: DF.Code | None
		ref_doctype: DF.Link
		reference_report: DF.Data | None
		report_name: DF.Data
		report_script: DF.Code | None
		report_type: DF.Literal["Report Builder", "Query Report", "Script Report", "Custom Report"]
		roles: DF.Table[HasRole]
		timeout: DF.Int
```

**File:** frappe/utils/background_jobs.py (L1-50)
```python
import os
import random
import signal
import socket
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from functools import lru_cache
from threading import Thread
from typing import Any, NoReturn
from uuid import uuid4

import redis
from redis.exceptions import BusyLoadingError, ConnectionError
from rq import Callback, Queue, Worker
from rq.defaults import DEFAULT_WORKER_TTL
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import Job, JobStatus
from rq.logutils import setup_loghandlers
from rq.timeouts import JobTimeoutException
from rq.worker import DequeueStrategy, StopRequested, WorkerStatus
from rq.worker_pool import WorkerPool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

import frappe
import frappe.monitor
from frappe import _
from frappe.utils import CallbackManager, cint, get_bench_id, get_sites
from frappe.utils.caching import site_cache
from frappe.utils.commands import log
from frappe.utils.data import sbool
from frappe.utils.redis_queue import RedisQueue

# TTL to keep RQ job logs in redis for.
RQ_JOB_FAILURE_TTL = 7 * 24 * 60 * 60  # 7 days instead of 1 year (default)
RQ_FAILED_JOBS_LIMIT = 1000  # Only keep these many recent failed jobs around
RQ_RESULTS_TTL = 10 * 60

RQ_MAX_JOBS = 5000  # Restart NOFORK workers after every N number of jobs
RQ_MAX_JOBS_JITTER = 50  # Random difference in max jobs to avoid restarting at same time

MAX_QUEUED_JOBS = 500  # frappe.enqueue will start failing when these many jobs exist in queue.
# When too many jobs are pending in queue, order can be selectively flipped to LIFO to give better
# response latencies to interactive jobs.
QUEUE_STARVATION_THRESHOLD = 16


_redis_queue_conn = None

```

**File:** frappe/utils/scheduler.py (L1-50)
```python
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
"""
Events:
	always
	daily
	monthly
	weekly
"""

import datetime
import os
import random
import time
from typing import NoReturn

from croniter import CroniterBadCronError
from filelock import FileLock, Timeout

import frappe
from frappe.utils import cint, get_bench_path, get_datetime, get_sites, now_datetime
from frappe.utils.background_jobs import set_niceness
from frappe.utils.caching import redis_cache

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_SCHEDULER_TICK = 4 * 60


def cprint(*args, **kwargs):
	"""Prints only if called from STDOUT"""
	try:
		os.get_terminal_size()
		print(*args, **kwargs)
	except Exception:
		pass


def start_scheduler() -> NoReturn:
	"""Run enqueue_events_for_all_sites based on scheduler tick.
	Specify scheduler_tick_interval in seconds in common_site_config.json"""

	tick = get_scheduler_tick()
	set_niceness()

	lock_path = _get_scheduler_lock_file()

	try:
		lock = FileLock(lock_path)
		lock.acquire(blocking=False)
	except Timeout:
```

**File:** frappe/testing/README.md (L1-37)
```markdown
# Frappe Testing Module

This module provides a comprehensive framework for running tests in Frappe applications. It includes functionality for test discovery, execution, result reporting, and environment setup.

## Key Components

- `TestConfig`: Configuration class for customizing test execution
- `TestRunner`: Main class for running test suites with additional Frappe-specific functionality
- `TestResult`: Custom test result class for improved output formatting and logging
- `discover_all_tests`: Function to discover all tests in specified Frappe apps
- `discover_doctype_tests`: Function to discover tests for specific DocTypes
- `discover_module_tests`: Function to discover tests in specific modules

## Usage

This module is typically used by Frappe's CLI commands for running tests, but can also be used programmatically for custom test execution scenarios.

For detailed information about each component, please refer to the well-commented code in the following files:

- [`__init__.py`](./__init__.py): Module initialization and logging setup
- [`runner.py`](./runner.py): TestRunner class and test execution logic
- [`discovery.py`](./discovery.py): Test discovery functions
- [`result.py`](./result.py): Custom TestResult class for result handling
- [`environment.py`](./environment.py): Test environment setup and teardown

## Example

```python
from frappe.testing import TestConfig, TestRunner, discover_all_tests

config = TestConfig(failfast=True, verbose=2)
runner = TestRunner(cfg=config)
discover_all_tests(['my_app'], runner)
runner.run()
```

For more detailed information about each component and its functionality, please refer to the docstrings and comments in the respective files.
```