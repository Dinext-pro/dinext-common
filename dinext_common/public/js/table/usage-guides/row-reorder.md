# Row reorder (drag-and-drop)

Перестановка строк **на клиенте** через gutter слева. Отдельный mixin-слой `RowReorderMixin` — не AG Grid Enterprise `rowDrag`.

Общий API: [`../README.md`](../README.md). Соседние контракты: [cell-changes.md](cell-changes.md), [merge-group-and-tree.md](merge-group-and-tree.md), [sections-and-summary.md](sections-and-summary.md).

---

## Включение

```js
DinextTable.create({
    container,
    data: [
        { id: 1, name: "Alpha", children: [{ id: 11, name: "Child" }] },
        { id: 2, name: "Beta" }
    ],
    columns: [{ field: "name", flex: 1 }],
    rowReorder: {
        enabled: true,
        allowTree: "reparent" // false | "siblings" | "reparent"
    },
    onValidateRowReorder({ table, source, move }) {
        return true; // false → drop отменяется до commit
    },
    onRowReorder: async ({ table, source, move }) => {
        await frappe.call({
            method: "my_app.api.reorder_rows",
            args: {
                row_id: move.rowId,
                new_row_id: move.newRowId,
                parent: move.toParentRowId,
                position: move.position,
                ordered_ids: move.orderedRowIds
            }
        });
    }
});
```

| Key | Default | Описание |
|-----|---------|----------|
| `rowReorder.enabled` | `false` | Reorder contour: gutter DnD + toolbar ↑↓ (preset `rows`) + `nudgeRowReorder` |
| `rowReorder.toolbarMove` | `true` | Show ↑↓ in preset `rows`; set `false` for tree UIs that only need gutter DnD |
| `rowReorder.handle` | `"gutter"` | `"gutter"` (v1). `"column"` — зарезервировано |
| `rowReorder.gutterWidth` | `12` | Ширина hit-zone слева (px) |
| `rowReorder.allowSummary` | `false` | Reorder pinned summary |
| `rowReorder.allowTree` | `"siblings"` | см. [Tree modes](#tree-modes) |

При `enabled: true` ядро ставит `animateRows: true`, если domain не задал `gridOptions.animateRows`.
Toolbar move arrows (preset `rows` + `rowCheck`) появляются только вместе с этим флагом — один контур. Стрелки = ±1 sibling (не reparent).

---

## Tree modes

| `allowTree` | Поведение |
|-------------|-----------|
| `false` | Только top-level строки в `data` |
| `"siblings"` | before/after **внутри одного** `parent.children` (или top-level) |
| `"reparent"` | before/after **между** parents + **inside** (стать child) |

---

## UX (как в tree)

1. Левый край строки (gutter) → `cursor: grab` → drag.
2. Зоны:

| Зона | Позиция | Визуал |
|------|---------|--------|
| Верх / низ | `before` / `after` — между | Подсветка **щели** между строками |
| Середина | `inside` — внутрь (`reparent`) | Серая **рамка-overlay** по bounds строки |

3. Невалидный drop → `not-allowed`.
4. Нет auto-expand на hover; после drop под свёрнутый parent → `expandRow`.
5. Outdent: `before`/`after` на parent.

Gutter отделён от tree-chevron и selection.

---

## Callbacks

### `onValidateRowReorder`

Sync, **до** изменения `sourceData`. Reject → операция не выполняется.

```js
onValidateRowReorder({ table, source, move }) {
    if (move.position === "inside" && move.targetRowId === "locked") return false;
    return true;
}
```

### `onRowReorder`

После optimistic commit. `false` / throw → revert порядка + path ids.

```js
onRowReorder: async ({ table, source, move }) => {
    // persist parent + order
}
```

### `canReorderRow` (опционально)

Per-row guard на **старт** drag:

```js
canReorderRow({ table, row, rowId, section, parentRowId }) {
    return !row.locked;
}
```

---

## Payload `move`

| Поле | Описание |
|------|----------|
| `section` | `"body"` \| `"summary"` |
| `position` | `"before"` \| `"after"` \| `"inside"` |
| `targetRowId` | строка, над которой отпустили |
| `parentRowId` | destination parent (`null` = top-level); = `toParentRowId` |
| `fromParentRowId` / `toParentRowId` | parent до / после |
| `rowId` / `newRowId` | path id до / после (на reparent меняется) |
| `fromIndex` / `toIndex` | индексы в sibling-массивах (pre-removal) |
| `blockSize` | `1` или размер merge-group |
| `orderedLocalRowIds` / `orderedRowIds` | порядок **destination** sibling-списка после move |
| `fromOrderedLocalRowIds` | порядок source-списка после move (при reparent) |
| `rows` | snapshot destination sibling-списка после move |

---

## Undo / Redo

Reorder в общем **CommandStack** (toolbar Undo/Redo, Ctrl+Z). Source: `rowReorder` (`ROW_REORDER_SOURCES`).

Reparent undo восстанавливает оба sibling-списка и path ids (`expandedIds`, checked rows).

---

## Guards

| Условие | Поведение |
|---------|-----------|
| Summary row | blocked, пока `allowSummary: true` |
| Merge tail row | drag blocked — тянуть только **head** (весь блок) |
| Merge block + nest / nested parent | reparent/nest blocked (flatten tree предполагает merge на top-level) |
| Drop into self / descendant | blocked (cycle) |
| `allowTree: "siblings"` + другой parent | drop запрещён |
| `allowTree: false` | только top-level |
| Active cell edit | DnD blocked |
| Column sort active | DnD blocked |

---

## Merge groups

Head (`mergeGroupIndex === 0`) тащит **весь блок**. Tail — не draggable.

Sibling reorder merge на top-level — как раньше. Cross-parent / inside для merge-блока — нет.

---

## Summary

```js
rowReorder: { enabled: true, allowSummary: true },
```

Summary refresh через `syncSummarySection()`.

---

## Roadmap

| Фича | Статус |
|------|--------|
| `handle: "column"` | reserved |
| Cross-parent + nest (`reparent`) | **done** |
| Keyboard a11y (Alt+↑/↓) | planned |
| Reorder при pagination / SSRM | out of scope |
| `allowWhenSorted` | not planned |
| Multi-row drag (не merge) | not planned |

---

## Потребителю

1. Плоский порядок: `allowTree: false` или `"siblings"`.
2. Полный tree-DnD: `allowTree: "reparent"`.
3. В `onRowReorder` persist `toParentRowId` + `orderedLocalRowIds` (или `orderedRowIds`) + при необходимости `newRowId`.
4. Не держать active column sort вместе с manual reorder.

---

## Файлы слоя

| Файл | Назначение |
|------|------------|
| `core/row-reorder/mixin.js` | Gutter DnD, zones UX, commit, undo |
| `core/row-reorder/ops.js` | Pure ops (sibling + reparent) |
| `core/row-reorder/constants.js` | sources, positions, tree modes |
| `@tests/row-reorder.test.mjs` | Unit-тесты ops |

Mixin order в `base.js`: после `FillHandleMixin`, до `RowCheckMixin`.
