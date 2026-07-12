# DinextTable — backlog улучшений ядра

Отдельный список задач по `public/js/table/core/` и контрактам API.  
Не путать с клиентскими сценариями — те в [`../usage-guides/`](../usage-guides/).

Формат пункта: `- [ ] кратко — контекст / критерий готовности`

---

## Техдолг (sections + tree)

- [x] **Dedupe expand/collapse** — `expandRow` / `expandSummaryRow`, `collapseRow`, `clearExpandedDescendants` / `clearSummaryExpandedDescendants`. Shared `expandTreeRow` / `collapseTreeRow` / `clearExpandedDescendantIds` в `tree/expand.js`. Body: `revealChildren` → `insertVisibleChildren` (eager only); summary: → `syncSummarySection`. Unit: `@tests/tree-expand.test.mjs`.

- [x] **`getRowClass` chain** — `chainRowClassHandlers` + merge в `mergeGridOptions`. SectionMixin только отдаёт `dinext-table-row--summary`; user `gridOptions.getRowClass` склеивается автоматически. Unit: `@tests/grid-options-merge.test.mjs`.

---

## Sections / summary (v2)

- [ ] **Generic `sections[]`** — сейчас hardcoded `body | summary`. Будущая модель: массив секций с `id`, `rows`, `pin`, guards; `_section` = section id.

- [ ] **Pin policies** — `summary.pin: 'top'`, несколько pinned bands, `pin: false` уже есть.

- [ ] **Collision guard `rowId`** — при init предупреждение (console / throw opt-in), если `id` из `summaryRows` резолвится в body через `findSourceRow` (body wins сейчас — дисциплина клиента).

- [ ] **`summary.edit` default** — сейчас `true`. Рассмотреть `false` (read-only footer по умолчанию) + явный opt-in; обновить гайд [`sections-and-summary.md`](../usage-guides/sections-and-summary.md).

---

## Тесты

- [ ] **Browser smoke: summary edit** — pinned row, typing, `onSaveCells` с `section: "summary"`, revert on `false`.

- [ ] **Browser smoke: summary tree** — eager + lazy expand на pinned; `onExpandRow` с `section: "summary"`.

- [ ] **Pinned + selection/clipboard edge cases** — focus body↔summary, Ctrl+A, paste bounds; зафиксировать ожидание в гайде или доработать guards.

- [x] **Unit: tree expand ctx** — `@tests/tree-expand.test.mjs` (mock ctx, no DOM).

---

## Selection / clipboard / span

- [ ] **Selection + rowSpan** — в [`merge-group-and-tree.md`](../usage-guides/merge-group-and-tree.md) зафиксировано «не идеал». Улучшить highlight/mask для merged cells или явно scope as wontfix.

- [ ] **`enableCellSpan` initial-only** — документировано; при необходимости resync span после `refresh` / tree expand.

---

## API / docs sync

- [x] **README vs fill-handle** — синхронизировано: fill handle в [selection-clipboard-navigation.md](selection-clipboard-navigation.md).

- [ ] **Computed summary** — осознанно вне ядра; при необходимости тонкий helper `table.recalcSummary(fn)` — отдельное решение, не автomatism в core.

---

## Когда брать в работу

| Триггер | Задача |
|---------|--------|
| Снова правим tree expand | Dedupe expand/collapse |
| Появился 3-й тип секции (header, side total) | Generic `sections[]` |
| Summary tree в prod-клиенте | Browser smoke + collision guard |
| Жалобы на случайный paste в итоги | `summary.edit: false` by default |

---

_Добавляйте новые пункты в конец секции или создавайте `todo/YYYY-MM-topic.md` для больших эпиков._
