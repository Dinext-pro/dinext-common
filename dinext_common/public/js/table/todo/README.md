# DinextTable — backlog улучшений ядра

Отдельный список задач по `public/js/table/core/` и контрактам API.  
Не путать с клиентскими сценариями — те в [`../usage-guides/`](../usage-guides/).

Формат пункта: `- [ ] кратко — контекст / критерий готовности`

---

## Техдолг (sections + tree)

- [x] **Dedupe expand/collapse** — `expandRow` / `expandSummaryRow`, `collapseRow`, `clearExpandedDescendants` / `clearSummaryExpandedDescendants`. Shared `expandTreeRow` / `collapseTreeRow` / `clearExpandedDescendantIds` в `tree/expand.js`. Body: `revealChildren` → `insertVisibleChildren` (eager only); summary: → `syncSummarySection`. Unit: `@tests/tree-expand.test.mjs`.

- [x] **`getRowClass` chain** — `chainRowClassHandlers` + merge в `mergeGridOptions`. SectionMixin только отдаёт `dinext-table-row--summary`; user `gridOptions.getRowClass` склеивается автоматически. Unit: `@tests/grid-options-merge.test.mjs`.

- [ ] **`treeContentKey` (opt-in)** — tree cell `refresh` уже skip remount body, если `_rowId` + `value` те же (chevron отдельно; меньше мигания `<img>`). Если domain рисует тело из полей вне `value` (avatar URL, meta) и они меняются без смены value — добавить `options.treeContentKey(params) => string` в ключ. Не угадывать domain-поля в ядре. Критерий: WR/другой client реально ловит stale body → API + README + unit.

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

## Sort

- [x] **v1 client sort layer** — `core/sort/` + [sorting.md](../usage-guides/sorting.md): siblings recursive, merge atoms, summary out, lazy `setRowChildren`, clear on row-reorder. Unit: `@tests/sort-model.test.mjs`.

- [ ] **Multi-sort** — `sort.multi: true` + Shift+click (API `cycleSortState` уже имеет ветку).

- [ ] **External / server sort** — `sort.mode: "external"`: только `onSortChange`, не мутировать `data`.

- [ ] **Browser smoke** — header cycle + tree + merge на доменных экранах (WE / P&L).

---

## Fullscreen

- [x] **Enter/exit hooks** — `fullscreen.onEnter` / `onExit` + top-level `onFullscreenEnter` / `onFullscreenExit`; fire on real `fullscreenchange` transitions (Esc included).

---

## API / docs sync

- [x] **README vs fill-handle** — синхронизировано: fill handle в [selection-clipboard-navigation.md](selection-clipboard-navigation.md).

- [ ] **Computed summary** — осознанно вне ядра; при необходимости тонкий helper `table.recalcSummary(fn)` — отдельное решение, не автomatism в core.

---

## Row check (done v1)

- [x] **Row check layer** — `core/row-check/` + toolbar preset `rows` (add/delete/duplicate/move ±1) + nudge via row-reorder commit. Guide: [row-check.md](../usage-guides/row-check.md). Domain migrate (WE `_selected`, UT toolbar) — отдельно.

---

## Row reorder tree (done)

- [x] **Tree reparent DnD** — `allowTree: "reparent"`: before/after cross-parent + nest inside, gap/frame UX, expand-after-drop (no hover expand), path remap (`expandedIds` / checked), selection muted while dragging. Guide: [row-reorder.md](../usage-guides/row-reorder.md). Unit: `@tests/row-reorder.test.mjs`.

### Follow-ups

- [ ] **Persist consumers** — Task tree / WE: `onRowReorder` + server parent/order (сейчас UI-only smoke на Task).
- [ ] **Lazy nest merge** — drop inside unloaded parent → children = [moved]; `expandRow` skips `onExpandRow` (уже не empty). Нужен merge server children + moved row.
- [ ] **Domain side-effects** — gantt/filters sync после reorder (`onTreeChange` сейчас не из reorder).
- [ ] **Sort + reorder** — DnD blocked while sorted; UX clear-sort on drag start?
- [ ] **Merge reparent** — blocked by design (flatten); confirm product need.

---

## Filter (column search)

Гайд: [filtering.md](../usage-guides/filtering.md).  
Решения: tree **A** (match + ancestors, v2); toggle **Keep** state; scope **flat-first**.

- [x] **Filter layer** — `core/filter/` + auto toolbar search (как rowCheck) + floating row + tree match+ancestors + unit `@tests/filter-model.test.mjs`.
- [x] **Filter row UI** — AG floatingFilter + noop parent filter; `filterable: false` opt-out; system cols без инпута.

---

## Когда брать в работу

| Триггер | Задача |
|---------|--------|
| Снова правим tree expand | Dedupe expand/collapse |
| Tree body stale при том же `value` (avatar/meta) | `treeContentKey` opt-in |
| Появился 3-й тип секции (header, side total) | Generic `sections[]` |
| Summary tree в prod-клиенте | Browser smoke + collision guard |
| Жалобы на случайный paste в итоги | `summary.edit: false` by default |

---

_Добавляйте новые пункты в конец секции или создавайте `todo/YYYY-MM-topic.md` для больших эпиков._
