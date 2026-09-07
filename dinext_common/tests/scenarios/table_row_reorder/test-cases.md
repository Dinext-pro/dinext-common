# DinextTable row-reorder / tree DnD

Клиентский контракт gutter DnD: жест → preview → `moveRowBlock` → payload `onRowReorder` (то, что gantt шлёт в `reorder_siblings`).

- issue: table row-reorder / tree DnD (dinext_common)
- site: `dev.dinext.localhost` (раннер Node, сайт не трогает)
- owner_app: `dinext_common`
- dependent_apps: []
- primary_surface: `Client Script`
- secondary_surfaces:
  - `UI smoke`
- scenario_dir: `frappe-bench/apps/dinext_common/dinext_common/tests/scenarios/table_row_reorder`
- data_helper: `data_setup.py`
- source_of_truth:
  - `app_code` `dinext_common/public/js/table/core/row-reorder/ops.js`
  - `app_code` `dinext_common/public/js/table/core/row-reorder/preview.js`
  - `app_code` `dinext_common/public/js/table/core/row-reorder/mixin.js`
- sync_required: `no`
- run_targets:
  - `dinext_common/public/js/table/@tests/row-reorder-scenarios.test.mjs`
  - `dinext_common/public/js/table/@tests/row-reorder.test.mjs`
- actors:
  - setup_user: in-memory clone (`data_setup.py` / `row-reorder-fixtures.mjs`)
  - business_user: same (нет DocType)
  - ui_actor: `simulateRowReorder` pipeline (без браузера)
- runtime_inputs:
  - `rowReorder.allowTree`: `false` | `siblings` | `reparent`
  - hitMap снимок на mousedown (не live translateY)
  - `SWAP_EDGE_PX = 2`, `NEST_SHIFT_PX = 24`
  - nest parent = строка **над слотом**, не swap-сосед
  - expanded branch: `collectDraggedRowIds` = корень, preview потомки по prefix
  - commit только логический mouseup; persist снаружи через `onRowReorder`
  - payload: `rowId`, `newRowId`, `fromParentRowId`, `toParentRowId`, `orderedLocalRowIds`, `fromOrderedLocalRowIds`, `blockSize`
- reset_scope:
  - нет site-документов; каждый тест клонирует fixture
- primary_test_artifacts:
  - `dinext_common/public/js/table/@tests/row-reorder-scenarios.test.mjs`
  - `dinext_common/public/js/table/@tests/helpers/row-reorder-fixtures.mjs`
- last_run: 2026-08-30 — Node scenario **61/61** + unit **27/27**

## Status Legend

- ⚪ не составлен
- 🟡 не запущен
- 🟢 пройден
- 🔴 не пройден

## Test Cases

### Flat reorder

- 🟢 TC-01: `a` after `b` → `b,a,c`; payload same-parent order
  - surface: `Client Script`
  - setup: `flat_abc`
  - action: swapDown на `b`
  - assert: ids `b,a,c`; `newRowId=a`; `orderedRowIds` совпадают
  - artifacts: `TC-01 flat drag a after b`
  - actor: `ui_actor`

- 🟢 TC-02: `c` before `a` → `c,a,b`
  - surface: `Client Script`
  - artifacts: `TC-02 flat drag c before a`

- 🟢 TC-03: `b` after `c` → `a,c,b`
  - surface: `Client Script`
  - artifacts: `TC-03 flat drag b after c`

- 🟢 TC-04: `d` before `a` в четырёх строках
  - surface: `Client Script`
  - artifacts: `TC-04 flat drag last before first of four`

- 🟢 TC-05: тот же слот (`a` ещё до `b`) → home/noop, данные не меняются
  - surface: `Client Script`
  - artifacts: `TC-05 same slot a before b is home/noop`

- 🟢 TC-06: курсор на своей строке → home
  - surface: `Client Script`
  - artifacts: `TC-06 pointer still on dragged row is home`

- 🟢 TC-07: зазор между hit-rect → нет intent
  - surface: `Client Script`
  - artifacts: `TC-07 gap between mapped rows`

### Pointer / nest intent

- 🟢 TC-08: вниз свап только после `SWAP_EDGE_PX`
  - surface: `Client Script`
  - artifacts: `TC-08 swap down only after SWAP_EDGE_PX`

- 🟢 TC-09: вверх симметрично
  - surface: `Client Script`
  - artifacts: `TC-09 swap up is symmetric`

- 🟢 TC-10: сдвиг `< NEST_SHIFT_PX` не nest
  - surface: `Client Script`
  - artifacts: `TC-10 right shift below nest threshold`

- 🟢 TC-11: `a` after `b` + right → child of `b`; payload `b:a`
  - surface: `Client Script`
  - artifacts: `TC-11 drag a after b plus right nests`

