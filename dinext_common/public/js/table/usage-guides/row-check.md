# Row check (checkbox column)

Выбор **строк** чекбоксом — отдельный слой от cell range `selection`. Opt-in колонка с reserved `colId`, state в `Set` row ids (не поле в data).

Общий API: [`../README.md`](../README.md). Соседи: [row-reorder.md](row-reorder.md), [selection-clipboard-navigation.md](selection-clipboard-navigation.md).

---

## Включение

```js
DinextTable.create({
    container,
    data: [
        { id: 1, name: "Alpha" },
        { id: 2, name: "Beta" }
    ],
    columns: [{ field: "name", flex: 1 }],
    rowCheck: { enabled: true },
    toolbar: {
        presets: ["history", "rows", "fullscreen"]
    },
    onAddRow: ({ table }) => ({ id: `new-${Date.now()}`, name: "" }),
    onDeleteRows: async ({ rowIds }) => {
        // persist delete; return false → revert sourceData + checks
    },
    onDuplicateRows: ({ rows }) => rows.map((row, i) => ({
        ...row,
        id: `copy-${Date.now()}-${i}`
    })),
    onRowCheckChange({ selectedRowIds }) {
        console.log(selectedRowIds);
    }
});
```

| Key | Default | Описание |
|-----|---------|----------|
| `rowCheck.enabled` | `false` | Inject system col + API |
| `rowCheck.unit` | `"row"` | `"row"` \| `"mergeHead"` |
| `rowCheck.allowSummary` | `false` | Check pinned summary |
| `rowCheck.selectAll` | `true` | Toolbar leading icon (stack+check ↔ stack clear); header col empty |
| `rowCheck.width` | `36` | Fixed col width |

**Не** добавляйте эту колонку в `columns`. Ядро inject `colId: "__dinext_row_check"` (`DinextTable.ROW_CHECK_COL_ID`).

Select-all в тулбаре появляется **автоматически** при `rowCheck.enabled` (не нужен отдельный preset), **в конце** primary-кнопок (перед fullscreen). Иконка: stack+✓ → select all; пустой stack → clear. `selectAll: false` — скрыть.

---

## `unit`

| Value | Поведение |
|-------|-----------|
| `"row"` | Чекбокс на каждой checkable row |
| `"mergeHead"` | Только head merge-группы; col с `spanRows`; tails не в Set; delete/nudge = весь atom. Auto `enableCellSpan: true` |

Явный выбор — без auto-guess по data.

---

## Toolbar preset `rows`

Добавьте `"rows"` в `toolbar.presets` (не в default).

| Кнопка | Условие |
|--------|---------|
| Select / clear all | авто иконка при `rowCheck` + `selectAll !== false` |
| Add | есть `onAddRow` |
| Delete | всегда (disabled если 0 checked); persist optional via `onDeleteRows` |
| Duplicate | есть `onDuplicateRows` (disabled если 0) |
| Move up / down | только если `rowReorder.enabled`; active при **ровно 1** checked и nudge возможен |

Move = тот же контур что gutter (`rowReorder.enabled` обязателен). Без reorder стрелок в тулбаре нет.

---

## Mutation pipeline

Один путь для add / delete / duplicate:

1. Optional validate — только `=== false` отклоняет (omit / `true` / `undefined` = ok).
2. Optimistic mutate `sourceData` (и summary при `allowSummary` + delete).
3. Sync grid + checked Set.
4. Persist hook — `false` / throw → revert snapshot **и** checks.
5. Undo command (общий CommandStack / toolbar Undo).

| Hook | Контракт |
|------|----------|
| `onAddRow` | вернуть **plain row**; иначе abort |
| `onDuplicateRows` | вернуть **non-empty rows[]** plain objects |
| `onDeleteRows` | optional; после remove; `false`/throw → revert |

Нет escape hatch `return true` («domain уже mutate»).

---

## Instance API

| Метод | Описание |
|-------|----------|
| `getCheckedRowIds()` / `getCheckedRows()` | Snapshot |
| `setCheckedRowIds(ids)` / `clearRowCheck()` | Set state |
| `toggleRowCheck(rowId, checked?)` | Одна строка |
| `setAllRowsChecked(checked)` | Select-all |
| `addRow()` / `deleteCheckedRows()` / `duplicateCheckedRows()` | Mutations |
| `nudgeCheckedRow(±1)` / `canNudgeCheckedRow(±1)` | Toolbar move |

---

## Callbacks

| Callback | Когда |
|----------|--------|
| `onRowCheckChange` | После toggle / select-all / clear / prune / mutations |
| `canCheckRow` | Per-row guard (section / leave / locked) |
| `onAddRow` | Factory: plain row |
| `onValidateDeleteRows` | Sync; `false` = stop |
| `onDeleteRows` | После optimistic remove |
| `onValidateDuplicateRows` | Sync; `false` = stop |
| `onDuplicateRows` | Factory: rows[] |

---

## Guards / edge cases

| Условие | Поведение |
|---------|-----------|
| User `columns` с тем же colId | strip + `console.warn` |
| Cell range / clipboard | System col вне range; arrow skip |
| Summary | blocked пока `allowSummary` |
| Merge tail при `mergeHead` | не checkable |
| Refresh data | prune мёртвых ids + `onRowCheckChange` если Set изменился |
| `type: "checkbox"` editor | другое — boolean cell, не rowCheck |
| Duplicate multi-select | inserts after **last** checked id |

---

## Roadmap (не v1)

| Фича | Статус |
|------|--------|
| Sync `_selected` field ↔ Set | out of scope (dual source) |
| Auto `unit` from merge meta | not planned |
| Cross-parent nudge | toolbar ±1 stays sibling-only; DnD reparent → `rowReorder.allowTree: "reparent"` |
| Keyboard a11y for check col | planned |

---

## Файлы

| Файл | Роль |
|------|------|
| `core/row-check/constants.js` | `ROW_CHECK_COL_ID`, units, sources |
| `core/row-check/model.js` | Pure: checkable, prune, remove, insert, clone |
| `core/row-check/mixin.js` | Col inject, Set API, mutations, undo |
| `core/toolbar/presets.js` | preset `rows` |
| `core/row-reorder/ops.js` | `computeNudgeToIndex`, `getStableRowId` |
