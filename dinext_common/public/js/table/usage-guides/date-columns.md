# Date columns

Как корректно делать колонки даты в DinextTable.

Общий API: [`../README.md`](../README.md).  
Presets: [`columns-and-formatting.md`](columns-and-formatting.md).  
Batch save / fill: [`cell-changes.md`](cell-changes.md), [`selection-clipboard-navigation.md`](selection-clipboard-navigation.md).

---

## Контракт значения

| | |
|--|--|
| Storage | `string` ISO `YYYY-MM-DD` или `null` |
| Не использовать | `Date` object в row data |
| Preset | `type: "date"` |

Ядро даёт:

- `valueParser` — paste / typed → ISO \| `null` (в т.ч. `DD.MM.YYYY`)
- `valueFormatter` — display (`frappe.format` если есть)
- `cellClass` — `--align-center`
- участие в **fill-handle / paste / clear**, когда `edit` разрешает ячейку

Ядро **не** ставит Desk-календарь (`ControlDate`) и **не** вешает default `cellEditor` на preset.

---

## Минимальная колонка (fill/paste + свой editor)

```js
{
    field: "exp_start_date",
    headerName: __("Start"),
    type: "date",
    edit: true, // или (row) => …
    cellEditor: MyDateCellEditor, // обязателен для удобного одиночного edit
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
    onSaveCells, // persist ISO strings
});
```

Без `cellEditor` одиночный edit уйдёт в дефолтный text editor AG — для дат обычно плохо.  
Fill/paste при этом всё равно работают (копируют scalar ISO).

---

## Desk UX: Frappe ControlDate (domain)

Календарь Frappe — **в приложении**, как AG Grid `cellEditor` (не click-replace DOM, не `edit: false`).

Паттерн:

1. `type: "date"` — контракт ядра  
2. `edit: (row) => …` — права  
3. `cellEditor: FrappeDateCellEditor` — `make_control({ fieldtype: "Date" })`  
4. **in-cell** editor (без `cellEditorPopup` / `isPopup`) — GUI заполняет ячейку  
5. datepicker на `body`, **кроме native fullscreen** — тогда `DinextTable.adoptOverlay` переносит календарь в `fullscreenElement` (`mousedown` → `preventDefault`, иначе `stopEditingWhenCellsLoseFocus` коммитит до `onSelect`)  
6. `getValue()` → ISO / system date string (`null` если пусто)  
7. на `change` / select → `params.stopEditing()`  
8. `destroy()` — снять datepicker / control  

Пример живого editor: `dinext_project_tasks_gantt` → `task_tree_gantt/table/columns/dates/frappe-date-editor.js`.

Не смешивать:

- ❌ `edit: false` + свой click-handler «вместо» editor (ломает fill)  
- ❌ `cellEditorPopup` + CSS «подогнать» popup под row height (ломает рамку/ширину)  
- ❌ писать ControlDate в `dinext_common` columnTypes  
- ❌ хранить в row `Date` и надеяться на AG `cellDataType: "date"`

---

## Опциональный native editor из ядра

Если Desk-календарь не нужен:

```js
{
    type: "date",
    edit: true,
    cellEditor: DinextTable.DateCellEditor, // <input type="date">
}
```

Хелперы: `DinextTable.parseDateValue`, `DinextTable.toIsoDateString`.

---

## Save

В `onSaveCells` уходит уже нормализованное ISO (после parser / editor `getValue`).  
Серверу Frappe обычно достаточно строки `YYYY-MM-DD` или `null`.

---

## Чеклист

- [ ] row field = ISO \| `null`  
- [ ] `type: "date"`  
- [ ] `edit` разрешает нужные строки  
- [ ] `cellEditor` (Frappe в domain или `DinextTable.DateCellEditor`)  
- [ ] `selection` + `clipboard` / `fillHandle`, если нужен mass copy  
- [ ] `onSaveCells` пишет даты без `Date` object  
