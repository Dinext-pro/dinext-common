# Колонки и форматирование

Справочник по `columns[]`, пресетам редакторов и styling passthrough в AG Grid.

Общий API: [`../README.md`](../README.md).

---

## DinextTable keys

| Key | Default | Описание |
|-----|---------|----------|
| `field` | — | Поле в row data |
| `headerName` | — | Заголовок |
| `edit` | inherit `options.edit` | `boolean` или `(row, field) => boolean`; **приоритет выше global** |
| `render` | — | Tree col 0: inner content; indent + chevron — ядро |
| `tree` | `true` на col 0 | `false` — без tree chrome |
| `cellRenderer` | — | Full override без compose (advanced) |
| `type` | — | Preset: `text`, `number`, `integer`, `date`, `select` |

**Tree col 0:** `[inset 8px + level×20][chevron|spacer][render(params)]`. Expand — **клик по chevron**.

---

## Editors (columnTypes presets)

Ядро регистрирует `gridOptions.columnTypes`:

| Preset | `cellDataType` | По умолчанию |
|--------|----------------|--------------|
| `text` | `text` | — |
| `number` | `number` | `--align-right`, locale `valueParser`, default `NumberCellEditor` |
| `integer` | `number` | как `number`, `Math.trunc` |
| `date` | `text` | ISO `YYYY-MM-DD` \| `null`; `valueParser` / `valueFormatter`; **без** default `cellEditor` |
| `select` | `text` | option key \| `null`; unknown paste → `null`; `cellEditorParams.values`; **без** default `cellEditor` |
| `checkbox` / `boolean` | `boolean` | AG checkbox renderer/editor |

`parseLocaleNumber` / `parseDateValue` / `parseSelectValue` — экспорт из `editors.js`.

**Date columns:** полный гайд — [`date-columns.md`](date-columns.md). Desk calendar (`ControlDate`) — в domain `cellEditor`, не в preset.

**Select columns:** полный гайд — [`select-columns.md`](select-columns.md). Desk Select (`ControlSelect`) — в domain `cellEditor`, не в preset.

---

## Layout & display (passthrough AG Grid)

`width`, `flex`, `minWidth`, `maxWidth`, `pinned`, `hide`, `cellDataType`, `valueFormatter`, `valueParser`, `cellEditor`, `cellEditorParams` — уходят в AG Grid как есть.

`pinned: "right"` — intent («итоги справа»). Runtime pin владеет ядро: default `pinEnd.mode: "auto"` снимает pin, пока колонки влезают в body; overflow → снова `right`. `pinEnd: { mode: "always" }` — как AG Grid (всегда к правому краю). `options.columns[].pinned` не мутируется.

---

## Три слоя форматирования

| Слой | Когда | API |
|------|-------|-----|
| Значение | число, дата, текст | `valueFormatter`, `cellDataType` |
| Стиль | цвет, фон, выравнивание | `cellClass`, `cellClassRules`, `cellStyle` |
| Структура | avatar, badge, составная ячейка | `render` или `cellRenderer` |

На tree col 0 `cellClass` / `cellClassRules` — на внешней `.ag-cell`. Align inner content — класс внутри `render`.

Utility-классы (`dinext-table.css`): `dinext-table-cell--align-right`, `--align-center`, `--negative`, `--highlight`, `--readonly`.

Row-level: `gridOptions.getRowClass`, `getRowStyle`, `rowClassRules`. Summary rows: ядро добавляет `dinext-table-row--summary` (см. [sections-and-summary.md](sections-and-summary.md)).

---

## Default col def

Через `defaultColDef` или `gridOptions.defaultColDef`. Ядро merge:

| Key | Value |
|-----|-------|
| `resizable` | `true` |
| `sortable` | `false` (AG flat sort off; см. [sorting.md](sorting.md)) |

`column.sortable` — флаг **слоя sort** (header cycle), не AG. При `sort.enabled: true` по умолчанию колонка кликабельна; `sortable: false` — opt-out.

При edit ядро также задаёт `enableCellChangeFlash`, `cellClassRules` для readonly.

---

## Пример

```js
columns: [
    {
        field: "value",
        headerName: "Value",
        type: "number",
        cellClassRules: {
            "dinext-table-cell--negative": (p) => p.value < 0,
            "dinext-table-cell--highlight": (p) => p.value >= 800,
        },
        valueFormatter: (p) => p.value == null ? "" : `${p.value} ₽`,
    },
],
gridOptions: {
    columnTypes: {
        money: {
            type: "numericColumn",
            cellClass: "dinext-table-cell--align-right",
            valueFormatter: (p) => fmtMoney(p.value),
        },
    },
},
```
