# Sorting — гайд

Клиентская сортировка **source-tree** (не AG Grid flat sort). Sibling-списки на каждом уровне; merge-блок — атом; `summaryRows` не трогаем.

**См. также:** [`../README.md`](../README.md), [merge-group-and-tree.md](merge-group-and-tree.md), [row-reorder.md](row-reorder.md).

---

## Модель

```
data (source)
  └─ siblings L0  → sort atoms
       └─ children → sort atoms (рекурсия)
```

**Atom** = одна строка **или** непрерывный merge-блок `[head … tail]`.  
Ключ сортировки — значение поля на **head** (для merge) / на самой строке.

AG `sortable` остаётся `false`: иначе Client-Side Row Model переставит плоский `rowData` и сломает tree/merge.

---

## Options

```js
DinextTable.create({
    sort: {
        enabled: true,          // default false (opt-in)
        multi: false,           // v1: одна колонка; multi — позже
        nulls: "last",          // "last" | "first"
        state: [{ field: "name", dir: "asc" }], // начальное / controlled
        // per-field comparator (optional)
        // comparators: { value: (a, b, ctx) => number }
    },
    columns: [
        { field: "name", headerName: "Name" },
        { field: "value", headerName: "Value", sortable: false } // opt-out колонки
    ],
    onSortChange: ({ sort, table }) => { /* ... */ }
});
```

| Key | Default | Описание |
|-----|---------|----------|
| `sort.enabled` | `false` | Включить header-click + API |
| `sort.multi` | `false` | Зарезервировано; v1 игнорирует |
| `sort.nulls` | `"last"` | Позиция `null` / `undefined` / `""` |
| `sort.state` | `[]` | `[{ field, dir: "asc"\|"desc" }]` |
| `column.sortable` | `true` если layer on | `false` — колонка не кликабельна |
| `onSortChange` | — | После смены state (и apply) |

---

## API

```js
table.getSort();                         // [{ field, dir }]
table.setSort([{ field: "name", dir: "asc" }]);
table.clearSort();
table.isSortEnabled();
table.isColumnSortable("name");
```

Header click cycle (если колонка sortable): `none → asc → desc → none`.

---

## Поведение по кейсам

| Кейс | Поведение |
|------|-----------|
| Flat | sort top-level `data` |
| Eager tree | siblings на каждом уровне |
| Lazy `setRowChildren` | новые children сразу сортируются текущим state |
| Merge-группа | блок целиком; ключ с head |
| Summary | **не** сортируется |
| Row reorder | после DnD sort **сбрасывается** (ручной порядок wins) |
| `refresh(data)` | если state не пуст — apply к новому source |

---

## Ограничения v1

- Одна колонка (не multi-sort).
- Ключ = `row[field]` (не DOM / не custom render).
- Нет server/`external` mode — при необходимости `onSortChange` + свой fetch, `sort.enabled: false`.
- Типы: number / string / boolean / Date; иначе `String(value)`.

---

## Чеклист клиента

- [ ] `sort.enabled: true`
- [ ] Колонки с `sortable: false` где не нужно
- [ ] Merge: корректные `mergeGroup*` на блоках
- [ ] Не полагаться на AG `defaultColDef.sortable`
- [ ] После programmatic `data` reorder — `clearSort` или новый `setSort`
