# DinextTable

Ядро editable-таблицы на **AG Grid 35 Community**. Один `options`-объект, поведение — mixins (`theme`, `tree`, `sort`, `section`, `edit`, `selection`, `clipboard`, …).

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
  sort/                  — recursive sibling sort (source tree; not AG flat sort)
  filter/                — column filter (flat-first; floating row + toolbar)
  shared/utils.js        — mergeGridOptions, rowId/children fields, merge-group, DOM helpers
  section/               — summary pin, TABLE_SECTIONS
  edit/                  — commitCellChanges, editors, navigation
  selection/             — range, clipboard, fill-handle, status bar
  row-reorder/           — gutter DnD + nudge ±1
  row-check/             — checkbox col + checked Set + row mutations
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
| [sorting.md](usage-guides/sorting.md) | Client sort: siblings + merge atoms |
| [filtering.md](usage-guides/filtering.md) | Column filter: toolbar search + row under header |
| [fullscreen.md](usage-guides/fullscreen.md) | Shell FS + enter/exit hooks |
| [sections-and-summary.md](usage-guides/sections-and-summary.md) | `summaryRows`, pin bottom, guards |
| [columns-and-formatting.md](usage-guides/columns-and-formatting.md) | Колонки, presets, styling |
| [date-columns.md](usage-guides/date-columns.md) | `type: date`, ISO, fill, Frappe cellEditor |
| [selection-clipboard-navigation.md](usage-guides/selection-clipboard-navigation.md) | Range, TSV, fill handle, Tab/Enter |
| [row-reorder.md](usage-guides/row-reorder.md) | Gutter row drag-and-drop reorder |
| [row-check.md](usage-guides/row-check.md) | Checkbox col, toolbar rows, nudge |

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
| `theme.columnBorder` | `true` | Vertical borders (body) |
| `theme.headerColumnBorder` | same as `columnBorder` | Vertical borders (header) |
| `theme.rowBorder` | Quartz default | Horizontal borders between rows |
| `theme.headerRowBorder` | Quartz default | Horizontal border under header |
| `theme.wrapperBorder` | Quartz default | Outer wrapper border |
| `theme.pinnedColumnBorder` | Quartz default | Border between pinned and center |
| `theme.pinnedRowBorder` | Quartz default | Border between pinned rows and body |
| `theme.cellHorizontalPadding` | Quartz default | Cell/header horizontal padding; `0` for abutting heatmap cells |
| `theme.borderRadius` | `4` | Quartz + `--dinext-table-radius` (toolbar/status) |
| `theme.fontFamily` | Desk `--font-stack` | Override; default Inter stack (not IBM Plex Sans) |

Borderless heatmap (opt-in): set border flags to `false` + `cellHorizontalPadding: 0`. Quartz `false` alone leaves transparent 1px seams — core maps to `{ width: 0 }`, forces `--ag-*-border*` off, and toggles `.dinext-table--no-row-borders` / `--no-column-borders`. Paint fills on `.ag-cell` (`cellClassRules` / `cellStyle`), not on child renderer wrappers. Unset flags keep default borders.

### Tree

| Key | Default | Описание |
|-----|---------|----------|
| `childrenField` | `"children"` | Поле дочерних строк |
| `rowIdField` | `"id"` | Local id (path: `101:1012`) |
| `expandedIds` | `[]` | Раскрыты при create |
| `onExpandRow` | — | Lazy load → `setRowChildren` |

→ [merge-group-and-tree.md](usage-guides/merge-group-and-tree.md), tree table в [selection-clipboard-navigation.md](usage-guides/selection-clipboard-navigation.md).

### Sort

| Key | Default | Описание |
|-----|---------|----------|
| `sort.enabled` | `false` | Opt-in client sort (header click + API) |
| `sort.state` | `[]` | `[{ field, dir: "asc"\|"desc" }]` |
| `sort.nulls` | `"last"` | Empty values position |
| `onSortChange` | — | После apply |

→ [sorting.md](usage-guides/sorting.md). AG `sortable` остаётся `false` — сортируется source-tree.

### Filter

| Key | Default | Описание |
|-----|---------|----------|
| `filter.enabled` | `true` | Column filter layer + toolbar search |
| `filter.active` | `false` | Filter row под header (toolbar toggle) |
| `filter.state` | `{}` | `{ field: query }` — Keep при закрытии UI |
| `onFilterChange` | — | После смены state / active |

