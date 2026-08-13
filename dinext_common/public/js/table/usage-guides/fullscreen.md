# Fullscreen — гайд

Native Fullscreen API на `container` или внешний `shell`. Хуки для domain-layout (скрыть charts и т.п.).

**См. также:** [`../README.md`](../README.md).

---

## Options

```js
DinextTable.create({
    container: tableEl,
    fullscreen: {
        enabled: true,
        target: "shell",          // default: "container"
        shell: rootEl,            // filters + table (+ optional chrome)
        onEnter: ({ table, element }) => {
            rootEl.classList.add("is-fullscreen");
        },
        onExit: ({ table, element }) => {
            rootEl.classList.remove("is-fullscreen");
        }
    },
    // aliases (optional; fire after nested):
    // onFullscreenEnter: (ctx) => {},
    // onFullscreenExit: (ctx) => {},
});
```

Хуки зовутся при **реальном** переходе (toolbar, Esc, browser UI) — один раз на enter/exit.

Native Fullscreen рисует только дерево `fullscreenElement`. Оверлеи на `body` (Frappe datepicker, AG popup) ядро переносит в host: `popupParent` + `DinextTable.adoptOverlay` / `getOverlayHost()`.

---

## Shell + CSS (предпочтительно)

Не вырезать DOM. FS на общий root; лишнее скрыть:

```css
.workload-reports-root:fullscreen .workload-reports-charts,
.workload-reports-root.is-fullscreen .workload-reports-charts {
    display: none;
}
```

| В FS | Как |
|------|-----|
| Только table | `target: "container"` (default) |
| Filters + table | `shell: root`, charts с CSS exclude |
| Filters + charts + table | `shell: root`, без exclude |

---

## API

```js
table.isFullscreen();
table.enterFullscreen();
table.exitFullscreen();
table.toggleFullscreen();
```
