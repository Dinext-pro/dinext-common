/**
 * Auto height: shrink viewport to content so pinned summary hugs last body row.
 * Cap at layout.maxHeight — then body scrolls, summary stays pinned bottom.
 *
 * Default `host` — consumer owns container height (PWR / gantt / FS).
 * Opt-in `auto`. Does not unpin summary rows (unlike pinEnd on columns).
 */

import { DEFAULT_ROW_HEIGHT } from "./grid.js";

const LAYOUT_FIT_SLACK_PX = 2;
const AUTO_CLASS = "dinext-table--layout-auto";

export function resolveLayoutHeightMode(options) {
    return options?.layout?.height === "auto" ? "auto" : "host";
}

export function parseLayoutSizePx(value) {
    if (value == null || value === "") {
        return null;
    }
    if (typeof value === "number") {
        return Number.isFinite(value) ? value : null;
    }
    const raw = String(value).trim();
    if (!raw) {
        return null;
    }
    const px = raw.match(/^(-?\d+(?:\.\d+)?)px$/i);
    if (px) {
        return Number(px[1]);
    }
    return raw;
}

export function cssSizeToPx(value, probeParent) {
    const parsed = parseLayoutSizePx(value);
    if (parsed == null) {
        return null;
    }
    if (typeof parsed === "number") {
        return parsed;
    }
    const parent = probeParent
        || (typeof document !== "undefined" ? document.body : null);
    if (!parent || typeof document === "undefined") {
        return null;
    }
    const probe = document.createElement("div");
    probe.style.cssText = [
        "position:absolute",
        "visibility:hidden",
        "pointer-events:none",
        "width:0",
        `height:${parsed}`
    ].join(";");
    parent.appendChild(probe);
    const px = probe.offsetHeight;
    probe.remove();
    return Number.isFinite(px) && px > 0 ? px : null;
}

export function sumLayoutChromePx({
    toolbarPx = 0,
    headerPx = 0,
    topHScrollPx = 0,
    bodyPx = 0,
    summaryPx = 0,
    bottomHScrollPx = 0,
    statusPx = 0,
    borderPx = 0,
    slackPx = LAYOUT_FIT_SLACK_PX
} = {}) {
    return toolbarPx
        + headerPx
        + topHScrollPx
        + bodyPx
        + summaryPx
        + bottomHScrollPx
        + statusPx
        + borderPx
        + slackPx;
}

export function resolveDesiredLayoutHeight({ contentPx, minPx, maxPx }) {
    let height = Math.max(0, Number(contentPx) || 0);
    if (maxPx != null && Number.isFinite(maxPx)) {
        height = Math.min(height, maxPx);
    }
    if (minPx != null && Number.isFinite(minPx) && minPx > 0) {
        height = Math.max(height, minPx);
    }
    return Math.round(height);
}

function offsetHeightOf(el) {
    if (!el) {
        return 0;
    }
    return el.offsetHeight || 0;
}

