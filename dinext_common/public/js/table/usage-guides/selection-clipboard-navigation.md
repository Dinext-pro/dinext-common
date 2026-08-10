# Selection, clipboard, navigation

Кастомные Community-реализации без AG Grid Enterprise (`rangeSelection`, clipboard module).

Общий API: [`../README.md`](../README.md). Batch save: [`cell-changes.md`](cell-changes.md).

---

## Navigation

Включена по умолчанию при `edit: true`, либо если у колонок есть `edit` (как WE: global `edit: false` + per-column). Явно: `navigation.enabled`.

| Key | Default | Описание |
|-----|---------|----------|
| `navigation.enabled` | `edit` или column `edit` | Tab + Enter navigation |
| `navigation.skipNonEditable` | `true` | Tab пропускает read-only |
| `navigation.enterMovesDown` | `true` | Enter → ниже via AG Grid `enterNavigatesVertically*` |
| `navigation.tabWraps` | `false` | Tab на границе — wrap |
| `navigation.isRowNavigable` | `() => true` | Фильтр строк (Tab) |
| `navigation.isCellNavigable` | `() => true` | Фильтр ячеек (Tab) |

**Клавиши:**

- **Tab / Shift+Tab** — commit → следующая navigable (skip read-only); editable → сразу edit. Capture-phase, т.к. bubble `onCellKeyDown` часто после stop-edit.
- **↑↓←→** — AG Grid default; read-only можно фокусировать, edit блокируется `editable`.
- **Enter / Shift+Enter** — только AG Grid (`enterNavigatesVertically` + `enterNavigatesVerticallyAfterEdit`): вниз / вверх, без авто-edit. Не skipNonEditable (колонка та же).
- Printable keys не перехватываются.

Tree chevron: `stopPropagation` — клавиатура не toggle tree.

---

## Click → edit (when active)

Sheets-like жест: **первый** клик — focus/select; **повторный одиночный** по уже focused ячейке — `startEditingCell`. Не `singleClickEdit`.

| Key | Default | Описание |
|-----|---------|----------|
| `clickWhenActive` | on при `edit` / column `edit` | `false` — выключить; `true` — явно включить |

**Условия старта edit:**

- ячейка была focused **до** этого pointer-жеста (snapshot на capture `mousedown`);
- `event.detail === 1` (вторая половина dblclick не стартует edit → `onCellDoubleClicked` жив);
- editable; без Shift/Ctrl/Cmd/Alt;
- не checkbox/boolean column;
- не fill-handle;
- selection: только 1×1 range (multi-cell / multi-range — нет).

Double-click edit (AG Grid default) и Tab→edit остаются.

---

## Selection (range)

Без Enterprise `rangeSelection`. Scalar-ячейки, видимые flat-строки (свёрнутые tree-потомки не в range).

| Key | Default | Описание |
|-----|---------|----------|
| `selection.enabled` | `false` | Range selection |
| `selection.suppressMultiRanges` | `false` | `true` — без Ctrl+Click multi-range |

**Жесты:**

- Drag — прямоугольник от anchor.
- Shift+Click — extend от `focusedCell`.
- Shift+стрелки — extend на 1 ячейку/строку.
- Ctrl/Cmd+Click — отдельный range (если не suppressed).
- Ctrl/Cmd+A — все видимые ячейки center viewport.

Highlight — CSS на `.ag-cell` DOM (`dinext-table-cell-in-range`, `-range-top/bottom/left/right`). Переподкладка на `onBodyScroll` (virtualization). Lookup ячейки — `queryAgCellElement` (учитывает несколько `.ag-row[row-index=N]` при `pinned` left/right).

Summary rows: по умолчанию **вне** selection (`summary.selection: false`).

**Ограничение:** selection + `rowSpan` (merge) — не идеал; см. [merge-group-and-tree.md](merge-group-and-tree.md).

---

## Clipboard (TSV)

| Key | Default | Описание |
|-----|---------|----------|
| `clipboard.enabled` | `selection.enabled` | Ctrl+C/V/D, Delete, undo stack |

**Клавиши** (вне edit; в edit — только Ctrl+Z):

| Key | Действие |
|-----|----------|
| Ctrl/Cmd+C | TSV выделения / focused cell |
| Ctrl/Cmd+V | Parse TSV → paste от top-left range |
| Ctrl/Cmd+D | Fill down верхней строки range |
| Delete | Clear editable → `null` |
| Ctrl/Cmd+Z | `undoClipboard()` — AG Grid edit undo или CommandStack |
| Ctrl/Cmd+Shift+Z | `redoClipboard()` — AG Grid edit redo или CommandStack |

Paste/clear/fill-down → `commitCellChanges` → один `onSaveCells` на batch. CommandStack limit 20.

Summary: по умолчанию **вне** clipboard (`summary.clipboard: false`).

---

## Fill handle

Excel-like drag уголка активного range. Copy-fill паттерна source → extension.

| Key | Default | Описание |
|-----|---------|----------|
| `fillHandle.enabled` | `clipboard.enabled` | Corner handle + drag |

Ось фиксируется при drag (↓/↑/←/→). Идёт через `fillRange` → `source: "fillHandle"`.

Требует `selection.enabled` + `clipboard.enabled` (или явный `fillHandle.enabled`).

DOM: handle монтируется в угловую `.ag-cell` (`right/bottom` CSS), едет со scroll вместе с ячейкой. На `onBodyScroll` — только re-attach после virtualization / hide если угол вне DOM. Host-класс `dinext-table-cell--fill-handle-host` → `overflow: visible`.

Preview CSS: `dinext-table-cell-fill-preview*`.

---

## Tree: eager vs lazy (body)

| | Eager | Lazy |
|--|-------|------|
| Данные | `children: [...]` | `hasChildren: true` |
| Expand | `insertVisibleChildren` | `onExpandRow` → `setRowChildren` |
| Grid | `applyTransaction` | `applyTransaction` |
| Loading | — | `_treeLoading` на chevron |

Path id: `parentId:childId:…`. Local `id` без `:`.

Merge + tree: [merge-group-and-tree.md](merge-group-and-tree.md).

---

## Data row (кратко)

**Клиентские поля:** любые под `columns[].field`; `id` + `children` / `hasChildren` для tree.

**Служебные (только grid, не задавать в source):**

| Key | Описание |
|-----|----------|
| `_rowId` | Stable id |
| `_level` | Глубина tree |
| `_hasChildren` | Expandable |
| `_parentRowId` | Parent path |
| `_treeLoading` | Lazy in progress |
| `_section` | `"summary"` на pinned summary (ядро) |

Merge metadata: `mergeGroupId`, `mergeGroupIndex`, `mergeGroupSize` — см. merge guide.