- 🟢 TC-12: `c` на место `b` + right → child of `a`, не `b`
  - surface: `Client Script`
  - artifacts: `TC-12 c onto b plus right nests under a`

- 🟢 TC-13: home + right → child of строки сверху
  - surface: `Client Script`
  - artifacts: `TC-13 home plus right nests under the row above`

- 🟢 TC-14: верхняя строка + right → nest нет
  - surface: `Client Script`
  - artifacts: `TC-14 top row home plus right cannot nest`

- 🟢 TC-15: `allowTree=siblings` игнорирует right
  - surface: `Client Script`
  - artifacts: `TC-15 allowNest off ignores right shift`

- 🟢 TC-16: nest parent AFTER=hover, BEFORE=previous, home=previous of home
  - surface: `Client Script`
  - artifacts: `TC-16 nest parent for AFTER is hover`

### Tree modes

- 🟢 TC-17: siblings — перестановка детей одного родителя
  - surface: `Client Script`
  - artifacts: `TC-17 siblings mode reorders inside the same parent`

- 🟢 TC-18: siblings — чужой родитель запрещён
  - surface: `Client Script`
  - artifacts: `TC-18 siblings mode blocks cross-parent drop`

- 🟢 TC-19: siblings + right всё равно sibling after
  - surface: `Client Script`
  - artifacts: `TC-19 siblings mode blocks INSIDE`

- 🟢 TC-20: `allowTree=false` — nested drag null
  - surface: `Client Script`
  - artifacts: `TC-20 tree OFF blocks nested row drag`

- 🟢 TC-21: `allowTree=false` — top-level reorder ок
  - surface: `Client Script`
  - artifacts: `TC-21 tree OFF still allows top-level`

### Reparent / levels

- 🟢 TC-22: nest в родителя с детьми → append last
  - surface: `Client Script`
  - artifacts: `TC-22 nest into parent that already has a child`

- 🟢 TC-23: лист к другому родителю after sibling; `fromOrdered` пустой у бывшего
  - surface: `Client Script`
  - artifacts: `TC-23 reparent leaf across parents after sibling`

- 🟢 TC-24: outdent ребёнка на родителя → before parent
  - surface: `Client Script`
  - artifacts: `TC-24 outdent first child onto parent`

- 🟢 TC-25: outdent на следующий root → after этого root
  - surface: `Client Script`
  - artifacts: `TC-25 outdent last child onto next root`

- 🟢 TC-26: nest в себя запрещён
  - surface: `Client Script`
  - artifacts: `TC-26 cannot nest row into itself`

- 🟢 TC-27: nest/drop предка в потомка запрещён
  - surface: `Client Script`
  - artifacts: `TC-27 cannot nest ancestor into descendant`

- 🟢 TC-28: top-level в глубокий узел (`a:a1`)
  - surface: `Client Script`
  - artifacts: `TC-28 nest top-level into deep grandchild path`

- 🟢 TC-29: leaf L2 → after sibling другого L2
  - surface: `Client Script`
  - artifacts: `TC-29 move level-2 leaf after another level-2 sibling`

- 🟢 TC-30: leaf L2 на top after root
  - surface: `Client Script`
  - artifacts: `TC-30 lift level-2 leaf to top-level`

- 🟢 TC-31: home+right top-level под L2 над ним
  - surface: `Client Script`
  - artifacts: `TC-31 home plus right nests top-level under the level-2`

- 🟢 TC-32: reorder братьев на дне дерева
  - surface: `Client Script`
  - artifacts: `TC-32 reorder siblings at deepest level`

- 🟢 TC-33: nest под последний из трёх root
  - surface: `Client Script`
  - artifacts: `TC-33 nest under last of three roots`

### Expanded / collapsed branch

- 🟢 TC-34: раскрытая ветка after соседний root — дети на узле, preview блок
  - surface: `Client Script`
  - artifacts: `TC-34 drag expanded branch after next root`

- 🟢 TC-35: раскрытая ветка nest под root — remap `p:*` → `q:p:*`
  - surface: `Client Script`
  - artifacts: `TC-35 drag expanded branch under another root remaps`

- 🟢 TC-36: раскрытая ветка before другую ветку
  - surface: `Client Script`
  - artifacts: `TC-36 drag expanded branch before another`

- 🟢 TC-37: свёрнутый parent тащит скрытых детей в data
  - surface: `Client Script`
  - artifacts: `TC-37 collapsed parent still moves hidden children`

- 🟢 TC-38: лист из раскрытой ветки на top — siblings остаются
  - surface: `Client Script`
  - artifacts: `TC-38 drag leaf out of expanded branch`

- 🟢 TC-39: nest раскрытого parent в своего child запрещён
  - surface: `Client Script`
  - artifacts: `TC-39 cannot nest expanded parent into its visible child`