export const LayoutMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._layoutSyncing = false;
        this._layoutSyncRaf = null;
        this._layoutResizeObserver = null;
        this._onLayoutWindowResize = null;
    }

    afterGridCreated() {
        super.afterGridCreated();
        this.syncLayoutAutoClass();
        if (!this.isLayoutAuto()) {
            return;
        }
        this.bindLayoutHeightListeners();
        this.syncLayoutHeight();
        requestAnimationFrame(() => this.syncLayoutHeight());
    }

    destroyFeatures() {
        this.unbindLayoutHeightListeners();
        this.clearLayoutInlineStyles();
        this.container?.classList.remove(AUTO_CLASS);
        super.destroyFeatures();
    }

    isLayoutAuto() {
        return resolveLayoutHeightMode(this.options) === "auto";
    }

    getLayoutOptions() {
        return this.options?.layout || {};
    }

    syncLayoutAutoClass() {
        this.container?.classList.toggle(AUTO_CLASS, this.isLayoutAuto());
    }

    buildLayoutGridOptions() {
        const sync = () => this.scheduleLayoutHeightSync();
        return {
            onGridSizeChanged: sync,
            onColumnResized: sync,
            onDisplayedColumnsChanged: sync,
            onFirstDataRendered: sync,
            onModelUpdated: sync
        };
    }

    syncVisibleRows() {
        super.syncVisibleRows();
        this.scheduleLayoutHeightSync();
    }

    setSummaryRows(rows) {
        super.setSummaryRows(rows);
        this.scheduleLayoutHeightSync();
    }

    syncFullscreenState() {
        const result = super.syncFullscreenState?.();
        this.syncLayoutHeight();
        return result;
    }

    toggleFilterRow(force) {
        const open = super.toggleFilterRow?.(force);
        this.scheduleLayoutHeightSync();
        return open;
    }

    handleSetOption(key, value) {
        if (key === "layout") {
            this.options.layout = value;
            this.syncLayoutAutoClass();
            if (this.isLayoutAuto()) {
                this.bindLayoutHeightListeners();
                this.syncLayoutHeight();
            } else {
                this.unbindLayoutHeightListeners();
                this.clearLayoutInlineStyles();
            }
            return true;
        }
        return super.handleSetOption?.(key, value) ?? false;
    }

    bindLayoutHeightListeners() {
        if (this._onLayoutWindowResize || typeof window === "undefined") {
            return;
        }
        this._onLayoutWindowResize = () => this.scheduleLayoutHeightSync();
        window.addEventListener("resize", this._onLayoutWindowResize);
        if (typeof ResizeObserver !== "function" || !this.container) {
            return;
        }
        this._layoutResizeObserver = new ResizeObserver(() => {
            if (this._layoutSyncing) {
                return;
            }
            this.scheduleLayoutHeightSync();
        });
        for (const sel of [
            ".dinext-table-toolbar",
            ".dinext-table-status-bar",
            ".ag-header"
        ]) {
            const el = this.container.querySelector(sel);
            if (el) {
                this._layoutResizeObserver.observe(el);
            }
        }
    }

    unbindLayoutHeightListeners() {
        if (this._layoutSyncRaf != null && typeof cancelAnimationFrame === "function") {
            cancelAnimationFrame(this._layoutSyncRaf);
        }
        this._layoutSyncRaf = null;
        if (this._onLayoutWindowResize && typeof window !== "undefined") {
            window.removeEventListener("resize", this._onLayoutWindowResize);
        }
        this._onLayoutWindowResize = null;
        this._layoutResizeObserver?.disconnect();
        this._layoutResizeObserver = null;
    }

    scheduleLayoutHeightSync() {
        if (!this.isLayoutAuto() || this._layoutSyncing) {
            return;
        }
        if (typeof requestAnimationFrame !== "function") {
            this.syncLayoutHeight();
            return;
        }
        if (this._layoutSyncRaf != null) {
            return;
        }
        this._layoutSyncRaf = requestAnimationFrame(() => {
            this._layoutSyncRaf = null;
            this.syncLayoutHeight();
        });
    }

    shouldSkipLayoutHeight() {
        if (!this.isLayoutAuto() || !this.container) {
            return true;
        }
        if (typeof this.isFullscreen === "function" && this.isFullscreen()) {
            return true;
        }
        return false;
    }

    clearLayoutInlineStyles() {
        if (!this.container) {
            return;
        }
        this.container.style.height = "";
        this.container.style.maxHeight = "";
        this.container.style.minHeight = "";
    }

    getLayoutRowHeight() {
        const theme = this.api?.getSizesForCurrentTheme?.();
        if (theme?.rowHeight > 0) {
            return theme.rowHeight;
        }
        const opt = this.options?.gridOptions?.rowHeight;
        if (opt > 0) {
            return opt;
        }
        return DEFAULT_ROW_HEIGHT;
    }

    getLayoutBodyPx() {
        const body = this.container?.querySelector?.(".ag-center-cols-container");
        if (body && body.offsetHeight > 0) {
            return body.offsetHeight;
        }
        const count = typeof this.api?.getDisplayedRowCount === "function"
            ? this.api.getDisplayedRowCount()
            : (this.rowData?.length || 0);
        return Math.max(0, count) * this.getLayoutRowHeight();
    }

    getLayoutSummaryPx() {
        const floating = this.container?.querySelector?.(".ag-floating-bottom");
        if (floating && floating.offsetHeight > 0) {
            return floating.offsetHeight;
        }
        const count = this.summaryRowData?.length || 0;
        return count * this.getLayoutRowHeight();
    }

    measureLayoutContentPx() {
        const wrapper = this.container?.querySelector?.(".ag-root-wrapper");
        const borderPx = wrapper
            ? Math.max(0, wrapper.offsetHeight - wrapper.clientHeight)
            : 0;
        return sumLayoutChromePx({
            toolbarPx: offsetHeightOf(this.container?.querySelector?.(".dinext-table-toolbar")),
            headerPx: offsetHeightOf(this.container?.querySelector?.(".ag-header")),
            topHScrollPx: offsetHeightOf(this.container?.querySelector?.(".dinext-table-hscroll-top")),
            bodyPx: this.getLayoutBodyPx(),
            summaryPx: this.getLayoutSummaryPx(),
            bottomHScrollPx: offsetHeightOf(
                this.container?.querySelector?.(".ag-body-horizontal-scroll")
            ),
            statusPx: offsetHeightOf(this.container?.querySelector?.(".dinext-table-status-bar")),
            borderPx
        });
    }

    resolveLayoutBoundPx(value) {
        return cssSizeToPx(value, this.container?.parentElement || this.container);
    }

    syncLayoutHeight({ followUp = false } = {}) {
        if (this._layoutSyncing) {
            return;
        }
        if (this.shouldSkipLayoutHeight()) {
            if (this.isLayoutAuto() && this.container) {
                this.clearLayoutInlineStyles();
            }
            return;
        }

        const opts = this.getLayoutOptions();
        const maxCss = opts.maxHeight;
        const minCss = opts.minHeight;
        if (maxCss != null && maxCss !== "") {
            this.container.style.maxHeight = typeof maxCss === "number"
                ? `${maxCss}px`
                : String(maxCss);
        } else {
            this.container.style.maxHeight = "";
        }
        if (minCss != null && minCss !== "") {
            this.container.style.minHeight = typeof minCss === "number"
                ? `${minCss}px`
                : String(minCss);
        } else {
            this.container.style.minHeight = "0px";
        }

        const desired = resolveDesiredLayoutHeight({
            contentPx: this.measureLayoutContentPx(),
            minPx: this.resolveLayoutBoundPx(minCss),
            maxPx: this.resolveLayoutBoundPx(maxCss)
        });
        const currentInline = this.container.style.height;
        const nextInline = `${desired}px`;
        if (currentInline === nextInline) {
            return;
        }

        this._layoutSyncing = true;
        try {
            this.container.style.height = nextInline;
        } finally {
            this._layoutSyncing = false;
        }

        if (!followUp) {
            requestAnimationFrame(() => this.syncLayoutHeight({ followUp: true }));
        }
    }
};