→ [filtering.md](usage-guides/filtering.md). Tree: match + ancestors.

### Fullscreen

| Key | Default | Описание |
|-----|---------|----------|
| `fullscreen.enabled` | `true` | Native Fullscreen API |
| `fullscreen.target` | `"container"` | `"shell"` — FS на внешний wrapper |
| `fullscreen.shell` | — | DOM при `target: "shell"` (filters + table и т.п.) |
| `fullscreen.onEnter` / `onExit` | — | После реального enter/exit (вкл. Esc) |
| `onFullscreenEnter` / `onFullscreenExit` | — | Top-level alias (оба вызываются, nested первым) |

Domain: что видно в FS — через `shell` + CSS hide siblings, не teleport DOM. Хуки — для class/layout.

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
| `clickWhenActive` | Повторный одиночный клик по уже focused → edit (default: как navigation / edit availability) |

`changes[]`: `{ rowId, field, oldValue, newValue, row, section, … }`.  
`source`: `edit` \| `paste` \| `fillDown` \| `fillHandle` \| `clear` \| `undo` \| `redo`.

→ [cell-changes.md](usage-guides/cell-changes.md), [selection-clipboard-navigation.md](usage-guides/selection-clipboard-navigation.md).

### Interaction

| Key | Default | Описание |
|-----|---------|----------|
| `navigation.*` | см. гайд | Tab/Enter |
| `selection.enabled` | `false` | Custom range |
| `clipboard.enabled` | `selection.enabled` | TSV copy/paste |
| `fillHandle.enabled` | `clipboard.enabled` | Corner drag fill |
| `rowReorder.enabled` | `false` | Reorder contour: gutter + toolbar ↑↓ + nudge; auto `animateRows` |
| `rowReorder.allowTree` | `"siblings"` | `false` \| `"siblings"` \| `"reparent"` (cross-parent + nest) |
| `rowCheck.enabled` | `false` | Checkbox col + checked Set; toolbar select/deselect icon |
| `rowCheck.unit` | `"row"` | `"mergeHead"` — check only merge head + span |
| `toolbar.enabled` | `true` | Command toolbar |
| `toolbar.defaultPinned` | `true` | Панель видна сразу (pin) |
| `toolbar.persistKey` | `null` | localStorage UI per table: pin + filter (`dinext-table:toolbar:${key}`) |
| `toolbar.presets` | `history/tree/fullscreen` | Filter icon auto при `filter.enabled`; opt-in: `"rows"`, `"clipboard"` |
| `toolbar.items` | `[]` | Domain zone (между presets и fullscreen): button / checkbox / separator / **custom** |

Layout: `[ pin | presets | filter | rowCheck ] | [ items… h-scroll ] | [ fullscreen ]`

Custom panel example:

```js
toolbar: {
  items: [{
    id: "domain-actions",
    type: "custom",
    render: ({ host, table }) => {
      host.replaceChildren(); // or return a fresh element
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-xs btn-default";
      btn.textContent = "Do thing";
      btn.onclick = () => { /* use table */ };
      return btn;
    }
  }]
}
```

→ [selection-clipboard-navigation.md](usage-guides/selection-clipboard-navigation.md), [row-reorder.md](usage-guides/row-reorder.md), [row-check.md](usage-guides/row-check.md).

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
| `DinextTable.ROW_CHECK_COL_ID` | Reserved system col id |
| `DinextTable.ROW_CHECK_UNITS` | `"row"` \| `"mergeHead"` |

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
| `getCheckedRowIds()` / `setCheckedRowIds` / `clearRowCheck` | Row check Set |
| `addRow()` / `deleteCheckedRows()` / `duplicateCheckedRows()` | Row mutations |
| `toggleFilterRow` / `getFilter` / `setFilter` / `clearFilter` | Column filter |
| `nudgeCheckedRow(±1)` | Move one checked row (row-reorder commit) |
| `destroy()` | Teardown |

**Properties:** `sourceData`, `summarySourceData`, `summaryRowData`, `rowData`, `columns`, `expandedIds`, `api`, `options`.

---

## Ограничения v1

- Selection + merge span — не идеал (documented).
- `enableCellSpan` — effectively initial layout; resync после tree — см. todo.
- Summary id не должен коллидировать с body (`findSourceRow` → body wins).
- Домен (формулы итогов, API save) — **только клиент**, не ядро.

План улучшений: [`todo/README.md`](todo/README.md).
