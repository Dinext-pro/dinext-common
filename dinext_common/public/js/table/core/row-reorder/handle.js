/** Visible 6-dot (3×2) drag affordance for row reorder. */

function moveHandleLabel() {
    return typeof __ === "function" ? __("Move") : "Move";
}

export function applyRowReorderHandleState(el, table) {
    if (!el) {
        return;
    }
    const locked = !!table?.isRowReorderSortLocked?.();
    const label = locked
        ? (table.getRowReorderSortLockTooltip?.() || moveHandleLabel())
        : moveHandleLabel();
    el.setAttribute("title", label);
    el.setAttribute("aria-label", label);
    el.classList.toggle("dinext-table-row-reorder-handle--locked", locked);
    const host = el.parentElement;
    if (host?.classList.contains("dinext-table-row-reorder-handle-host")) {
        host.setAttribute("title", label);
    }
}

export function createRowReorderHandleEl(table) {
    const el = document.createElement("span");
    el.className = "dinext-table-row-reorder-handle";
    el.setAttribute("draggable", "false");
    el.setAttribute("role", "button");
    applyRowReorderHandleState(el, table);
    return el;
}

/** Class renderer for the reserved `__dinext_row_reorder` system column. */
export class RowReorderHandleCellRenderer {
    init(params) {
        this.eGui = document.createElement("div");
        this.eGui.className = "dinext-table-row-reorder-handle-host";
        this.handleEl = createRowReorderHandleEl(params?.context?.dinextTable);
        this.eGui.appendChild(this.handleEl);
        this.params = params;
    }

    getGui() {
        return this.eGui;
    }

    refresh(params) {
        this.params = params;
        applyRowReorderHandleState(this.handleEl, params?.context?.dinextTable);
        return true;
    }
}
