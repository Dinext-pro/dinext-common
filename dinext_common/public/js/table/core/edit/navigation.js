const NAVIGATION_DEFAULTS = {
    skipNonEditable: true,
    enterMovesDown: true,
    tabWraps: false,
    isRowNavigable: () => true,
    isCellNavigable: () => true
};

/** True when any leaf column opts into edit (global `edit: false` + per-column edit). */
function columnsAllowEdit(columns) {
    for (const col of columns || []) {
        if (Array.isArray(col.children) && col.children.length) {
            if (columnsAllowEdit(col.children)) return true;
            continue;
        }
        if (col.edit !== undefined && col.edit !== false) return true;
    }
    return false;
}

export const NavigationMixin = (Base) => class extends Base {
    /**
     * Explicit `navigation.enabled` wins.
     * Default on when global `edit` or any column has `edit` (not `false`).
     */
    isNavigationEnabled() {
        const enabled = this.options.navigation?.enabled;
        if (enabled !== undefined) {
            return !!enabled;
        }
        if (this.options.edit) {
            return true;
        }
        return columnsAllowEdit(this.columns);
    }

    getNavigationOptions() {
        return { ...NAVIGATION_DEFAULTS, ...(this.options.navigation || {}) };
    }

    isColumnEditableForRow(column, rowNode) {
        const colDef = column.getColDef();
        const editable = colDef.editable;
        if (typeof editable === "function") {
            return !!editable({
                api: this.api,
                node: rowNode,
                data: rowNode.data,
                colDef,
                column
            });
        }
        return !!editable;
    }

    isCellEligibleForNavigation(rowNode, column) {
        const nav = this.getNavigationOptions();
        const row = rowNode.data;
        if (!row 
            || !nav.isRowNavigable(row)
            || !nav.isCellNavigable(row, column.getColDef().field)
            || (nav.skipNonEditable && !this.isColumnEditableForRow(column, rowNode))
        ) return false;
        return true;
    }

    /** Next Tab target honouring skipNonEditable. `null` at grid boundary (no wrap unless tabWraps). */
    resolveNextCell({ rowNode, column, direction }) {
        if (!this.api || !rowNode || !column) return null;

        const columns = this.api.getAllDisplayedColumns();
        const colCount = columns.length;
        const rowCount = this.api.getDisplayedRowCount();
        let colIndex = columns.indexOf(column);
        let rowIndex = rowNode.rowIndex;
        if (colIndex === -1 || rowIndex == null || !colCount || !rowCount) {
            return null;
        }

        const backwards = direction === "prev";
        const step = backwards ? -1 : 1;
        const wrap = this.getNavigationOptions().tabWraps;
        const maxSteps = rowCount * colCount;

        for (let i = 0; i < maxSteps; i++) {
            colIndex += step;
            if (colIndex >= colCount) {
                colIndex = 0;
                rowIndex += 1;
            } else if (colIndex < 0) {
                colIndex = colCount - 1;
                rowIndex -= 1;
            }

            if (rowIndex < 0 || rowIndex >= rowCount) {
                if (!wrap) return null;
                rowIndex = ((rowIndex % rowCount) + rowCount) % rowCount;
            }

            const candidateRow = this.api.getDisplayedRowAtIndex(rowIndex);
            const candidateColumn = columns[colIndex];
            if (candidateRow && candidateColumn && this.isCellEligibleForNavigation(candidateRow, candidateColumn)) {
                return { rowNode: candidateRow, column: candidateColumn };
            }
        }

        return null;
    }

    moveFocusToResolvedCell(next, { startEditing } = {}) {
        if (!next || !this.api) return;
        this.api.setFocusedCell(next.rowNode.rowIndex, next.column.getColId());
        if (startEditing && this.isColumnEditableForRow(next.column, next.rowNode)) {
            this.api.startEditingCell({ rowIndex: next.rowNode.rowIndex, colKey: next.column.getColId() });
        }
    }

    /** Outside edit: Tab jumps to next navigable cell. While editing, let AG Grid stop edit first. */
    resolveTabToNextCell(params) {
        if (params.editing) return true;

        const rowNode = this.api.getDisplayedRowAtIndex(params.previousCellPosition.rowIndex);
        if (!rowNode) {
            return params.nextCellPosition ?? false;
        }

        const next = this.resolveNextCell({
            rowNode,
            column: params.previousCellPosition.column,
            direction: params.backwards ? "prev" : "next"
        });

        if (!next) return false;
        return { rowIndex: next.rowNode.rowIndex, column: next.column, rowPinned: null };
    }

    /**
     * Capture-phase Tab while editing: record intent before the editor stops edit.
     * Bubble `onCellKeyDown` is often too late (editing already stopped).
     * Enter is handled by AG Grid `enterNavigatesVerticallyAfterEdit` — not here.
     */
    bindTabKeyCapture() {
        this.unbindTabKeyCapture();
        if (!this.isNavigationEnabled() || !this.container) return;
        this._tabKeydownCapture = (domEvent) => {
            if (domEvent.key !== "Tab") return;
            if (!this.api?.getEditingCells()?.length) return;
            this._pendingTabNav = { shiftKey: !!domEvent.shiftKey };
        };
        this.container.addEventListener("keydown", this._tabKeydownCapture, true);
    }

    unbindTabKeyCapture() {
        if (this._tabKeydownCapture && this.container) {
            this.container.removeEventListener("keydown", this._tabKeydownCapture, true);
        }
        this._tabKeydownCapture = null;
    }

    afterGridCreated() {
        super.afterGridCreated();
        this.bindTabKeyCapture();
    }

    destroyFeatures() {
        this.unbindTabKeyCapture();
        this._pendingTabNav = null;
        super.destroyFeatures();
    }

    /** After edit stop: Tab → next navigable cell and keep editing. */
    handleCellEditingStopped(event) {
        super.handleCellEditingStopped(event);

        const pending = this._pendingTabNav;
        this._pendingTabNav = null;
        if (!pending || !this.isNavigationEnabled()) return;

        const rowNode = event.node;
        const column = event.column;
        if (!rowNode || !column) return;

        const next = this.resolveNextCell({
            rowNode,
            column,
            direction: pending.shiftKey ? "prev" : "next"
        });
        setTimeout(() => this.moveFocusToResolvedCell(next, { startEditing: true }), 0);
    }

    buildNavigationGridOptions() {
        if (!this.isNavigationEnabled()) return {};

        const enterMovesDown = this.getNavigationOptions().enterMovesDown;
        return {
            // Official Excel-style Enter / Shift+Enter (Community).
            enterNavigatesVertically: enterMovesDown,
            enterNavigatesVerticallyAfterEdit: enterMovesDown,
            tabToNextCell: params => this.resolveTabToNextCell(params)
        };
    }
};
