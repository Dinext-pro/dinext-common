# Selection, clipboard, navigation

Кастомные Community-реализации без AG Grid Enterprise (`rangeSelection`, clipboard module).

Общий API: [`../README.md`](../README.md). Batch save: [`cell-changes.md`](cell-changes.md).

---

## Navigation

Включена по умолчанию при `edit: true` (или `navigation.enabled`).

| Key | Default | Описание |
|-----|---------|----------|
| `navigation.enabled` | `options.edit` | Tab/Enter после edit |
| `navigation.skipNonEditable` | `true` | Tab/Enter пропускают read-only |
| `navigation.enterMovesDown` | `true` | Enter → ячейка ниже |
| `navigation.tabWraps` | `false` | Tab на границе — wrap |
| `navigation.isRowNavigable` | `() => true` | Фильтр строк |
| `navigation.isCellNavigable` | `() => true` | Фильтр ячеек |

**Клавиши:**

- **Tab / Shift+Tab** — в edit: commit → следующая navigable ячейка; editable → сразу edit. Вне edit — только фокус.
- **↑↓←→** — AG Grid default; read-only можно фокусировать, edit блокируется `editable`.
- **Enter** после edit — вниз (`enterMovesDown`), без авто-edit.
- Printable keys не перехватываются.

Tree chevron: `stopPropagation` — клавиатура не toggle tree.

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

Highlight — CSS на `.ag-cell` DOM (`dinext-table-cell-in-range`, `-range-top/bottom/left/right`). Переподкладка на `onBodyScroll` (virtualization).

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
| Ctrl/Cmd+Z | `api.undoCellEditing()` или CommandStack undo |

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
