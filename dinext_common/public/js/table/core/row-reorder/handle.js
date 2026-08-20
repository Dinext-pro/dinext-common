/** Visible 6-dot (3×2) drag affordance for row reorder. */

export function createRowReorderHandleEl() {
    const el = document.createElement("span");
    el.className = "dinext-table-row-reorder-handle";
    el.setAttribute("draggable", "false");
    el.setAttribute("role", "button");
    const label = typeof __ === "function" ? __("Move") : "Move";
    el.setAttribute("title", label);
    el.setAttribute("aria-label", label);
    return el;
}

/** Class renderer for the reserved `__dinext_row_reorder` system column. */
export class RowReorderHandleCellRenderer {
    init(params) {
        this.eGui = document.createElement("div");
        this.eGui.className = "dinext-table-row-reorder-handle-host";
        this.eGui.appendChild(createRowReorderHandleEl());
        this.params = params;
    }

    getGui() {
        return this.eGui;
    }

    refresh() {
        return true;
    }
}
