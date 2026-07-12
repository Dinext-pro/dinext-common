import { queryAgCellElement } from "../shared/utils.js";

const FILL_HANDLE_DEFAULTS = {
    enabled: undefined
};

const FILL_PREVIEW_CLASSES = [
    "dinext-table-cell-fill-preview",
    "dinext-table-cell-fill-preview-top",
    "dinext-table-cell-fill-preview-bottom",
    "dinext-table-cell-fill-preview-left",
    "dinext-table-cell-fill-preview-right"
];

/**
 * Excel-like fill handle on the bottom-right corner of the active range.
 * Drag ↓/↑/←/→ (axis-locked) to copy-fill the source pattern into extension cells.
 *
 * Mounted inside the corner .ag-cell (CSS right/bottom) so scroll moves it with the
 * grid DOM — no left/top sync on every body scroll.
 */
export const FillHandleMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._fillHandleEl = null;
        this._fillHandleHostCell = null;
        this._isFillDragging = false;
        this._fillSourceBounds = null;
        this._fillTargetBounds = null;
    }

    destroyFeatures() {
        this.destroyFillHandleListeners();
        this.hideFillHandle();
        this._fillHandleEl = null;
        super.destroyFeatures();
    }

    afterGridCreated() {
        super.afterGridCreated();
        if (this.isFillHandleEnabled()) {
            this.ensureFillHandleElement();
            this.updateFillHandle();
        }
    }

    getFillHandleOptions() {
        return { ...FILL_HANDLE_DEFAULTS, ...(this.options.fillHandle || {}) };
    }

    /** Default: enabled when clipboard is enabled. */
    isFillHandleEnabled() {
        const enabled = this.getFillHandleOptions().enabled;
        if (enabled !== undefined) {
            return !!enabled;
        }
        return this.isClipboardEnabled();
    }

    ensureFillHandleElement() {
        // AG Grid may destroy the host cell (virtualization) and take the handle with it.
        if (this._fillHandleEl && !this._fillHandleEl.isConnected) {
            this._fillHandleEl = null;
            this._fillHandleHostCell = null;
        }
        if (this._fillHandleEl) {
            return;
        }
        const handle = document.createElement("div");
        handle.className = "dinext-table-fill-handle";
        handle.setAttribute("role", "presentation");
        handle.addEventListener("mousedown", event => this.handleFillHandleMouseDown(event));
        this._fillHandleEl = handle;
    }

    isSelectionCornerRowDisplayed(maxRowIndex) {
        const firstRow = this.api?.getFirstDisplayedRowIndex();
        const lastRow = this.api?.getLastDisplayedRowIndex();
        if (firstRow == null || lastRow == null || firstRow < 0) {
            return false;
        }
        return maxRowIndex >= firstRow && maxRowIndex <= lastRow;
    }

    clearFillHandleHost() {
        if (this._fillHandleHostCell) {
            this._fillHandleHostCell.classList.remove("dinext-table-cell--fill-handle-host");
            this._fillHandleHostCell = null;
        }
    }

    hideFillHandle() {
        if (this._fillHandleEl) {
            this._fillHandleEl.style.display = "none";
            this._fillHandleEl.remove();
        }
        this.clearFillHandleHost();
    }

    mountFillHandleToCell(cellEl) {
        if (!this._fillHandleEl || !cellEl) {
            return;
        }
        if (this._fillHandleHostCell && this._fillHandleHostCell !== cellEl) {
            this._fillHandleHostCell.classList.remove("dinext-table-cell--fill-handle-host");
        }
        if (this._fillHandleEl.parentElement !== cellEl) {
            cellEl.appendChild(this._fillHandleEl);
        }
        cellEl.classList.add("dinext-table-cell--fill-handle-host");
        this._fillHandleHostCell = cellEl;
        this._fillHandleEl.style.display = "block";
    }

    destroyFillHandleListeners() {
        if (this._onFillMouseMove) {
            document.removeEventListener("mousemove", this._onFillMouseMove);
            this._onFillMouseMove = null;
        }
        if (this._onFillMouseUp) {
            document.removeEventListener("mouseup", this._onFillMouseUp);
            this._onFillMouseUp = null;
        }
    }

    refreshSelectionHighlight() {
        super.refreshSelectionHighlight();
        this.updateFillHandle();
    }

    isFillHandleVisible() {
        if (!this.isFillHandleEnabled() || !this.api || this._isFillDragging) {
            return false;
        }
        if (this.api.getEditingCells()?.length) {
            return false;
        }
        const bounds = this.getClipboardTargetBounds();
        return !!bounds;
    }

    getCellElement(rowIndex, colId) {
        return queryAgCellElement(this.container, rowIndex, colId);
    }

    updateFillHandle() {
        if (!this.isFillHandleEnabled()) {
            return;
        }
        this.ensureFillHandleElement();
        if (!this._fillHandleEl) {
            return;
        }
        if (!this.isFillHandleVisible()) {
            this.hideFillHandle();
            return;
        }

        const bounds = this.getClipboardTargetBounds();
        if (!bounds || !this.isSelectionCornerRowDisplayed(bounds.maxRowIndex)) {
            this.hideFillHandle();
            return;
        }

        const columns = this.api.getAllDisplayedColumns();
        const colId = columns[bounds.maxColIndex]?.getColId();
        const cellEl = colId != null ? this.getCellElement(bounds.maxRowIndex, colId) : null;
        // Cell gone (virtualized / scrolled away) → detach. When back in DOM, re-mount.
        // Position is CSS on the cell — no left/top sync while scrolling.
        if (!cellEl) {
            this.hideFillHandle();
            return;
        }

        this.mountFillHandleToCell(cellEl);
    }

    getCellIndicesFromPoint(clientX, clientY) {
        const el = document.elementFromPoint(clientX, clientY);
        const cellEl = el?.closest?.(".ag-cell");
        const rowEl = cellEl?.closest?.(".ag-row");
        if (!cellEl || !rowEl || !this.container?.contains(cellEl)) {
            return null;
        }

        const rowIndex = Number.parseInt(rowEl.getAttribute("row-index"), 10);
        const colId = cellEl.getAttribute("col-id");
        if (!Number.isFinite(rowIndex) || !colId) {
            return null;
        }

        const columns = this.api.getAllDisplayedColumns();
        const colIndex = columns.findIndex(col => col.getColId() === colId);
        if (colIndex === -1) {
            return null;
        }

        return { rowIndex, colIndex };
    }

    computeFillTargetBounds(sourceBounds, hoverRowIndex, hoverColIndex) {
        const cornerRow = sourceBounds.maxRowIndex;
        const cornerCol = sourceBounds.maxColIndex;
        const dRow = hoverRowIndex - cornerRow;
        const dCol = hoverColIndex - cornerCol;

        if (Math.abs(dRow) >= Math.abs(dCol)) {
            if (dRow >= 0) {
                return {
                    minRowIndex: sourceBounds.minRowIndex,
                    maxRowIndex: hoverRowIndex,
                    minColIndex: sourceBounds.minColIndex,
                    maxColIndex: sourceBounds.maxColIndex
                };
            }
            return {
                minRowIndex: hoverRowIndex,
                maxRowIndex: sourceBounds.maxRowIndex,
                minColIndex: sourceBounds.minColIndex,
                maxColIndex: sourceBounds.maxColIndex
            };
        }

        if (dCol >= 0) {
            return {
                minRowIndex: sourceBounds.minRowIndex,
                maxRowIndex: sourceBounds.maxRowIndex,
                minColIndex: sourceBounds.minColIndex,
                maxColIndex: hoverColIndex
            };
        }
        return {
            minRowIndex: sourceBounds.minRowIndex,
            maxRowIndex: sourceBounds.maxRowIndex,
            minColIndex: hoverColIndex,
            maxColIndex: sourceBounds.maxColIndex
        };
    }

    boundsExtendSource(sourceBounds, targetBounds) {
        return targetBounds.minRowIndex < sourceBounds.minRowIndex
            || targetBounds.maxRowIndex > sourceBounds.maxRowIndex
            || targetBounds.minColIndex < sourceBounds.minColIndex
            || targetBounds.maxColIndex > sourceBounds.maxColIndex;
    }

    getCellFillPreviewState(rowIndex, colIndex, sourceBounds, targetBounds) {
        if (rowIndex < targetBounds.minRowIndex || rowIndex > targetBounds.maxRowIndex) {
            return null;
        }
        if (colIndex < targetBounds.minColIndex || colIndex > targetBounds.maxColIndex) {
            return null;
        }
        if (rowIndex >= sourceBounds.minRowIndex && rowIndex <= sourceBounds.maxRowIndex
            && colIndex >= sourceBounds.minColIndex && colIndex <= sourceBounds.maxColIndex) {
            return null;
        }

        return {
            top: rowIndex === targetBounds.minRowIndex,
            bottom: rowIndex === targetBounds.maxRowIndex,
            left: colIndex === targetBounds.minColIndex,
            right: colIndex === targetBounds.maxColIndex
        };
    }

    clearFillPreviewDom() {
        if (!this.container) {
            return;
        }
        const selector = FILL_PREVIEW_CLASSES.map(cls => `.${cls}`).join(",");
        this.container.querySelectorAll(selector).forEach(el => el.classList.remove(...FILL_PREVIEW_CLASSES));
    }

    refreshFillPreview() {
        this.clearFillPreviewDom();
        if (!this._isFillDragging || !this._fillSourceBounds || !this._fillTargetBounds || !this.container || !this.api) {
            return;
        }
        if (!this.boundsExtendSource(this._fillSourceBounds, this._fillTargetBounds)) {
            return;
        }

        const columns = this.api.getAllDisplayedColumns();
        const firstRow = this.api.getFirstDisplayedRowIndex();
        const lastRow = this.api.getLastDisplayedRowIndex();
        if (firstRow == null || lastRow == null || firstRow < 0) {
            return;
        }

        const { minRowIndex, maxRowIndex, minColIndex, maxColIndex } = this._fillTargetBounds;
        const minRow = Math.max(minRowIndex, firstRow);
        const maxRow = Math.min(maxRowIndex, lastRow);

        for (let rowIndex = minRow; rowIndex <= maxRow; rowIndex += 1) {
            for (let colIndex = minColIndex; colIndex <= maxColIndex; colIndex += 1) {
                const state = this.getCellFillPreviewState(
                    rowIndex,
                    colIndex,
                    this._fillSourceBounds,
                    this._fillTargetBounds
                );
                if (!state) {
                    continue;
                }
                const colId = columns[colIndex].getColId();
                const cellEl = this.getCellElement(rowIndex, colId);
                if (!cellEl) {
                    continue;
                }
                cellEl.classList.add("dinext-table-cell-fill-preview");
                if (state.top) cellEl.classList.add("dinext-table-cell-fill-preview-top");
                if (state.bottom) cellEl.classList.add("dinext-table-cell-fill-preview-bottom");
                if (state.left) cellEl.classList.add("dinext-table-cell-fill-preview-left");
                if (state.right) cellEl.classList.add("dinext-table-cell-fill-preview-right");
            }
        }
    }

    applySelectionFromBounds(bounds) {
        const columns = this.api.getAllDisplayedColumns();
        const startNode = this.api.getDisplayedRowAtIndex(bounds.minRowIndex);
        const endNode = this.api.getDisplayedRowAtIndex(bounds.maxRowIndex);
        if (!startNode?.data || !endNode?.data) {
            return;
        }

        const start = this.makeCellRef(startNode, columns[bounds.minColIndex]);
        const end = this.makeCellRef(endNode, columns[bounds.maxColIndex]);
        this._selectionAnchor = start;
        this.cellRanges = [this.makeRange(start, end)];
        this.focusedCell = end;
        this.refreshSelectionHighlight();
    }

    handleFillHandleMouseDown(event) {
        if (event.button !== 0 || !this.isFillHandleEnabled() || !this.api) {
            return;
        }

        const sourceBounds = this.getClipboardTargetBounds();
        if (!sourceBounds) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();

        this._isFillDragging = true;
        this._fillSourceBounds = { ...sourceBounds };
        this._fillTargetBounds = { ...sourceBounds };
        this._fillHandleEl.style.display = "none";

        this._onFillMouseMove = moveEvent => this.handleFillDragMouseMove(moveEvent);
        this._onFillMouseUp = upEvent => this.handleFillDragMouseUp(upEvent);
        document.addEventListener("mousemove", this._onFillMouseMove);
        document.addEventListener("mouseup", this._onFillMouseUp);
    }

    handleFillDragMouseMove(event) {
        if (!this._isFillDragging || !this._fillSourceBounds) {
            return;
        }

        const indices = this.getCellIndicesFromPoint(event.clientX, event.clientY);
        if (!indices) {
            return;
        }

        this._fillTargetBounds = this.computeFillTargetBounds(
            this._fillSourceBounds,
            indices.rowIndex,
            indices.colIndex
        );
        this.refreshFillPreview();
    }

    handleFillDragMouseUp() {
        this.destroyFillHandleListeners();

        const sourceBounds = this._fillSourceBounds;
        const targetBounds = this._fillTargetBounds;
        const hadExtension = sourceBounds && targetBounds
            && this.boundsExtendSource(sourceBounds, targetBounds);

        this._isFillDragging = false;
        this.clearFillPreviewDom();

        if (hadExtension) {
            this.fillRange(sourceBounds, targetBounds, { respectSelectionMask: false });
            this.applySelectionFromBounds(targetBounds);
        } else {
            this.updateFillHandle();
        }

        this._fillSourceBounds = null;
        this._fillTargetBounds = null;
    }

    handleFillHandleBodyScroll() {
        if (this._isFillDragging) {
            this.refreshFillPreview();
        } else {
            this.updateFillHandle();
        }
    }

    handleFillHandleCellFocused() {
        this.updateFillHandle();
    }

    buildFillHandleGridOptions() {
        if (!this.isFillHandleEnabled()) {
            return {};
        }

        return {
            onBodyScroll: () => this.handleFillHandleBodyScroll(),
            onCellFocused: () => this.handleFillHandleCellFocused()
        };
    }
};
