# DinextTable

Ядро editable-таблицы на **AG Grid 35 Community**. Один `options`-объект, поведение — mixins (`theme`, `tree`, `section`, `edit`, `selection`, `clipboard`, …).

```js
frappe.require(["dinext-table.bundle.js"], () => {
    DinextTable.create({ container, data, columns, edit: true });
});
```

| Ресурс | Путь |
|--------|------|
| Типы IDE | [`dinext-table.d.ts`](dinext-table.d.ts) |
| Unit-тесты | [`@tests/`](@tests/) — `npm run test:dinext-table` из `apps/dinext_common` |
| Backlog ядра | [`todo/README.md`](todo/README.md) |

---

## Структура `core/`

Папка — только если **2+ файла** домена. Одиночные модули остаются в корне `core/`.

```
core/
  facade.js, base.js, grid.js, theme.js
  tree/                  — model.js (pure) + expand.js + mixin.js (renderer/expand)
  shared/utils.js        — mergeGridOptions, rowId/children fields, merge-group, DOM helpers
  section/               — summary pin, TABLE_SECTIONS
  edit/                  — commitCellChanges, editors, navigation
  selection/             — range, clipboard, fill-handle, status bar
  row-reorder/           — gutter DnD
  toolbar/               — command bar + fullscreen
```

Импорт: напрямую из файлов домена (`./edit/mixin.js`, `./tree/model.js`). Без barrel `index.js`.

---

## Usage guides

Детальные сценарии — в [`usage-guides/`](usage-guides/):

| Гайд | Тема |
|------|------|
| [cell-changes.md](usage-guides/cell-changes.md) | Batch edit: `onValidateCells` / `onSaveCells` |
| [merge-group-and-tree.md](usage-guides/merge-group-and-tree.md) | Merge (`rowSpan`) + tree eager/lazy |
| [sections-and-summary.md](usage-guides/sections-and-summary.md) | `summaryRows`, pin bottom, guards |
| [columns-and-formatting.md](usage-guides/columns-and-formatting.md) | Колонки, presets, styling |
| [selection-clipboard-navigation.md](usage-guides/selection-clipboard-navigation.md) | Range, TSV, fill handle, Tab/Enter |
| [row-reorder.md](usage-guides/row-reorder.md) | Gutter row drag-and-drop reorder |

---

## Быстрый старт

```js
DinextTable.create({
    container,
    edit: true,
    selection: { enabled: true },
    data: [
        { id: 1, name: "Alpha", value: 100 },
        { id: 2, name: "Beta", value: 200, children: [{ id: "2.1", name: "Child", value: 50 }] }
    ],
    summaryRows: [{ id: "total", name: "Итого", value: 350 }],
    columns: [
        { field: "name", headerName: "Name", flex: 1 },
        { field: "value", headerName: "Value", width: 120, type: "number" }
    ],
    onValidateCells: () => true,
    onSaveCells: async ({ changes }) => { /* один batch на операцию */ },
    onExpandRow: async ({ rowId, table, section }) => {
        table.setRowChildren(rowId, await fetchChildren(rowId));
    },
    onReady: (table) => console.log(table.rowData.length),
});
```

---

## Options — обзор

### Core

| Key | Default | Описание |
|-----|---------|----------|
| `container` | — | **required** — DOM для grid |
| `data` | `[]` | Body rows (top-level) |
| `columns` | `[]` | → [columns-and-formatting.md](usage-guides/columns-and-formatting.md) |
| `edit` | `false` | Global editable default |
| `theme.columnBorder` | `true` | Vertical borders |

### Tree

| Key | Default | Описание |
|-----|---------|----------|
| `childrenField` | `"children"` | Поле дочерних строк |
| `rowIdField` | `"id"` | Local id (path: `101:1012`) |
| `expandedIds` | `[]` | Раскрыты при create |
| `onExpandRow` | — | Lazy load → `setRowChildren` |

→ [merge-group-and-tree.md](usage-guides/merge-group-and-tree.md), tree table в [selection-clipboard-navigation.md](usage-guides/selection-clipboard-navigation.md).

### Summary

| Key | Default | Описание |
|-----|---------|----------|
| `summaryRows` | `[]` | Итоги отдельно от `data` |
| `summary.pin` | `"bottom"` | `pinnedBottomRowData` |
| `summary.edit` / `clipboard` / `selection` | `true` / `false` / `false` | Guards |

→ [sections-and-summary.md](usage-guides/sections-and-summary.md).

### Edit

| Key | Описание |
|-----|----------|
| `onValidateCells` | Sync validate до commit; reject → revert batch |
| `onSaveCells` | Async persist; `false`/throw → revert |
| `readOnlyEdit` | AG Grid `readOnlyEdit` pipeline |

`changes[]`: `{ rowId, field, oldValue, newValue, row, section, … }`.  
`source`: `edit` \| `paste` \| `fillDown` \| `fillHandle` \| `clear` \| `undo` \| `redo`.

→ [cell-changes.md](usage-guides/cell-changes.md).

### Interaction

| Key | Default | Описание |
|-----|---------|----------|
| `navigation.*` | см. гайд | Tab/Enter |
| `selection.enabled` | `false` | Custom range |
| `clipboard.enabled` | `selection.enabled` | TSV copy/paste |
| `fillHandle.enabled` | `clipboard.enabled` | Corner drag fill |
| `rowReorder.enabled` | `true` | Gutter row DnD reorder |

→ [selection-clipboard-navigation.md](usage-guides/selection-clipboard-navigation.md), [row-reorder.md](usage-guides/row-reorder.md).

### Callbacks & passthrough

| Key | Описание |
|-----|----------|
| `onReady(table)` | Grid ready, `table.api` доступен |
| `onCellDoubleClicked(params, table)` | Double click |
| `gridOptions` / `defaultColDef` | AG Grid passthrough; callbacks merge с ядром |

---

## Static API

| API | Описание |
|-----|----------|
| `DinextTable.VERSION` | `"35.2.1"` |
| `DinextTable.load()` | CSS + ag-grid-community |
| `DinextTable.create(options)` | `load()` → instance |
| `DinextTable.createMergeGroupSpanRows(options?)` | Helper для `spanRows` |
| `DinextTable.CELL_CHANGE_SOURCES` | Константы `source` |

---

## Instance API

| Метод | Описание |
|-------|----------|
| `refresh(data?)` | Body data + resync rows |
| `setOption(key, value)` | `data`, `columns`, `edit`, `summaryRows`, … |
| `setSummaryRows(rows)` | Summary + pin sync |
| `toggleRow` / `expandRow` / `collapseRow` | Tree |
| `setRowChildren(rowId, children)` | Lazy load result |
| `getCellRanges()` / `clearCellSelection()` | Selection |
| `copySelectionToClipboard()` | async TSV |
| `pasteFromClipboard()` / `fillDownSelection()` / `clearSelectionCells()` | Clipboard batch |
| `fillRange(sourceBounds, targetBounds, opts?)` | Programmatic fill |
| `undoClipboard()` / `redoClipboard()` | AG Grid edit undo/redo или CommandStack |
| `destroy()` | Teardown |

**Properties:** `sourceData`, `summarySourceData`, `summaryRowData`, `rowData`, `columns`, `expandedIds`, `api`, `options`.

---

## Ограничения v1

- Selection + merge span — не идеал (documented).
- `enableCellSpan` — effectively initial layout; resync после tree — см. todo.
- Summary id не должен коллидировать с body (`findSourceRow` → body wins).
- Домен (формулы итогов, API save) — **только клиент**, не ядро.

План улучшений: [`todo/README.md`](todo/README.md).

