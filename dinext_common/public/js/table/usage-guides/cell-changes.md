# Cell changes (batch edit)

Как обрабатывать мутации ячеек через **`onValidateCells`** / **`onSaveCells`**.

Общий API: [`../README.md`](../README.md).

---

## Контракт

Любое изменение данных (typing, paste, fill, clear, undo clipboard) → **один batch**:

```js
DinextTable.create({
    edit: true,
    onValidateCells({ table, source, range, changes }) {
        return true; // false | string → reject batch
    },
    onSaveCells: async ({ table, source, range, changes }) => {
        // один API call на операцию
        await saveToServer({ source, changes });
    }
});
```

Scalar edit — `changes.length === 1`, `source: "edit"`.

---

## Поля

### `source`

| Значение | Операция |
|----------|----------|
| `edit` | typing / Enter / AG Grid undo edit |
| `paste` | Ctrl+V |
| `fillDown` | Ctrl+D |
| `fillHandle` | drag corner |
| `clear` | Delete |
| `undo` / `redo` | clipboard command stack |

### `changes[]`

| Поле | Описание |
|------|----------|
| `rowId` | stable id (`_rowId` или `rowIdField`) |
| `rowIndex` | displayed row index |
| `colId` | AG Grid column id |
| `field` | business field |
| `oldValue` / `newValue` | до / после |
| `row` | snapshot row data |
| `section` | `"body"` \| `"summary"` — логическая секция строки |

### `range`

Bounding box batch: `startRowId`, `endRowId`, `startColId`, `endColId`, опционально `minRowIndex`…`maxColIndex`.

---

## Правила

1. **`onValidateCells`** — sync, до commit. Reject → revert всего batch.
2. **`onSaveCells`** — async ok. `false` / throw → revert grid + `sourceData`.
3. Paste 20 ячеек = **1** `onSaveCells`, не 20.
4. Merge/spanned: только **логические** editable ячейки в `changes`.
5. Summary: ветвление по `change.section` — см. [sections-and-summary.md](sections-and-summary.md).

---

## Пример (server save)

```js
onSaveCells: async ({ source, changes }) => {
    const payload = changes.map(({ rowId, field, newValue }) => ({
        row_id: rowId,
        field,
        value: newValue
    }));
    const res = await frappe.call({
        method: "my_app.api.update_cells",
        args: { source, cells: payload }
    });
    if (res.exc) return false;
}
```

---

## Server side-effects (другие строки)

`onSaveCells` коммитит **только** `changes` из UI. Если сервер дописал другие строки
(каскад дат родителя, rollup, …), верни их в ответе и примени через:

```js
table.applyExternalCellValues([
    { id: "TASK-PARENT", field: "exp_end_date", value: "2026-08-20" },
    // или tree path: { rowId: "ROOT:TASK-PARENT", field: "exp_end_date", value: "…" }
]);
```

Это тот же путь, что у обычного commit: **grid copy + `sourceData`**, без
`onValidateCells` / повторного `onSaveCells`.

Нельзя:

- ❌ писать только `node.data` / `refreshCells` — tree grid-строка это **копия**
  (`makeVisibleRow` spread); `sourceData` останется stale и перетрёт UI при
  следующем flatten/refresh
- ❌ звать `commitCellChanges` для side-effect — снова уйдёт в `onSaveCells`
