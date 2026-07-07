# Merge-группа + Tree — гайд для клиентов

Краткий справочник: как собирать отчёты, где несколько **отображаемых** строк объединяются в одной колонке (`rowSpan`), а у группы есть **expand/collapse** (eager или lazy children).

**См. также:** [`../README.md`](../README.md) (общий API), [`../test-data.js`](../test-data.js) + страница `dinext-table-test` (живой demo).

---

## Что такое merge-группа

**Не отдельный DocType.** Это контракт метаданных на **соседних** строках в `data`:

| Поле | Где | Значение |
|------|-----|----------|
| `mergeGroupId` | все строки группы | один id, напр. `"g-1"` |
| `mergeGroupIndex` | каждая строка | `0` = head, `1…N-1` = tail |
| `mergeGroupSize` | все строки группы | число строк в группе (≥ 2) |

**Head** (`index === 0`) — единственный владелец tree:

- `children: [...]` (eager) **или** `hasChildren: true` (lazy)
- expand/collapse по `_rowId` head
- chevron в первой колонке (обычно в центре merged-ячейки)

**Tail** — только layout: свои значения в остальных колонках, **без** `children` / `hasChildren`.

Строки группы в `data` идут **подряд**: head, затем tail(ы).

---

## Минимальный пример

### 1. Data

```js
const data = [
    {
        id: "1",
        mergeGroupId: "g-1",
        mergeGroupIndex: 0,
        mergeGroupSize: 2,
        a: "Общий текст",
        b: "B-1",
        children: [{ id: "1.1", a: "1.1", b: "B-1.1" }]
    },
    {
        id: "2",
        mergeGroupId: "g-1",
        mergeGroupIndex: 1,
        mergeGroupSize: 2,
        a: "",
        b: "B-2"
    }
];
```

### 2. Колонки + AG Grid span

```js
DinextTable.create({
    container,
    data,
    columns: [
        {
            field: "a",
            headerName: "A",
            render: (params) => { /* tree label */ },
            spanRows: DinextTable.createMergeGroupSpanRows()
        },
        { field: "b", headerName: "B" }
    ],
    gridOptions: {
        enableCellSpan: true   // обязательно для spanRows; initial-only
    }
});
```

`spanRows` ставьте **только на колонках, где нужен merge**. Остальные колонки — одна ячейка на строку.

### 3. Lazy load (опционально)

На **head** — `hasChildren: true`, без массива `children`:

```js
{
    id: "3",
    mergeGroupId: "g-2",
    mergeGroupIndex: 0,
    mergeGroupSize: 2,
    a: "Lazy group",
    hasChildren: true
}
```

```js
DinextTable.create({
    // ...
    onExpandRow: async ({ rowId, row, table }) => {
        const children = await fetchChildren(row.id);
        table.setRowChildren(rowId, children);
    }
});
```

Без `setRowChildren` expand откатится. Пока fetch — chevron pulse (`_treeLoading`).

---

## Правила (обязательно)

1. **`children` / `hasChildren` только на head** (`mergeGroupIndex === 0`).
2. **Строки группы подряд** в массиве `data`, индексы `0…size-1` без пропусков.
3. **Один `mergeGroupId`** — одна непрерывная цепочка строк; не разрывать другими row.
4. **Children в grid вставляются после tail** группы (ядро делает само) — merge в колонке A не ломается.
5. **`enableCellSpan: true`** в `gridOptions` при `spanRows`.
6. **Не совмещать** `colSpan` и `spanRows` на **одной** колонке (ограничение AG Grid).
7. **Tree-колонка** — первая (`columns[0]`), `tree !== false`. Chevron рисуется ядром.

---

## Кастомные имена полей

```js
DinextTable.create({
    mergeGroup: {
        idField: "mgId",
        indexField: "mgIndex",
        sizeField: "mgSize"
    },
    columns: [{
        field: "a",
        spanRows: DinextTable.createMergeGroupSpanRows({ mergeGroup: { /* те же имена */ } })
    }]
});
```

---

## Eager vs lazy в merge-группе

| | Eager | Lazy |
|--|-------|------|
| Head data | `children: [...]` | `hasChildren: true` |
| Expand | сразу в grid | `onExpandRow` → `setRowChildren(rowId, …)` |
| Повторный expand | из `sourceData` | из кэша в `sourceData` (если не очистили) |

`rowId` в callbacks — id **head** (для top-level merge это `"1"`, `"3"`, …).

---

## Чеклист перед сдачей

- [ ] Head + tail(s) с одним `mergeGroupId`, индексы 0…size-1
- [ ] `mergeGroupSize` совпадает с числом строк группы
- [ ] `children` / `hasChildren` только на head
- [ ] `spanRows` + `enableCellSpan` на нужных колонках
- [ ] Lazy: `onExpandRow` всегда вызывает `setRowChildren`
- [ ] Demo: expand/collapse — merge не «прыгает», children под tail
- [ ] Edit/save: `onSaveCells` получает `changes[]` с `rowId` каждой логической строки (head и tail разные id)

---

## Чего не делать

| Антипаттерн | Почему |
|-------------|--------|
| `children` на tail | два источника правды, expand непредсказуем |
| expand у каждой строки merge | rowSpan + insert после parent ломают merge |
| span на все колонки «на всякий случай» | лишние ограничения selection/clipboard |
| sort/filter по merged-отчёту | AG Grid span + sort дают странные результаты |
| rowSpan через несколько merge-групп | span только внутри одного `mergeGroupId` |

---

## Demo в репозитории

| Кейс | Строки test-data |
|------|------------------|
| merge + eager | 1–2 |
| merge + lazy | 3–4 |
| tree eager | 5, 10 |
| tree lazy | 7 |

Страница: **DinextTable Test** → Recreate → expand chevron.

---

## Ограничения (не баги ядра)

- **Range selection / clipboard** — прямоугольник по индексам; merged-ячейки AG Grid обрабатывает не идеально.
- **Pinned + span** — span не пересекает pin-зону.
- **`enableCellSpan`** — только при create, потом не переключить.
- **Вложенный tree под merge** — поддерживается; у child-своих merge-групп те же правила на их уровне.

---

## Тесты

Unit-тесты: [`../@tests/`](../@tests/) (рядом с `core/`).

```bash
cd frappe-bench/apps/dinext_common
npm run test:dinext-table
```

Новые сценарии:

1. Фикстуры — `@tests/helpers/fixtures.mjs`
2. Новый файл — `@tests/<topic>.test.mjs` (`node:test` + `node:assert/strict`)
3. `run.mjs` подхватит все `*.test.mjs` автоматически