- 🟢 TC-40: draggedIds = корень; preview потомки по prefix
  - surface: `Client Script`
  - artifacts: `TC-40 collectDraggedRowIds is parent only`

- 🟢 TC-41: home-полоса ветки = parent … last visible child
  - surface: `Client Script`
  - artifacts: `TC-41 expanded home band`

- 🟢 TC-42: home+right раскрытой ветки → parent = видимая строка над ней (`p:pc2`)
  - surface: `Client Script`
  - artifacts: `TC-42 expanded branch home plus right nests under the visible row above`

- 🟢 TC-43: две раскрытые ветки — after сохраняет оба subtree
  - surface: `Client Script`
  - artifacts: `TC-43 drag one expanded branch after another`

- 🟢 TC-44: раскрытая mid-ветка nest под другой mid — дети и remap
  - surface: `Client Script`
  - artifacts: `TC-44 nest expanded mid-level branch`

- 🟢 TC-61: свёрнутый предыдущий root + right → nest под этот root
  - surface: `Client Script`
  - artifacts: `TC-61 collapsed previous root plus right`

### Merge

- 🟢 TC-45: merge head двигает блок
  - surface: `Client Script`
  - artifacts: `TC-45 merge head moves the whole block`

- 🟢 TC-46: merge tail drag blocked
  - surface: `Client Script`
  - artifacts: `TC-46 merge tail cannot start a drag`

- 🟢 TC-47: merge не nest
  - surface: `Client Script`
  - artifacts: `TC-47 merge block cannot nest`

- 🟢 TC-48: merge не reparent
  - surface: `Client Script`
  - artifacts: `TC-48 merge block cannot reparent`

### Payload / preview / undo

- 🟢 TC-49: `remapPathIdSet` переписывает subtree
  - surface: `Client Script`
  - artifacts: `TC-49 remapPathIdSet`

- 🟢 TC-50: `restoreCrossParentOrders` откатывает reparent
  - surface: `Client Script`
  - artifacts: `TC-50 restoreCrossParentOrders`

- 🟢 TC-51: nest payload: `section`, `position`, `parentRowId`, `rows[]`
  - surface: `Client Script`
  - artifacts: `TC-51 payload after nest`

- 🟢 TC-52: `isSelfOrDescendantId` только path prefix
  - surface: `Client Script`
  - artifacts: `TC-52 isSelfOrDescendantId`

- 🟢 TC-53: preview nest `indentDelta=20`
  - surface: `Client Script`
  - artifacts: `TC-53 preview nest bumps indent`

- 🟢 TC-54: home+nest всё равно строит preview (только indent)
  - surface: `Client Script`
  - artifacts: `TC-54 preview home plus nest still plans`

- 🟢 TC-55: preview раскрытой ветки едет одним блоком
  - surface: `Client Script`
  - artifacts: `TC-55 preview same-parent swap moves the dragged block`

- 🟢 TC-56: gantt sibling contract — same parent, `blockSize=1`, local id в order
  - surface: `Client Script`
  - artifacts: `TC-56 gantt persist contract sibling`

- 🟢 TC-57: gantt reparent contract — from/to orders, parent name = last segment
  - surface: `Client Script`
  - artifacts: `TC-57 gantt persist contract reparent`

- 🟢 TC-58: средний из трёх детей вниз
  - surface: `Client Script`
  - artifacts: `TC-58 reorder middle of three children`

- 🟢 TC-59: flatten collapsed vs expanded
  - surface: `Client Script`
  - artifacts: `TC-59 flattenVisible`

- 🟢 TC-60: clone fixture не мутирует исходник
  - surface: `Client Script`
  - artifacts: `TC-60 clone fixture is isolated`

### UI smoke (браузер, не dinext_common runner)

- ⚪ TC-UI-01: live gantt gutter — flat swap + persist `custom_tree_order`
  - surface: `UI smoke`
  - actor: `ui_actor` на `dev.dinext.localhost`
  - notes: нужен Task-проект в `dinext_project_tasks_gantt`; не в этом scenario_dir

- ⚪ TC-UI-02: live — раскрытая ветка, preview блок, mouseup один persist
  - surface: `UI smoke`
  - notes: тот же gantt site

- ⚪ TC-UI-03: live — nest + `parent_task` + `from_ordered_ids`
  - surface: `UI smoke`
  - notes: проверять через `/api` после drop, не через JS pipeline

## Last run

- date: `2026-08-30`
- site: `dev.dinext.localhost` (Node, без bench run-tests)
- command: `node --test dinext_common/public/js/table/@tests/row-reorder-scenarios.test.mjs`
- result: **61/61 OK**
- secondary: `node --test dinext_common/public/js/table/@tests/row-reorder.test.mjs` — **27/27 OK**
- notes: primary = pipeline mixin без DOM. Браузерные TC-UI-* не запускались.
