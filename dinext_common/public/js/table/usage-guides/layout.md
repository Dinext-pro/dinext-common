# Layout — auto height

Как убрать дыру между последней строкой тела и `summaryRows`, не снимая pin.

Общий API: [`../README.md`](../README.md). Summary: [`sections-and-summary.md`](sections-and-summary.md).

---

## Зачем

AG Grid `pinnedBottom` клеится к низу **вьюпорта**. Хост с фикс. высотой (`min(60vh, 672px)`) + мало строк → пустой зазор. `pinEnd` для колонок снимает pin; для summary так нельзя (другой store, guards, tree).

Решение ядра: **сжать контейнер** до chrome + body + summary, потолок — `maxHeight`. Pin остаётся. Много строк → скролл тела, итоги снизу.

`domLayout: "autoHeight"` не использовать: нет внутреннего вертикального скролла, footer уедет.

---

## Options

| Key | Default | Описание |
|-----|---------|----------|
| `layout.height` | `"host"` | `"auto"` — ядро ставит `height` в px. `"host"` — как раньше (CSS / inline) |
| `layout.maxHeight` | — | px или CSS: `672`, `"60vh"`, `"min(60vh, 672px)"` |
| `layout.minHeight` | — | пол. `280` снова даст дыру на короткой таблице |

Fullscreen: тот же hug. Потолок — доступная высота экрана/shell, не `maxHeight`. Высота на `.dinext-table-grid-host`; контейнер остаётся `100%` (фон, оверлеи). Много строк → скролл тела, итоги снизу.

Не включать `auto` там, где хост сам кормит высоту (PWR fill-viewport, gantt).

---

## Пример

```js
DinextTable.create({
    container,
    data,
    summaryRows,
    layout: {
        height: "auto",
        maxHeight: "min(60vh, 672px)"
    },
    columns
});
```

Домен не ставит фикс. `height` / `min-height: 280px` на контейнер — иначе CSS перебьёт hug.
