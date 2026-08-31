# Select columns

Как корректно делать колонки выбора в DinextTable.

Общий API: [`../README.md`](../README.md).  
Presets: [`columns-and-formatting.md`](columns-and-formatting.md).  
Batch save / fill: [`cell-changes.md`](cell-changes.md), [`selection-clipboard-navigation.md`](selection-clipboard-navigation.md).

---

## Контракт значения

| | |
|--|--|
| Storage | option **key** `string` или `null` |
| Не использовать | произвольная строка вне списка; object `{ value, label }` в row |
| Preset | `type: "select"` |
| Options | `cellEditorParams.values`: `string[]` или `(params) => string[]` |
| Labels (optional) | `cellEditorParams.labels`: `{ [key]: display }` |

Ядро даёт:

- `valueParser` — paste / typed → key \| `null` (label тоже матчится; **unknown → `null`**, не raw)
- `valueFormatter` — key as-is; `labels[key]` если задан; иначе `__(key)` если есть `__`
- участие в **fill-handle / paste / clear**, когда `edit` разрешает ячейку
- filter остаётся **text** (`resolveFilterKind` не выделяет select)

Ядро **не** ставит Desk `ControlSelect` и **не** вешает default `cellEditor` на preset.

Пустой `values` → любой paste unmatched → `null`.

---

## Минимальная колонка (fill/paste + свой editor)

```js
{
    field: "priority",
    headerName: __("Priority"),
    type: "select",
    edit: true, // или (row) => …
    cellEditorParams: {
        values: ["High", "Medium", "Low"],
        // labels: { High: __("High"), Medium: __("Medium"), Low: __("Low") },
    },
    cellEditor: MySelectCellEditor, // обязателен для удобного одиночного edit
}
```

Таблица:

```js
DinextTable.create({
    edit: true,
    selection: { enabled: true },
    clipboard: { enabled: true },
    fillHandle: { enabled: true },
    columns: [/* … */],
    onValidateCells,
    onSaveCells, // persist option keys
});
```

Без `cellEditor` одиночный edit уйдёт в дефолтный text editor AG.  
Fill/paste при этом всё равно работают (копируют scalar key; unknown → `null`).

`values` per-row:

```js
cellEditorParams: {
    values: (params) => params.data?.allowed || [],
}
```

---

## Desk UX: Frappe ControlSelect (domain)

Select Frappe — **в приложении**, как AG Grid `cellEditor` (не click-replace DOM, не `edit: false`).

Паттерн:

1. `type: "select"` — контракт ядра  
2. `edit: (row) => …` — права  
3. `cellEditorParams.values` — список ключей (и опционально `labels`)  
4. `cellEditor: FrappeSelectCellEditor` — `make_control({ fieldtype: "Select" })`  
5. **in-cell** editor (без `cellEditorPopup` / `isPopup`)  
6. `getValue()` → option key (`null` если пусто / unknown)  
7. на `change` → `params.stopEditing()`  
8. `destroy()` — снять control  

Пример живого editor: `dinext_project_tasks_gantt` → `task_tree_gantt/table/columns/frappe-select-editor.js` (Status / Priority).

Не смешивать:

- ❌ `edit: false` + свой click-handler «вместо» editor (ломает fill)  
- ❌ `cellEditorPopup` + CSS «подогнать» popup под row height  
- ❌ писать ControlSelect / Task meta в `dinext_common` columnTypes  
- ❌ оставлять unmatched paste как raw string (parser ядра даёт `null`)

---

## Опциональный native editor из ядра

Если Desk Select не нужен:

```js
{
    type: "select",
    edit: true,
    cellEditorParams: { values: ["A", "B"] },
    cellEditor: DinextTable.SelectCellEditor, // native <select>
}
```

Хелпер: `DinextTable.parseSelectValue(raw, options, { labels })`.

---

## Save

В `onSaveCells` уходит уже нормализованный key (после parser / editor `getValue`).  
Серверу Frappe обычно достаточно строки-ключа или `null`.

---

## Чеклист

- [ ] row field = option key \| `null`  
- [ ] `type: "select"`  
- [ ] `cellEditorParams.values` задан  
- [ ] `edit` разрешает нужные строки  
- [ ] `cellEditor` (Frappe в domain или `DinextTable.SelectCellEditor`)  
- [ ] `selection` + `clipboard` / `fillHandle`, если нужен mass copy  
- [ ] `onSaveCells` пишет ключи, не display labels  
