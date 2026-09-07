# Sections и summary rows

Как подключать **итоговые строки** (totals, subtotals) как вторую логическую секцию таблицы, а не как «сырой» `pinnedBottomRowData` мимо ядра.

Общий API: [`../README.md`](../README.md). Batch edit: [`cell-changes.md`](cell-changes.md).

---

## Зачем отдельная секция

| Подход | Проблема |
|--------|----------|
| Клиент сам кладёт строки в `gridOptions.pinnedBottomRowData` | Ядро не знает source of truth → `findSourceRow`, `onSaveCells`, tree/merge не работают |
| Итоги смешаны в `data[]` | Сложно отделить paste/fill/selection; риск случайной мутации totals |

**Контракт DinextTable:** body = `options.data`, summary = `options.summaryRows`. Ядро синхронизирует summary → `pinnedBottomRowData` (pin bottom по умолчанию).

---

## Минимальный пример

```js
DinextTable.create({
    container,
    edit: true,
    data: [
        { id: 1, name: "Row A", amount: 100 },
        { id: 2, name: "Row B", amount: 250 }
    ],
    summaryRows: [
        { id: "total", name: "Итого", amount: 350 }
    ],
    columns: [
        { field: "name", headerName: "Name", flex: 1 },
        { field: "amount", headerName: "Amount", width: 120, type: "number" }
    ],
    onSaveCells: async ({ changes }) => {
        for (const { section, rowId, field, newValue } of changes) {
            if (section === "summary") {
                await saveSummaryCell(rowId, field, newValue);
            } else {
                await saveBodyCell(rowId, field, newValue);
            }
        }
    }
});
```

---

## Options

| Key | Тип | Default | Описание |
|-----|-----|---------|----------|
| `summaryRows` | `row[]` | `[]` | Top-level строки summary-секции (тот же контракт, что `data`) |
| `summary.pin` | `"bottom"` \| `false` | `"bottom"` | `"bottom"` → `pinnedBottomRowData`; `false` — только source, без pin |
| `summary.expandedIds` | `string[]` | `[]` | Раскрытые tree-строки **только** в summary (отдельно от body `expandedIds`) |
| `summary.edit` | `boolean` | `true` | `false` — summary не editable даже при `column.edit` |
| `summary.clipboard` | `boolean` | `false` | Paste / fill / clear / copy TSV на summary |
| `summary.selection` | `boolean` | `false` | Range selection на summary |

Runtime: `table.setSummaryRows(rows)` или `table.setOption("summaryRows", rows)`.

---

## Служебное поле `_section`

На **visible** summary-строках ядро ставит `_section: "summary"`. В client source `summaryRows` задавать `_section` не нужно.

Body-строки по умолчанию без `_section` (логически `"body"`).

В `onValidateCells` / `onSaveCells` каждый элемент `changes[]` содержит:

```js
{ rowId, field, oldValue, newValue, row, section: "body" | "summary" }
```

---

## Pin bottom — policy отображения

Summary живёт в **отдельном** `summarySourceData` / `summaryRowData`. Pin — только способ показа (один scroll viewport body, итоги закреплены снизу).

Не передавайте `pinnedBottomRowData` в `gridOptions` сами — ядро перезапишет при `summaryRows.length > 0`.

---

## Merge + tree на summary

На summary работают те же правила, что в [`merge-group-and-tree.md`](merge-group-and-tree.md):

- merge metadata: `mergeGroupId`, `mergeGroupIndex`, `mergeGroupSize`
- `children` / `hasChildren` только на **head** merge-группы (`mergeGroupIndex === 0`)
- lazy expand: `onExpandRow` получает `section: "summary"`; пишите children через `table.setRowChildren(rowId, children)`

**Expand/collapse в summary:** ядро пересобирает `pinnedBottomRowData` (`syncSummarySection`), а не `applyTransaction` на center rows.

**ID:** `rowIdField` в summary не должен совпадать с body на том же path-level, иначе `findSourceRow` вернёт body-строку. Префикс в id (`"total"`, `"sum-1"`) — нормальная практика.

---

## Guards (paste / selection)

По умолчанию summary **не** участвует в:

- range selection (`summary.selection: false`)
- clipboard batch (`summary.clipboard: false`)

Прямой edit ячейки summary (typing) — **разрешён**, если `summary.edit !== false` и колонка editable.

Чтобы totals участвовали в Ctrl+V / выделении:

```js
summary: {
    clipboard: true,
    selection: true
}
```

---

## CSS

Ядро вешает `dinext-table-row--summary` на pinned summary-строки. Стили — в `dinext-table.css`; можно дополнить через `gridOptions.getRowClass` (ядро склеивает с user callback).

Горизонтальное выравнивание summary **по центру** по умолчанию (в т.ч. поверх column `align-right` / number presets). Body-колонки не меняются.

---

## Чеклист клиента

1. Body в `data`, итоги в `summaryRows` — не смешивать.
2. Уникальные `id` между секциями.
3. `onSaveCells` — ветка по `change.section`.
4. Не трогать `pinnedBottomRowData` вручную.
5. Paste/fill на totals — только если явно `summary.clipboard: true`.
