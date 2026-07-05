# DinextTable

Ядро таблицы на AG Grid 35 Community. Подключение:

```js
frappe.require(["dinext-table.bundle.js"], () => {
    DinextTable.create({ container, data, columns });
});
```

---

## `DinextTable.create(options)`

Один объект options. Поведение задаёт mixins (theme, tree, grid).

### Обязательные

| Key | Тип | Описание |
|-----|-----|----------|
| `container` | `HTMLElement` | DOM-узел для grid |

### Данные и колонки

| Key | Тип | Default | Описание |
|-----|-----|---------|----------|
| `data` | `Array` | `[]` | Top-level строки (см. [Data row](#data-row)) |
| `columns` | `Array` | `[]` | Колонки (см. [Column](#column)) |
| `edit` | `boolean` | `false` | Global editable default |

### Tree

| Key | Тип | Default | Описание |
|-----|-----|---------|----------|
| `childrenField` | `string` | `"children"` | Поле с дочерними строками в `data` |
| `rowIdField` | `string` | `"id"` | Локальный id строки (path: `101:1012:10121`) |
| `expandedIds` | `string[]` | `[]` | Id строк, раскрытых при create |
| `onExpandRow` | `async ({ rowId, row, table }) => void` | — | Lazy load: клиент вызывает `table.setRowChildren(rowId, children)` |

### Callbacks

| Key | Сигнатура | Описание |
|-----|-----------|----------|
| `onReady` | `(table) => void` | Grid создан, `table.api` доступен |
| `onCellDoubleClicked` | `(params, table) => void` | Двойной клик по ячейке |

### AG Grid passthrough

| Key | Тип | Описание |
|-----|-----|----------|
| `gridOptions` | `object` | Любые AG Grid options; callbacks склеиваются с ядром |
| `defaultColDef` | `object` | Default col def; deep merge с ядром |

---

## Static API

| API | Описание |
|-----|----------|
| `DinextTable.VERSION` | `"35.2.1"` |
| `DinextTable.load()` | Загрузить CSS + ag-grid-community |
| `DinextTable.create(options)` | `load()` → instance |

---

## Instance API

| Метод | Описание |
|-------|----------|
| `refresh(data?)` | Обновить `sourceData`, пересобрать `rowData` |
| `setOption(key, value)` | `data`, `columns`, `edit` |
| `toggleRow(rowId)` | Expand / collapse |
| `expandRow(rowId)` | Раскрыть (eager или lazy) |
| `collapseRow(rowId)` | Свернуть с потомками |
| `setRowChildren(rowId, children)` | Записать children + обновить grid (lazy load) |
| `destroy()` | Уничтожить grid |

### Instance properties

| Key | Описание |
|-----|----------|
| `sourceData` | Исходные top-level данные |
| `rowData` | Visible flat rows в grid |
| `columns` | Определения колонок (DinextTable API) |
| `expandedIds` | `Set` раскрытых `_rowId` |
| `api` | AG Grid GridApi |
| `options` | Исходный options object |

---

## Column

Элемент массива `columns`. Ядро нормализует в AG Grid `columnDefs`.

### DinextTable keys

| Key | Тип | Default | Описание |
|-----|-----|---------|----------|
| `field` | `string` | — | Поле в `data` row |
| `headerName` | `string` | — | Заголовок колонки |
| `edit` | `boolean \| (row, field) => boolean` | inherit `options.edit` | Column editable; приоритет выше global |
| `render` | `(params) => HTMLElement \| string` | — | **Tree col 0:** inner content (avatar, labels). Chevron + indent — ядро |
| `tree` | `boolean` | `true` на col 0 | `false` — без tree chrome на этой колонке |
| `cellRenderer` | `function \| class` | — | **Full override:** заменяет compose целиком (advanced) |

Приоритет edit: **`column.edit` > `options.edit`**.

**Tree col 0 layout:** `[indent][chevron|spacer][render(params)]`. Expand — **клик по chevron**.

### Layout (passthrough AG Grid)

| Key | Тип | Описание |
|-----|-----|----------|
| `width` | `number` | Фиксированная ширина |
| `flex` | `number` | Flex-grow |
| `minWidth` | `number` | Мин. ширина |
| `maxWidth` | `number` | Макс. ширина |
| `pinned` | `"left" \| "right"` | Закрепление |
| `hide` | `boolean` | Скрыть колонку |

### Display / edit (passthrough AG Grid)

| Key | Тип | Описание |
|-----|-----|----------|
| `cellDataType` | `string` | `"text"`, `"number"`, `"date"`, … |
| `valueFormatter` | `function` | Формат отображения |
| `valueParser` | `function` | Парсинг при edit |
| `cellEditor` | `string \| function` | Editor AG Grid |
| `cellEditorParams` | `object` | Параметры editor |

### Formatting (passthrough AG Grid)

Ядро не добавляет свой DSL — ключи из `columns[]` и `gridOptions` уходят в AG Grid как есть.

| Key | Уровень | Описание |
|-----|---------|----------|
| `cellStyle` | column | Inline CSS object или `(params) => object` |
| `cellClass` | column | CSS class или `(params) => string \| string[]` |
| `cellClassRules` | column | `{ "class-name": (params) => boolean }` — **предпочтительно для условного форматирования** |
| `type` | column | Имя preset из `gridOptions.columnTypes` |
| `getRowClass` | gridOptions | CSS class на строку |
| `getRowStyle` | gridOptions | Inline style на строку |
| `rowClassRules` | gridOptions | Условные классы строки |
| `columnTypes` | gridOptions | Переиспользуемые пресеты colDef |

**Три слоя — не одно и то же:**

| Слой | Когда | API |
|------|-------|-----|
| Значение | число, дата, текст без смены DOM | `valueFormatter`, `cellDataType` |
| Стиль | цвет, жирность, выравнивание, фон | `cellClass`, `cellClassRules`, `cellStyle` |
| Структура | avatar, badge, составная ячейка | `render` (tree col 0) или `cellRenderer` |

Utility-классы в `dinext-table.css`: `dinext-table-cell--align-right`, `--align-center`, `--negative`, `--highlight`, `dinext-table-row--level-*`.

На tree col 0 `cellClass` / `cellClassRules` вешаются на внешнюю `.ag-cell` AG Grid (вместе с indent). Align только inner content — класс внутри `render`.

### Default col def (на уровне table)

Через `defaultColDef` или `gridOptions.defaultColDef`. Ядро задаёт:

| Key | Value |
|-----|-------|
| `resizable` | `true` |
| `sortable` | `false` |

---

## Data row

Элемент массива `data` (и вложенный `children`).

### Бизнес-поля

Любые поля под `columns[].field`. Пример:

| Key | Тип | Пример |
|-----|-----|--------|
| `id` | `string \| number` | `101` |
| `name` | `string` | `"Group Alpha"` |
| `value` | `number` | `450` |

Имена полей — на усмотрение клиента; `rowIdField` / `columns` должны им соответствовать.

### Tree (клиентские)

| Key | Тип | Описание |
|-----|-----|----------|
| `children` | `Array<row>` | Дочерние строки (eager). Имя поля — `childrenField` |
| `hasChildren` | `boolean` | `true` — expandable без загруженных `children` (lazy) |

Произвольные поля для `render` (avatar, meta) — на усмотрение клиента.

**Eager:** `children: [...]`  
**Lazy:** `hasChildren: true` + `onExpandRow` → `setRowChildren`

Вложенность: N уровней. Path id: `parentId:childId:grandchildId`.  
Local `id` не должен содержать `:`.

### Служебные (ядро, только в grid rowData)

Добавляются при flatten; не задавать в source `data`:

| Key | Описание |
|-----|----------|
| `_rowId` | Stable id для AG Grid |
| `_level` | Глубина (0 = root) |
| `_hasChildren` | Expandable |
| `_parentRowId` | `_rowId` родителя |
| `_treeLoading` | Lazy fetch in progress (только grid node) |

---

## Tree: eager vs lazy

| | Eager | Lazy |
|--|-------|------|
| Данные | `children: [...]` | `hasChildren: true` |
| Expand | `insertVisibleChildren` | `onExpandRow` → `setRowChildren` |
| Grid update | `applyTransaction` | `applyTransaction` |
| Loading | — | chevron pulse (`_treeLoading`) |

Первая колонка (`columns[0]`): `[indent][chevron|spacer][render]`. Expand — **клик по chevron**.

---

## Formatting: пример

```js
DinextTable.create({
    container,
    data,
    columns: [
        {
            field: "value",
            headerName: "Value",
            cellClass: "dinext-table-cell--align-right",
            valueFormatter: (p) => p.value == null ? "" : `${p.value} ₽`,
            cellClassRules: {
                "dinext-table-cell--negative": (p) => p.value < 0,
                "dinext-table-cell--highlight": (p) => p.value >= 800,
            },
        },
    ],
    gridOptions: {
        columnTypes: {
            money: {
                type: "numericColumn",
                cellClass: "dinext-table-cell--align-right",
                valueFormatter: (p) => fmtMoney(p.value),
            },
        },
        getRowClass: (p) => p.data?._level ? `dinext-table-row--level-${p.data._level}` : "",
    },
});
```

---

## Пример

```js
DinextTable.create({
    container,
    edit: true,
    data: [
        {
            id: 101,
            name: "Group Alpha",
            children: [
                { id: 1011, name: "Child" },
                { id: 1012, name: "Sub-group", children: [
                    { id: 10121, name: "Nested" }
                ]}
            ]
        },
        { id: 201, name: "Lazy group", hasChildren: true }
    ],
    columns: [
        {
            field: "name",
            headerName: "Name",
            flex: 1,
            render: (params) => {
                const el = document.createElement("span");
                el.textContent = params.data.name;
                return el;
            }
        },
        { field: "value", headerName: "Value", width: 120, edit: false },
    ],
    onExpandRow: async ({ rowId, table }) => {
        const children = await fetchChildren(rowId);
        table.setRowChildren(rowId, children);
    },
    onReady: (table) => console.log(table.rowData.length),
});
```

Smoke-test: `/app/dinext-table-test`
