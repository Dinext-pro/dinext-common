# Row reorder (drag-and-drop)

Перестановка строк **на клиенте** через gutter слева. Отдельный mixin-слой `RowReorderMixin` — не AG Grid Enterprise `rowDrag`.

Общий API: [`../README.md`](../README.md). Соседние контракты: [cell-changes.md](cell-changes.md), [merge-group-and-tree.md](merge-group-and-tree.md), [sections-and-summary.md](sections-and-summary.md).

---

## Включение

```js
DinextTable.create({
    container,
    data: [
        { id: 1, name: "Alpha" },
        { id: 2, name: "Beta" },
        { id: 3, name: "Gamma" }
    ],
    columns: [{ field: "name", flex: 1 }],
    rowReorder: { enabled: true },
    onValidateRowReorder({ table, source, move }) {
        return true; // false → drop отменяется до commit
    },
    onRowReorder: async ({ table, source, move }) => {
        await frappe.call({
            method: "my_app.api.reorder_rows",
            args: { ordered_ids: move.orderedRowIds }
        });
    }
});
```

| Key | Default | Описание |
|-----|---------|----------|
| `rowReorder.enabled` | `false` | Gutter DnD; `true` — включить |
| `rowReorder.handle` | `"gutter"` | `"gutter"` (v1). `"column"` — зарезервировано |
| `rowReorder.gutterWidth` | `12` | Ширина hit-zone слева (px) |
| `rowReorder.allowSummary` | `false` | Reorder pinned summary |
| `rowReorder.allowTree` | `"siblings"` | `"siblings"` — внутри одного `parent.children`; `false` — только top-level `data` |

---

## UX

1. Навести на **левый gutter** строки (первые 12px по умолчанию) → `cursor: grab`.
2. Зажать ЛКМ в gutter → drag, строка полупрозрачная.
3. Отпустить над другой строкой **того же sibling-уровня** → commit.
4. Линия-индикатор показывает позицию вставки (до/после midpoint строки).

Gutter отделён от tree-chevron и selection — chevron кликается как раньше.

---

## Callbacks

### `onValidateRowReorder`

Sync, **до** изменения `sourceData`. Reject → операция не выполняется.

```js
onValidateRowReorder({ table, source, move }) {
    if (move.section === "summary") return false;
    return true;
}
```

### `onRowReorder`

После optimistic commit. `false` / throw → revert порядка + `sourceData`.

```js
onRowReorder: async ({ table, source, move }) => {
    // persist
}
```

### `canReorderRow` (опционально)

Per-row guard:

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
| `parentRowId` | `null` для top-level; `"101"` для nested |
| `rowId` | stable id перетаскиваемой строки (`_rowId` или path) |
| `fromIndex` / `toIndex` | индексы в **sibling-массиве** (`data` или `parent.children`) |
| `blockSize` | `1` или размер merge-group |
| `orderedLocalRowIds` | local ids в sibling-списке после move |
| `orderedRowIds` | full path ids (`101:5`) после move |
| `rows` | snapshot sibling-списка после move |

---

## Undo / Redo

Reorder попадает в общий **CommandStack** (toolbar Undo/Redo, Ctrl+Z). Отдельный `source` в row-reorder layer: `rowReorder` (см. `ROW_REORDER_SOURCES`).

---

## Guards (v1)

| Условие | Поведение |
|---------|-----------|
| Summary row | blocked, пока `allowSummary: true` |
| Merge tail row | blocked — тянуть только **head** (весь блок) |
| Разные parent в tree | drop запрещён |
| Active cell edit | DnD blocked |
| Column sort active | DnD blocked |
| `allowTree: false` | только top-level строки в `data` |

---

## Tree

При `allowTree: "siblings"` (default):

- Перестановка только среди **direct siblings** (один `parent.children` или top-level `data`).
- Nested `children` в `sourceData` обновляются на месте; затем `syncVisibleRows()` + refresh grid.
- Lazy children (`onExpandRow`) — reorder после load, как у eager.

**Не поддерживается в v1:** перенос строки между разными parents (cross-level move).

---

## Merge groups

Head row (`mergeGroupIndex === 0`) тащит **весь блок** (`mergeGroupSize` строк) в `sourceData`.

Tail rows (`mergeGroupIndex > 0`) — не draggable.

---

## Summary

По умолчанию summary **не** reorderable. Opt-in:

```js
rowReorder: { enabled: true, allowSummary: true },
onRowReorder({ move }) {
    if (move.section === "summary") { /* save summary order */ }
}
```

Summary refresh через `syncSummarySection()` (не `applyTransaction`).

---

## Roadmap (не v1 — зафиксировано для возврата)

| Фича | Статус |
|------|--------|
| `handle: "column"` — отдельная grip-колонка | reserved |
| Cross-parent tree move | not planned v1 |
| Keyboard a11y (Alt+↑/↓) | planned |
| Reorder при pagination / server-side row model | out of scope |
| `rowReorder.allowWhenSorted: true` | not planned — sort и manual order конфликтуют |
| Toolbar preset `row-reorder` | not needed (always gutter) |

---

## Потребителю (WE и др.)

1. Включить `rowReorder: { enabled: true }`.
2. В `onRowReorder` отправить `move.orderedRowIds` или `orderedLocalRowIds` + `parentRowId`.
3. При tree — уточнять `parentRowId` на сервере.
4. Не включать одновременно column sort и reorder без сброса sort.

---

## Файлы слоя

| Файл | Назначение |
|------|------------|
| `core/row-reorder/mixin.js` | Mixin: gutter DnD, commit, undo |
| `core/row-reorder/ops.js` | Pure ops (sibling list, merge block) |
| `core/row-reorder/constants.js` | `ROW_REORDER_SOURCES` |
| `@tests/row-reorder.test.mjs` | Unit-тесты ops |

Mixin order в `base.js`: после `FillHandleMixin`, до `SelectionStatusMixin`. См. также [`../README.md`](../README.md) — структура `core/`.
