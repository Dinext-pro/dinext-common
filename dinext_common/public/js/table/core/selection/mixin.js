import { matchKeyboardShortcut, queryAgCellElement } from "../shared/utils.js";

const SELECTION_DEFAULTS = {
    enabled: false,
    suppressMultiRanges: false
};

const RANGE_HIGHLIGHT_CLASSES = [
    "dinext-table-cell-in-range",
    "dinext-table-cell-range-top",
    "dinext-table-cell-range-bottom",
    "dinext-table-cell-range-left",
    "dinext-table-cell-range-right"
];

const ARROW_DIRECTIONS = {
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right"
};

/**
 * Custom range selection for AG Grid Community (no `rangeSelection` module).
 * Highlight is applied by toggling classes directly on rendered `.ag-cell` DOM
 * nodes (matched via AG Grid's own `row-index` / `col-id` attributes) instead
 * of `cellClass`/`cellClassRules`, so it never conflicts with column-level
 * cellClass and survives arbitrary column setups. Because AG Grid virtualizes
 * rows, cells recreated by scrolling lose those classes — `onBodyScroll`
 * re-applies them.
 */
export const SelectionMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this.initSelectionState();
    }

    destroyFeatures() {
        this.destroySelectionListeners();
        super.destroyFeatures();
    }

    initSelectionState() {
        this.cellRanges = [];
        this.focusedCell = null;
        this._selectionAnchor = null;
        this._isRangeDragging = false;
        this._isExtending = false;
        this._mouseFocusPending = false;

        if (this.isSelectionEnabled()) {
            this._onSelectionMouseUp = () => {
                setTimeout(() => { this._isRangeDragging = false; }, 0);
            };
            document.addEventListener("mouseup", this._onSelectionMouseUp);

            /**
             * AG Grid always fires `cellFocused` *before* `cellMouseDown` for the same click.
             * Without this flag, `handleSelectionCellFocused` would collapse `cellRanges` to the
             * newly-clicked cell before `handleSelectionCellMouseDown` gets a chance to read the
             * pre-click state (breaks Shift/Ctrl+Click and multi-range append). Capture phase on
             * the container runs before AG Grid's own (target-level) mousedown handling, so it's
             * set in time for the resulting `cellFocused` to see it.
             */
            this._onSelectionMouseDownCapture = () => {
                this._mouseFocusPending = true;
                setTimeout(() => {
                    this._mouseFocusPending = false;
                }, 0);
            };
            this.container.addEventListener("mousedown", this._onSelectionMouseDownCapture, true);
        }
    }

    destroySelectionListeners() {
        if (this._onSelectionMouseUp) {
            document.removeEventListener("mouseup", this._onSelectionMouseUp);
            this._onSelectionMouseUp = null;
        }
        if (this._onSelectionMouseDownCapture) {
            this.container.removeEventListener("mousedown", this._onSelectionMouseDownCapture, true);
            this._onSelectionMouseDownCapture = null;
        }
    }

    getSelectionOptions() {
        return { ...SELECTION_DEFAULTS, ...(this.options.selection || {}) };
    }

    isSelectionEnabled() {
        return !!this.getSelectionOptions().enabled;
    }

    makeCellRef(node, column) {
        return { rowId: this.getEditRowId(node.data), colId: column.getColId() };
    }

    makeRange(anchorRef, endRef) {
        return {
            startRowId: anchorRef.rowId,
            startColId: anchorRef.colId,
            endRowId: endRef.rowId,
            endColId: endRef.colId
        };
    }

    /** Replaces only the last range (keeps earlier ranges from a multi-range gesture). */
    extendActiveRange(anchorRef, endRef) {
        const range = this.makeRange(anchorRef, endRef);
        this.cellRanges = this.cellRanges.length
            ? [...this.cellRanges.slice(0, -1), range]
            : [range];
    }

    getRowIndexForId(rowId) {
        const node = this.api?.getRowNode(String(rowId));
        return node ? node.rowIndex : null;
    }

    getColumnIndexById(colId, columns) {
        return columns.findIndex(col => col.getColId() === colId);
    }

    /** Resolves a range's two named endpoints to a normalized index rectangle; `null` if a row/col is no longer displayed. */
    buildRangeBounds(range, columns) {
        const startRowIndex = this.getRowIndexForId(range.startRowId);
        const endRowIndex = this.getRowIndexForId(range.endRowId);
        const startColIndex = this.getColumnIndexById(range.startColId, columns);
        const endColIndex = this.getColumnIndexById(range.endColId, columns);

        if (startRowIndex == null || endRowIndex == null || startColIndex === -1 || endColIndex === -1) {
            return null;
        }

        return {
            minRowIndex: Math.min(startRowIndex, endRowIndex),
            maxRowIndex: Math.max(startRowIndex, endRowIndex),
            minColIndex: Math.min(startColIndex, endColIndex),
            maxColIndex: Math.max(startColIndex, endColIndex)
        };
    }

    /** Union bounding box across all ranges, clipped to the currently rendered row/col window. */
    getRangesViewportBox(columns, firstRow, lastRow) {
        let minRow = Infinity, maxRow = -Infinity, minCol = Infinity, maxCol = -Infinity;

        for (const range of this.cellRanges) {
            const bounds = this.buildRangeBounds(range, columns);
            if (!bounds) {
                continue;
            }
            minRow = Math.min(minRow, bounds.minRowIndex);
            maxRow = Math.max(maxRow, bounds.maxRowIndex);
            minCol = Math.min(minCol, bounds.minColIndex);
            maxCol = Math.max(maxCol, bounds.maxColIndex);
        }

        if (minRow === Infinity) {
            return null;
        }

        return {
            minRow: Math.max(minRow, firstRow),
            maxRow: Math.min(maxRow, lastRow),
            minCol: Math.max(minCol, 0),
            maxCol: Math.min(maxCol, columns.length - 1)
        };
    }

    /** Whether (rowIndex, colIndex) falls inside any range, plus which edges of that range it touches (for border classes). */
    getCellRangeState(rowIndex, colIndex) {
        const columns = this.api?.getAllDisplayedColumns() || [];
        let inRange = false;
        let top = false, bottom = false, left = false, right = false;

        for (const range of this.cellRanges) {
            const bounds = this.buildRangeBounds(range, columns);
            if (!bounds) {
                continue;
            }
            if (rowIndex < bounds.minRowIndex || rowIndex > bounds.maxRowIndex) {
                continue;
            }
            if (colIndex < bounds.minColIndex || colIndex > bounds.maxColIndex) {
                continue;
            }
            inRange = true;
            top = top || rowIndex === bounds.minRowIndex;
            bottom = bottom || rowIndex === bounds.maxRowIndex;
            left = left || colIndex === bounds.minColIndex;
            right = right || colIndex === bounds.maxColIndex;
        }

        return { inRange, top, bottom, left, right };
    }

    clearSelectionHighlightDom() {
        if (!this.container) {
            return;
        }
        const selector = RANGE_HIGHLIGHT_CLASSES.map(cls => `.${cls}`).join(",");
        this.container.querySelectorAll(selector).forEach(el => el.classList.remove(...RANGE_HIGHLIGHT_CLASSES));
    }

    refreshSelectionHighlight() {
        this.clearSelectionHighlightDom();
        if (!this.container || !this.api || !this.cellRanges.length) {
            return;
        }

        const columns = this.api.getAllDisplayedColumns();
        const firstRow = this.api.getFirstDisplayedRowIndex();
        const lastRow = this.api.getLastDisplayedRowIndex();
        if (firstRow == null || lastRow == null || firstRow < 0) {
            return;
        }

        const box = this.getRangesViewportBox(columns, firstRow, lastRow);
        if (!box) {
            return;
        }

        for (let rowIndex = box.minRow; rowIndex <= box.maxRow; rowIndex++) {
            for (let colIndex = box.minCol; colIndex <= box.maxCol; colIndex++) {
                const state = this.getCellRangeState(rowIndex, colIndex);
                if (!state.inRange) {
                    continue;
                }
                const colId = columns[colIndex].getColId();
                const cellEl = queryAgCellElement(this.container, rowIndex, colId);
                if (!cellEl) {
                    continue;
                }
                cellEl.classList.add("dinext-table-cell-in-range");
                if (state.top) cellEl.classList.add("dinext-table-cell-range-top");
                if (state.bottom) cellEl.classList.add("dinext-table-cell-range-bottom");
                if (state.left) cellEl.classList.add("dinext-table-cell-range-left");
                if (state.right) cellEl.classList.add("dinext-table-cell-range-right");
            }
        }
    }

    handleSelectionCellMouseDown(event) {
        if (this._isFillDragging) {
            return;
        }
        if (event.event?.button !== 0 || !event.node?.data || !event.column) {
            return;
        }
        if (!this.shouldApplySelectionToRow(event.node)) {
            return;
        }

        const cellRef = this.makeCellRef(event.node, event.column);
        const domEvent = event.event;
        const shift = !!domEvent.shiftKey;
        const multi = !!(domEvent.ctrlKey || domEvent.metaKey) && !this.getSelectionOptions().suppressMultiRanges;

        this._isExtending = false;

        if (shift) {
            const anchor = this._selectionAnchor || this.focusedCell || cellRef;
            this._selectionAnchor = anchor;
            this.extendActiveRange(anchor, cellRef);
        } else if (multi) {
            this._selectionAnchor = cellRef;
            this.cellRanges = [...this.cellRanges, this.makeRange(cellRef, cellRef)];
        } else {
            this._selectionAnchor = cellRef;
            this.cellRanges = [this.makeRange(cellRef, cellRef)];
        }

        this.focusedCell = cellRef;
        this._isRangeDragging = true;
        this.refreshSelectionHighlight();
    }

    handleSelectionCellMouseOver(event) {
        if (this._isFillDragging) {
            return;
        }
        if (!this._isRangeDragging || !this._selectionAnchor || !event.node?.data || !event.column) {
            return;
        }
        if (!this.shouldApplySelectionToRow(event.node)) {
            return;
        }
        this.extendActiveRange(this._selectionAnchor, this.makeCellRef(event.node, event.column));
        this.refreshSelectionHighlight();
    }

    /** Keeps `focusedCell` in sync with AG Grid's own focus; collapses selection to the focused cell unless it's the target of an active drag/shift-extension gesture. */
    handleSelectionCellFocused(event) {
        if (event.rowIndex == null || !event.column || !this.api) {
            this.focusedCell = null;
            return;
        }
        if (this._mouseFocusPending) {
            return;
        }
        const node = this.api.getDisplayedRowAtIndex(event.rowIndex);
        if (!node?.data) {
            return;
        }

        this.focusedCell = this.makeCellRef(node, event.column);

        if (this._isRangeDragging || this._isExtending || this._isFillDragging) {
            return;
        }
        this.cellRanges = [this.makeRange(this.focusedCell, this.focusedCell)];
        this.refreshSelectionHighlight();
    }

    resolveSelectionStep({ rowIndex, colIndex, columns, direction }) {
        let r = rowIndex;
        let c = colIndex;
        if (direction === "up") r -= 1;
        if (direction === "down") r += 1;
        if (direction === "left") c -= 1;
        if (direction === "right") c += 1;

        if (r < 0 || r >= this.api.getDisplayedRowCount() || c < 0 || c >= columns.length) {
            return null;
        }
        const rowNode = this.api.getDisplayedRowAtIndex(r);
        if (!rowNode?.data || !this.shouldApplySelectionToRow(rowNode)) {
            return null;
        }
        return { rowIndex: r, colId: columns[c].getColId(), rowId: this.getEditRowId(rowNode.data) };
    }

    handleSelectionCellKeyDown(event) {
        const domEvent = event.event;
        const key = domEvent?.key;
        if (!key && !domEvent?.code) {
            return;
        }

        if (matchKeyboardShortcut(domEvent, { mod: true, code: "KeyA", key: "a" })) {
            domEvent.preventDefault();
            this.selectAllVisibleCells();
            return;
        }

        const direction = ARROW_DIRECTIONS[key];
        if (!direction || !domEvent.shiftKey) {
            this._isExtending = false;
            return;
        }
        if (this.api?.getEditingCells()?.length) {
            return;
        }
        if (!event.node?.data || !event.column) {
            return;
        }

        const columns = this.api.getAllDisplayedColumns();
        const colIndex = columns.indexOf(event.column);
        if (colIndex === -1) {
            return;
        }

        if (!this._isExtending) {
            this._selectionAnchor = this.makeCellRef(event.node, event.column);
            this._isExtending = true;
        }

        const next = this.resolveSelectionStep({ rowIndex: event.node.rowIndex, colIndex, columns, direction });
        if (!next) {
            return;
        }

        domEvent.preventDefault();
        this.extendActiveRange(this._selectionAnchor, { rowId: next.rowId, colId: next.colId });
        this.api.setFocusedCell(next.rowIndex, next.colId);
        this.refreshSelectionHighlight();
    }

    selectAllVisibleCells() {
        if (!this.api) {
            return;
        }
        const columns = this.api.getAllDisplayedColumns();
        const rowCount = this.api.getDisplayedRowCount();
        if (!columns.length || !rowCount) {
            return;
        }
        const firstNode = this.api.getDisplayedRowAtIndex(0);
        const lastNode = this.api.getDisplayedRowAtIndex(rowCount - 1);
        if (!firstNode?.data || !lastNode?.data) {
            return;
        }

        const start = this.makeCellRef(firstNode, columns[0]);
        const end = this.makeCellRef(lastNode, columns[columns.length - 1]);
        this._selectionAnchor = start;
        this._isExtending = false;
        this.cellRanges = [this.makeRange(start, end)];
        this.refreshSelectionHighlight();
    }

    /** Raw range state (`{ startRowId, startColId, endRowId, endColId }[]`); callers resolve to indices via own lookups if needed. */
    getCellRanges() {
        return this.cellRanges.map(range => ({ ...range }));
    }

    clearCellSelection() {
        this.cellRanges = [];
        this._selectionAnchor = null;
        this._isExtending = false;
        this.refreshSelectionHighlight();
    }

    buildSelectionGridOptions() {
        if (!this.isSelectionEnabled()) return {};

        return {
            onCellMouseDown: event => this.handleSelectionCellMouseDown(event),
            onCellMouseOver: event => this.handleSelectionCellMouseOver(event),
            onCellFocused: event => this.handleSelectionCellFocused(event),
            onCellKeyDown: event => this.handleSelectionCellKeyDown(event),
            onBodyScroll: () => this.refreshSelectionHighlight()
        };
    }
};
