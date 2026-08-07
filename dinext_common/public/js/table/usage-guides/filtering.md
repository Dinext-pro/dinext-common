# Filtering — гайд

Клиентский **column filter** как отдельный layer (не AG Client-Side filter как source of truth). Source `data` не мутируем; режем **visible** body rows.

**См. также:** [`../README.md`](../README.md), [sorting.md](sorting.md), [merge-group-and-tree.md](merge-group-and-tree.md).

---

## Модель

```
data (source) → sort (если on) → visible rows → filter → grid rowData
```

Toolbar search icon ↔ показать/скрыть **filter row** под header (инпут на filterable-колонку).  
`state` фильтров **живёт** при закрытии UI (Keep); clear — только API / очистка инпута.

---

## Options

```js
DinextTable.create({
    filter: {
        enabled: true,       // default true
        active: false,       // UI filter row visible (toolbar toggle)
        state: {},           // { [field]: string }
        mergeMatchMode: "atom",    // "rows" → only matching merge rows
        mergeAncestorMode: "atom", // "head" → compact merge ancestor in tree
        mergeInheritedFields: [],  // head-owned fields inherited by merge tails
    },
    columns: [
        { field: "name", headerName: "Name" },
        { field: "id", headerName: "Id", filterable: false }
    ],
    // toolbar.presets default includes "filter"
    onFilterChange: ({ filter, active, table }) => { /* ... */ }
});
```

| Key | Default | Описание |
|-----|---------|----------|
| `filter.enabled` | `true` | Layer + search icon в toolbar (auto-inject) |
| `filter.active` | `false` | Filter row под header |
| `filter.state` | `{}` | `{ field: queryString }` |
| `filter.mergeMatchMode` | `"atom"` | `"rows"` оставляет только совпавшие строки внутри merge-группы и пересобирает display merge |
| `filter.mergeAncestorMode` | `"atom"` | `"head"` оставляет одну head-строку merge-группы, если совпал только tree-потомок |
| `filter.mergeInheritedFields` | `[]` | Поля merged-head, которые tail-строки наследуют при фильтрации |
| `column.filterable` | `true` если layer on | `false` — нет инпута |
| `onFilterChange` | — | После смены `state` / `active` / clear |

System cols (`rowCheck`) — всегда вне filter.  
Иконка поиска **всегда** в toolbar при `filter.enabled` (как rowCheck), даже если consumer задал свой `toolbar.presets`.  
Отключить: `filter: { enabled: false }`.

### Persist (localStorage)

Тот же `toolbar.persistKey`, что и pin:

```js
toolbar: {
  persistKey: "work-efforts:PROJ-001", // уникально на таблицу/контекст
}
```

Пишет JSON `{ pinned, filter: { active, state } }`.  
Legacy `"1"`/`"0"` (только pin) читается; следующий save мигрирует в JSON.  
Без `persistKey` — filter/pin не сохраняются.

---

## API

```js
table.isFilterEnabled();
table.isFilterRowOpen();
table.isFilterActive();            // непустой state (UI может быть закрыт)
table.toggleFilterRow(force?);     // UI only; state keep
table.getFilter();                 // { ...state }
table.setFilter({ name: "foo" });
table.setFilterField("name", "foo");
table.clearFilter();
table.isColumnFilterable("name");
```

Семантика: **AND** по колонкам. Операторы зависят от `column.type` / `cellDataType` (или `filterKind`).

### Операторы

| Kind | Query | Значение |
|------|-------|----------|
| text (default) | `foo` | contains (ci) |
| text | `=foo` | exact (ci) |
| text | `!foo` / `-foo` | not contains |
| text | `">1"` | literal contains (escape) |
| number / integer | `>1` `>=1` `<1` `<=1` `=1` `<>1` `!=1` | compare |
| number | `10` (без op) | contains по string |
| date | те же compare | ISO / `DD.MM.YYYY` |
| any | `"..."` | literal contains |

На **text** `>1` — это contains строки `">1"`, не greater-than.  
Невалидный операнд на number/date (`>abc`) → строка не проходит.

---

## Поведение по кейсам

| Кейс | Поведение |
|------|-----------|
| Flat | hide rows без match |
| Merge-группа | self-match: atom целиком или совпавшие rows по `mergeMatchMode`; descendant-only: atom или head по `mergeAncestorMode` |
| Summary | **вне** filter (всегда visible) |
| Selection | при apply — clear ranges |
| Row-check / delete | display layer; checked Set / source не трогаем |
| Row reorder | при активном filter (непустой state) — blocked |
| Sort + filter | sort source → filter visible |
| Toggle UI off | **Keep** state; повторный on — те же инпуты |
| Tree nested | **match + ancestors**; auto-expand ancestors только для display (не пишет `expandedIds`) |
| `refresh(data)` | применить текущий `state` к новому source |

---

## Tree

Политика: **match + ancestors**. Не matching siblings/descendants скрыты.  
При активном filter expand не добавляет строки напрямую из source: видимость
потомков остаётся результатом той же filter projection. Lazy children после
загрузки запускают один повторный расчёт projection.
Collapse после clear filter — прежний `expandedIds` пользователя.

---

## Ограничения

- Нет диапазона `1..10`, OR в одном инпуте, regex.
- Floating row = AG floatingFilter + noop parent filter; visibility via `rowData`.

---

## Чеклист клиента

- [ ] Иконка поиска есть при `filter.enabled` (default true); иначе `filter: { enabled: false }`
- [ ] `filterable: false` на служебных колонках
- [ ] Не полагаться на AG column `filter` как на public API ядра
