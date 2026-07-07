const NAVIGATION_DEFAULTS = {
    skipNonEditable: true,
    enterMovesDown: true,
    tabWraps: false,
    isRowNavigable: () => true,
    isCellNavigable: () => true
};

export const NavigationMixin = (Base) => class extends Base {
    /** `options.edit` opts navigation in by default; explicit `navigation.enabled` always wins. */
    isNavigationEnabled() {
        const enabled = this.options.navigation?.enabled;
        return enabled !== undefined ? !!enabled : !!this.options.edit;
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
        if (!row) {
            return false;
        }
        if (!nav.isRowNavigable(row)) {
            return false;
        }
        if (!nav.isCellNavigable(row, column.getColDef().field)) {
            return false;
        }
        if (nav.skipNonEditable && !this.isColumnEditableForRow(column, rowNode)) {
            return false;
        }
        return true;
    }

    /** Scans displayed rows/cols for the next cell matching navigability + editable rules. `null` at grid boundary (no wrap). */
    resolveNextCell({ rowNode, column, direction }) {
        if (!this.api || !rowNode || !column) {
            return null;
        }

        const columns = this.api.getAllDisplayedColumns();
        const colCount = columns.length;
        const rowCount = this.api.getDisplayedRowCount();
        let colIndex = columns.indexOf(column);
        let rowIndex = rowNode.rowIndex;
        if (colIndex === -1 || rowIndex == null || !colCount || !rowCount) {
            return null;
        }

        const horizontal = direction === "next" || direction === "prev";
        const step = (direction === "next" || direction === "down") ? 1 : -1;
        const wrap = horizontal && this.getNavigationOptions().tabWraps;
        const maxSteps = rowCount * colCount;

        for (let i = 0; i < maxSteps; i++) {
            if (horizontal) {
                colIndex += step;
                if (colIndex >= colCount) {
                    colIndex = 0;
                    rowIndex += 1;
                } else if (colIndex < 0) {
                    colIndex = colCount - 1;
                    rowIndex -= 1;
                }
            } else {
                rowIndex += step;
            }

            if (rowIndex < 0 || rowIndex >= rowCount) {
                if (!wrap) {
                    return null;
                }
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
        if (!next || !this.api) {
            return;
        }
        this.api.setFocusedCell(next.rowNode.rowIndex, next.column.getColId());
        if (startEditing && this.isColumnEditableForRow(next.column, next.rowNode)) {
            this.api.startEditingCell({ rowIndex: next.rowNode.rowIndex, colKey: next.column.getColId() });
        }
    }

    /** Tab / Enter after edit — honour skipNonEditable; arrow keys use AG Grid default (focus any cell). */
    resolveTabToNextCell(params) {
        if (params.editing) {
            return true;
        }

        const rowNode = this.api.getDisplayedRowAtIndex(params.previousCellPosition.rowIndex);
        if (!rowNode) {
            return params.nextCellPosition ?? false;
        }

        const next = this.resolveNextCell({
            rowNode,
            column: params.previousCellPosition.column,
            direction: params.backwards ? "prev" : "next"
        });

        if (!next) {
            return false;
        }
        return { rowIndex: next.rowNode.rowIndex, column: next.column, rowPinned: null };
    }

    /** Records Tab/Enter pressed while a cell is editing; consumed once by handleCellEditingStopped. Printable keys are never touched here. */
    handleNavigationCellKeyDown(event) {
        const key = event.event?.key;
        if (key !== "Tab" && key !== "Enter") {
            return;
        }
        if (!this.api?.getEditingCells()?.length) {
            return;
        }
        this._pendingNavKey = { key, shiftKey: !!event.event.shiftKey };
    }

    /** Wraps EditMixin's seam: Tab moves to the next navigable cell (and continues editing there); Enter moves down a row when `enterMovesDown`. */
    handleCellEditingStopped(event) {
        super.handleCellEditingStopped(event);

        const pending = this._pendingNavKey;
        this._pendingNavKey = null;
        if (!pending || !this.isNavigationEnabled()) {
            return;
        }

        const rowNode = event.node;
        const column = event.column;
        if (!rowNode || !column) {
            return;
        }

        if (pending.key === "Tab") {
            const next = this.resolveNextCell({ rowNode, column, direction: pending.shiftKey ? "prev" : "next" });
            setTimeout(() => this.moveFocusToResolvedCell(next, { startEditing: true }), 0);
            return;
        }

        if (pending.key === "Enter" && this.getNavigationOptions().enterMovesDown) {
            const next = this.resolveNextCell({ rowNode, column, direction: "down" });
            setTimeout(() => this.moveFocusToResolvedCell(next, { startEditing: false }), 0);
        }
    }

    buildNavigationGridOptions() {
        if (!this.isNavigationEnabled()) {
            return {};
        }

        return {
            tabToNextCell: params => this.resolveTabToNextCell(params),
            onCellKeyDown: event => this.handleNavigationCellKeyDown(event)
        };
    }
};
