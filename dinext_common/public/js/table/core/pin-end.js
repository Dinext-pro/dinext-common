/**
 * Right-pin policy for declared `pinned: "right"` columns.
 *
 * `columns[].pinned` stays intent. Runtime pin is owned here — do not mutate
 * `options.columns[].pinned`. Default mode `auto` — pin only on overflow.
 * Opt-in `always` = AG Grid stick-to-viewport.
 */

const PIN_END_OVERFLOW_PX = 1;
const ROW_CHECK_DEFAULT_WIDTH = 36;
const ROW_REORDER_DEFAULT_WIDTH = 18;

export function resolvePinEndMode(options) {
    return options?.pinEnd?.mode === "always" ? "always" : "auto";
}

function isLeafColumn(col) {
    return !Array.isArray(col?.children) || col.children.length === 0;
}

function columnId(col) {
    if (!col) {
        return null;
    }
    if (col.colId != null && col.colId !== "") {
        return String(col.colId);
    }
    if (col.field != null && col.field !== "") {
        return String(col.field);
    }
    return null;
}

function declaredWidth(col) {
    return Number(col?.width ?? col?.minWidth ?? 0) || 0;
}

function walkDeclaredLeaves(columns, ancestorPinned, visit) {
    if (!Array.isArray(columns)) {
        return;
    }
    for (const col of columns) {
        const pinnedHere = ancestorPinned || col?.pinned === "right";
        if (!isLeafColumn(col)) {
            walkDeclaredLeaves(col.children, pinnedHere, visit);
            continue;
        }
        visit(col, pinnedHere || col?.pinned === "right");
    }
}

/** Leaf ids under any declared `pinned: "right"` group or leaf. Hidden included. */
export function collectDeclaredPinRightLeafs(columns) {
    const ids = [];
    walkDeclaredLeaves(columns, false, (col, pinRight) => {
        if (!pinRight) {
            return;
        }
        const id = columnId(col);
        if (id) {
            ids.push(id);
        }
    });
    return ids;
}

/** Visible leaf widths from declared `width` / `minWidth`. Hidden skipped. */
export function sumDeclaredVisibleLeafWidths(columns) {
    let total = 0;
    walkDeclaredLeaves(columns, false, (col) => {
        if (col?.hide) {
            return;
        }
        total += declaredWidth(col);
    });
    return total;
}

export function sumInjectedColumnWidths(options = {}) {
    let extra = 0;
    if (options.rowCheck?.enabled) {
        extra += Number(options.rowCheck.width) || ROW_CHECK_DEFAULT_WIDTH;
    }
    if (options.rowReorder?.enabled) {
        extra += Number(options.rowReorder.width) || ROW_REORDER_DEFAULT_WIDTH;
    }
    return extra;
}

export function resolveDesiredPinEnd({
    totalWidth,
    availableWidth,
    overflowPx = PIN_END_OVERFLOW_PX
}) {
    if (!availableWidth) {
        return "right";
    }
    return totalWidth > availableWidth + overflowPx ? "right" : null;
}

export const PinEndMixin = (Base) => class extends Base {
    afterGridCreated() {
        super.afterGridCreated();
        this.syncPinEnd();
        requestAnimationFrame(() => this.syncPinEnd());
    }

    applyColumns(columns) {
        super.applyColumns(columns);
        this.syncPinEnd();
    }

    buildPinEndGridOptions() {
        const sync = () => this.syncPinEnd();
        return {
            onGridSizeChanged: sync,
            onColumnResized: sync,
            onDisplayedColumnsChanged: sync,
            onFirstDataRendered: sync
        };
    }

    isPinEndAuto() {
        return resolvePinEndMode(this.options) === "auto";
    }

    getPinEndAvailableWidth() {
        const body = this.container?.querySelector?.(".ag-body")
            || this.container?.querySelector?.(".ag-root-wrapper-body")
            || this.container;
        return body?.clientWidth || 0;
    }

    getPinEndContentWidth() {
        const cols = this.api?.getAllDisplayedColumns?.();
        if (Array.isArray(cols) && cols.length) {
            const actual = cols.reduce((sum, col) => {
                return sum + (Number(col.getActualWidth?.()) || 0);
            }, 0);
            if (actual > 0) {
                return actual;
            }
        }
        return sumDeclaredVisibleLeafWidths(this.columns)
            + sumInjectedColumnWidths(this.options);
    }

    getRuntimePinEnd(ids) {
        const id = ids[0];
        const col = typeof this.api?.getColumn === "function"
            ? this.api.getColumn(id)
            : null;
        if (col && typeof col.isPinnedRight === "function") {
            return col.isPinnedRight() ? "right" : null;
        }
        const all = this.api?.getAllGridColumns?.() || [];
        const found = all.find((item) => item.getColId?.() === id);
        if (found && typeof found.isPinnedRight === "function") {
            return found.isPinnedRight() ? "right" : null;
        }
        return "right";
    }

    syncPinEnd() {
        if (this._pinEndSyncing || !this.api || !this.isPinEndAuto()) {
            return;
        }
        const ids = collectDeclaredPinRightLeafs(this.columns);
        if (!ids.length) {
            return;
        }

        const available = this.getPinEndAvailableWidth();
        const total = this.getPinEndContentWidth();
        const desired = resolveDesiredPinEnd({
            totalWidth: total,
            availableWidth: available
        });
        if (this.getRuntimePinEnd(ids) === desired) {
            return;
        }
        if (typeof this.api.setColumnsPinned !== "function") {
            return;
        }

        this._pinEndSyncing = true;
        try {
            this.api.setColumnsPinned(ids, desired);
        } finally {
            this._pinEndSyncing = false;
        }
    }
};
