import { isSummarySectionRow, TABLE_SECTIONS } from "../section/sections.js";
import {
    ROW_REORDER_INDICATOR_BASE_LEFT_PX,
    ROW_REORDER_POSITIONS,
    ROW_REORDER_SOURCES,
    ROW_REORDER_TREE_INDENT_PX,
    ROW_REORDER_TREE_MODES
} from "./constants.js";
import {
    buildRowReorderMovePayload,
    collectDraggedRowIds,
    collectLocalRowIds,
    computeNudgeToIndex,
    getLocalRowId,
    getSiblingListForParent,
    getStableRowId,
    moveRowBlock,
    remapPathIdsForBlockMove,
    resolveDropPosition,
    resolveDropTarget,
    resolveReorderContext,
    restoreCrossParentOrders,
    restoreSiblingListOrder
} from "./ops.js";

const ROW_REORDER_DEFAULTS = {
    enabled: false,
    handle: "gutter",
    gutterWidth: 12,
    allowSummary: false,
    /**
     * `false` | `"siblings"` | `"reparent"`
     * Default `"siblings"` — safe for existing consumers; set `"reparent"` for full tree DnD.
     */
    allowTree: ROW_REORDER_TREE_MODES.SIBLINGS
};

/**
 * Row drag-and-drop reorder layer (custom gutter DnD, not AG Grid rowDrag module).
 * Client-first commit into source arrays + validate/save callbacks + undo stack.
 */
export const RowReorderMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._rowReorderDrag = null;
        this._rowReorderDropGapEl = null;
        this._rowReorderDropInsideEl = null;
    }

    destroyFeatures() {
        this.destroyRowReorderListeners();
        this.clearRowReorderUi();
        super.destroyFeatures();
    }

    afterGridCreated() {
        super.afterGridCreated();
        if (this.isRowReorderEnabled()) {
            this.ensureRowReorderDropIndicator();
            this.bindRowReorderListeners();
            this.container?.classList.add("dinext-table--row-reorder-enabled");
        }
    }

    getRowReorderOptions() {
        return { ...ROW_REORDER_DEFAULTS, ...(this.options.rowReorder || {}) };
    }

    getRowReorderTreeMode() {
        const mode = this.getRowReorderOptions().allowTree;
        if (mode === ROW_REORDER_TREE_MODES.REPARENT) {
            return ROW_REORDER_TREE_MODES.REPARENT;
        }
        if (mode === ROW_REORDER_TREE_MODES.OFF) {
            return ROW_REORDER_TREE_MODES.OFF;
        }
        return ROW_REORDER_TREE_MODES.SIBLINGS;
    }

    isRowReorderEnabled() {
        return !!this.getRowReorderOptions().enabled;
    }

    shouldApplyRowReorderToRow(rowNode) {
        return !!rowNode?.data;
    }

    isRowReorderBlocked() {
        if (!this.api) {
            return true;
        }
        if (this.api.getEditingCells()?.length) {
            return true;
        }
        if (this.isGridSorted()) {
            return true;
        }
        if (this._rowReorderDrag) {
            return true;
        }
        return false;
    }

    isGridSorted() {
        const state = this.api?.getColumnState?.() || [];
        return state.some((col) => col.sort != null);
    }

    getRowReorderSourceRows(section) {
        if (section === TABLE_SECTIONS.SUMMARY) {
            return this.summarySourceData || [];
        }
        return this.sourceData || [];
    }

    resolveRowReorderSection(row) {
        return isSummarySectionRow(row) ? TABLE_SECTIONS.SUMMARY : TABLE_SECTIONS.BODY;
    }

    canStartRowReorder(rowNode) {
        if (!this.isRowReorderEnabled() || !rowNode?.data || this.isRowReorderBlocked()) {
            return false;
        }
        if (!this.shouldApplyRowReorderToRow(rowNode)) {
            return false;
        }

        const section = this.resolveRowReorderSection(rowNode.data);
        if (section === TABLE_SECTIONS.SUMMARY && !this.getRowReorderOptions().allowSummary) {
            return false;
        }

        const rowId = getStableRowId(rowNode.data, this.options);
        const sourceRows = this.getRowReorderSourceRows(section);
        const ctx = resolveReorderContext(sourceRows, rowId, this.options);
        if (!ctx) {
            return false;
        }

        if (this.getRowReorderTreeMode() === ROW_REORDER_TREE_MODES.OFF && ctx.parentRowId != null) {
            return false;
        }

        const canReorderRow = this.options.canReorderRow;
        if (typeof canReorderRow === "function") {
            return canReorderRow({
                table: this,
                row: rowNode.data,
                rowId,
                section,
                parentRowId: ctx.parentRowId
            }) !== false;
        }

        return true;
    }

    isRowReorderGutterHit(rowEl, clientX) {
        if (!rowEl) {
            return false;
        }
        const gutterWidth = this.getRowReorderOptions().gutterWidth ?? 12;
        const rect = rowEl.getBoundingClientRect();
        return clientX - rect.left <= gutterWidth;
    }

    getRowElementFromPoint(clientX, clientY) {
        const el = document.elementFromPoint(clientX, clientY);
        const rowEl = el?.closest?.(".ag-row");
        if (!rowEl || !this.container?.contains(rowEl)) {
            return null;
        }
        if (rowEl.closest(".ag-floating-bottom, .ag-pinned-left-floating-bottom, .ag-pinned-right-floating-bottom")) {
            return null;
        }
        return rowEl;
    }

    getDisplayedRowNodeFromElement(rowEl) {
        if (!rowEl || !this.api) {
            return null;
        }
        const rowIndex = Number.parseInt(rowEl.getAttribute("row-index"), 10);
        if (!Number.isFinite(rowIndex)) {
            return null;
        }
        return this.api.getDisplayedRowAtIndex(rowIndex);
    }

    ensureRowReorderDropIndicator() {
        if (!this.container) {
            return;
        }
        if (!this._rowReorderDropGapEl) {
            const gap = document.createElement("div");
            gap.className = "dinext-table-row-reorder-drop-gap";
            gap.setAttribute("aria-hidden", "true");
            gap.hidden = true;
            this.container.appendChild(gap);
            this._rowReorderDropGapEl = gap;
        }
        if (!this._rowReorderDropInsideEl) {
            // Overlay frame — AG .ag-row outline/bg are clipped or overridden.
            const frame = document.createElement("div");
            frame.className = "dinext-table-row-reorder-drop-inside-frame";
            frame.setAttribute("aria-hidden", "true");
            frame.hidden = true;
            this.container.appendChild(frame);
            this._rowReorderDropInsideEl = frame;
        }
    }

    clearRowReorderUi() {
        this.container?.classList.remove(
            "dinext-table--row-reorder-grabbing",
            "dinext-table--row-reorder-gutter-hover",
            "dinext-table--row-reorder-drop-invalid"
        );
        this.hideRowReorderDropVisuals();
        this.container?.querySelectorAll(".ag-row.dinext-table-row--dragging").forEach((el) => {
            el.classList.remove("dinext-table-row--dragging");
        });
    }

    setRowReorderDropInvalid(invalid) {
        this.container?.classList.toggle("dinext-table--row-reorder-drop-invalid", !!invalid);
    }

    /** Left offset for between-row gap band (align with tree level). */
    resolveRowReorderGapLeft(rowEl, indentLevel) {
        const level = Math.max(0, Number(indentLevel) || 0);
        const treeCell = rowEl?.querySelector?.(".dinext-table-tree-cell");
        if (treeCell && this.container) {
            const containerRect = this.container.getBoundingClientRect();
            const cellRect = treeCell.getBoundingClientRect();
            const pad = Number.parseFloat(treeCell.style.paddingLeft) || 0;
            return Math.max(
                ROW_REORDER_INDICATOR_BASE_LEFT_PX,
                cellRect.left - containerRect.left + pad
            );
        }
        return ROW_REORDER_INDICATOR_BASE_LEFT_PX + level * ROW_REORDER_TREE_INDENT_PX;
    }

    bindRowReorderListeners() {
        this.destroyRowReorderListeners();

        this._onRowReorderMouseDown = (event) => {
            if (event.button !== 0 || !this.isRowReorderEnabled()) {
                return;
            }
            const rowEl = event.target.closest?.(".ag-row");
            if (!rowEl || !this.container.contains(rowEl)) {
                return;
            }
            if (!this.isRowReorderGutterHit(rowEl, event.clientX)) {
                return;
            }

            const rowNode = this.getDisplayedRowNodeFromElement(rowEl);
            if (!this.canStartRowReorder(rowNode)) {
                return;
            }

            // Capture: beat AG Grid / selection cellMouseDown (they run at target).
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation?.();
            this.beginRowReorderDrag(rowNode, rowEl);
        };

        this._onRowReorderMouseMove = (event) => {
            if (this._rowReorderDrag) {
                this.updateRowReorderDrag(event);
                return;
            }
            this.updateRowReorderGutterHover(event);
        };

        this._onRowReorderMouseUp = () => {
            if (this._rowReorderDrag) {
                this.finishRowReorderDrag();
            }
        };

        this.container.addEventListener("mousedown", this._onRowReorderMouseDown, true);
        document.addEventListener("mousemove", this._onRowReorderMouseMove);
        document.addEventListener("mouseup", this._onRowReorderMouseUp);
    }

    destroyRowReorderListeners() {
        if (this._onRowReorderMouseDown && this.container) {
            this.container.removeEventListener("mousedown", this._onRowReorderMouseDown, true);
        }
        if (this._onRowReorderMouseMove) {
            document.removeEventListener("mousemove", this._onRowReorderMouseMove);
        }
        if (this._onRowReorderMouseUp) {
            document.removeEventListener("mouseup", this._onRowReorderMouseUp);
        }
        this._onRowReorderMouseDown = null;
        this._onRowReorderMouseMove = null;
        this._onRowReorderMouseUp = null;
    }

    updateRowReorderGutterHover(event) {
        if (!this.isRowReorderEnabled() || this.isRowReorderBlocked()) {
            this.container?.classList.remove("dinext-table--row-reorder-gutter-hover");
            return;
        }

        const rowEl = this.getRowElementFromPoint(event.clientX, event.clientY);
        if (!rowEl || !this.isRowReorderGutterHit(rowEl, event.clientX)) {
            this.container?.classList.remove("dinext-table--row-reorder-gutter-hover");
            return;
        }

        const rowNode = this.getDisplayedRowNodeFromElement(rowEl);
        if (!this.canStartRowReorder(rowNode)) {
            this.container?.classList.remove("dinext-table--row-reorder-gutter-hover");
            return;
        }

        this.container.classList.add("dinext-table--row-reorder-gutter-hover");
    }

    beginRowReorderDrag(rowNode, rowEl) {
        const rowId = getStableRowId(rowNode.data, this.options);
        const section = this.resolveRowReorderSection(rowNode.data);
        const sourceRows = this.getRowReorderSourceRows(section);
        const ctx = resolveReorderContext(sourceRows, rowId, this.options);
        if (!ctx) {
            return;
        }

        const fromList = ctx.list;
        this._rowReorderDrag = {
            rowId,
            section,
            sourceRows,
            ctx,
            fromOrderBefore: collectLocalRowIds(fromList, this.options),
            dropTarget: null,
            dragRowEls: this.collectDisplayedRowElementsForBlock(ctx, section)
        };

        // DnD and cell range selection must not run together.
        this.suppressSelectionForRowReorder?.();

        this.container.classList.add("dinext-table--row-reorder-grabbing");
        for (const el of this._rowReorderDrag.dragRowEls) {
            el.classList.add("dinext-table-row--dragging");
        }
    }

    /** True while gutter row-drag is active (selection/clipboard layers check this). */
    isRowReorderDragging() {
        return !!this._rowReorderDrag;
    }

    collectDisplayedRowElementsForBlock(ctx, section) {
        const elements = [];
        if (!this.api) {
            return elements;
        }

        const draggedIds = new Set(collectDraggedRowIds(ctx, this.options));

        this.api.forEachNode((node) => {
            if (!node.data || this.resolveRowReorderSection(node.data) !== section) {
                return;
            }
            const stableId = getStableRowId(node.data, this.options);
            if (!draggedIds.has(stableId)) {
                return;
            }
            const rowIndex = node.rowIndex;
            if (rowIndex == null) {
                return;
            }
            const rowEl = this.container.querySelector(`.ag-row[row-index="${rowIndex}"]`);
            if (rowEl) {
                elements.push(rowEl);
            }
        });

        return elements;
    }

    updateRowReorderDrag(event) {
        const drag = this._rowReorderDrag;
        if (!drag) {
            return;
        }

        drag.dropTarget = null;

        const hoverRowEl = this.getRowElementFromPoint(event.clientX, event.clientY);
        if (!hoverRowEl) {
            this.hideRowReorderDropVisuals();
            this.setRowReorderDropInvalid(true);
            return;
        }

        const hoverNode = this.getDisplayedRowNodeFromElement(hoverRowEl);
        if (!hoverNode?.data) {
            this.hideRowReorderDropVisuals();
            this.setRowReorderDropInvalid(true);
            return;
        }

        const hoverRowId = getStableRowId(hoverNode.data, this.options);
        const allowTree = this.getRowReorderTreeMode();
        const allowInside = allowTree === ROW_REORDER_TREE_MODES.REPARENT;
        const rect = hoverRowEl.getBoundingClientRect();
        const position = resolveDropPosition(event.clientY - rect.top, rect.height, allowInside);

        const dropTarget = resolveDropTarget({
            sourceRows: drag.sourceRows,
            dragCtx: drag.ctx,
            hoverRowId,
            position,
            allowTree,
            options: this.options
        });

        if (!dropTarget) {
            this.hideRowReorderDropVisuals();
            this.setRowReorderDropInvalid(true);
            return;
        }

        drag.dropTarget = dropTarget;
        this.setRowReorderDropInvalid(false);

        if (dropTarget.position === ROW_REORDER_POSITIONS.INSIDE) {
            this.hideRowReorderDropGap();
            this.showRowReorderDropInside(hoverRowEl);
        } else {
            this.hideRowReorderDropInside();
            this.showRowReorderDropGap(hoverRowEl, dropTarget);
        }
    }

    /** Union rect of all AG pin slices for the same displayed row-index. */
    getRowReorderRowBounds(rowEl) {
        if (!rowEl || !this.container) {
            return null;
        }
        const rowIndex = rowEl.getAttribute("row-index");
        const safeIndex = rowIndex == null
            ? null
            : (typeof CSS !== "undefined" && typeof CSS.escape === "function"
                ? CSS.escape(String(rowIndex))
                : String(rowIndex));
        const slices = safeIndex != null
            ? [...this.container.querySelectorAll(`.ag-row[row-index="${safeIndex}"]`)]
            : [rowEl];
        if (!slices.length) {
            return null;
        }

        let left = Infinity;
        let top = Infinity;
        let right = -Infinity;
        let bottom = -Infinity;
        for (const el of slices) {
            const r = el.getBoundingClientRect();
            left = Math.min(left, r.left);
            top = Math.min(top, r.top);
            right = Math.max(right, r.right);
            bottom = Math.max(bottom, r.bottom);
        }
        return { left, top, right, bottom, width: right - left, height: bottom - top };
    }

    showRowReorderDropGap(rowEl, dropTarget) {
        const gapEl = this._rowReorderDropGapEl;
        if (!gapEl || !this.container || !dropTarget) {
            return;
        }

        const gapHeight = 4;
        const containerRect = this.container.getBoundingClientRect();
        const rowRect = rowEl.getBoundingClientRect();
        const edge = dropTarget.position === ROW_REORDER_POSITIONS.BEFORE
            ? rowRect.top
            : rowRect.bottom;
        const top = edge - (gapHeight / 2) - containerRect.top + this.container.scrollTop;
        const left = this.resolveRowReorderGapLeft(rowEl, dropTarget.indentLevel);

        gapEl.hidden = false;
        gapEl.style.height = `${gapHeight}px`;
        gapEl.style.top = `${top}px`;
        gapEl.style.left = `${left}px`;
        gapEl.style.right = "0";
        gapEl.style.width = "";
    }

    showRowReorderDropInside(rowEl) {
        const frame = this._rowReorderDropInsideEl;
        if (!frame || !this.container) {
            return;
        }
        const bounds = this.getRowReorderRowBounds(rowEl);
        if (!bounds || bounds.width <= 0 || bounds.height <= 0) {
            this.hideRowReorderDropInside();
            return;
        }

        const containerRect = this.container.getBoundingClientRect();
        frame.hidden = false;
        frame.style.top = `${bounds.top - containerRect.top + this.container.scrollTop}px`;
        frame.style.left = `${bounds.left - containerRect.left + this.container.scrollLeft}px`;
        frame.style.width = `${bounds.width}px`;
        frame.style.height = `${bounds.height}px`;
        frame.style.right = "auto";
    }

    hideRowReorderDropGap() {
        if (this._rowReorderDropGapEl) {
            this._rowReorderDropGapEl.hidden = true;
        }
    }

    hideRowReorderDropInside() {
        if (this._rowReorderDropInsideEl) {
            this._rowReorderDropInsideEl.hidden = true;
        }
    }

    hideRowReorderDropVisuals() {
        this.hideRowReorderDropGap();
        this.hideRowReorderDropInside();
    }

    finishRowReorderDrag() {
        const drag = this._rowReorderDrag;
        this._rowReorderDrag = null;
        this.clearRowReorderUi();

        if (!drag?.dropTarget) {
            return;
        }

        this.commitRowReorder({
            section: drag.section,
            ctx: drag.ctx,
            dropTarget: drag.dropTarget,
            fromOrderBefore: drag.fromOrderBefore
        });
    }

    applySiblingListOrder(section, parentRowId, orderedLocalIds) {
        const list = getSiblingListForParent(
            this.getRowReorderSourceRows(section),
            parentRowId,
            this.options
        );
        if (!list) {
            return;
        }
        restoreSiblingListOrder(list, orderedLocalIds, this.options);
        this.refreshAfterRowReorder(section);
    }

    refreshAfterRowReorder(section) {
        // Inner mixins (e.g. Sort) may clear derived state before we rebind rows.
        super.refreshAfterRowReorder?.(section);

        if (section === TABLE_SECTIONS.SUMMARY) {
            if (typeof this.syncSummarySection === "function") {
                this.syncSummarySection();
            }
            return;
        }

        if (typeof this.syncVisibleRows === "function") {
            this.syncVisibleRows();
        }
        this.setGridOption("rowData", [...(this.rowData || [])]);
        this.refreshAllTreeToggles?.();
    }

    remapRowPathIdsAfterReorder(fromParentRowId, toParentRowId, localIds) {
        if (fromParentRowId === toParentRowId) {
            return;
        }
        if (this.expandedIds) {
            remapPathIdsForBlockMove(this.expandedIds, {
                fromParentRowId,
                toParentRowId,
                localIds
            });
        }
        super.remapRowPathIdsAfterReorder?.(fromParentRowId, toParentRowId, localIds);
    }

    resolveNudgeRowReorder(rowId, direction) {
        if (!rowId || !direction || this.isRowReorderBlocked()) {
            return null;
        }

        const node = this.api?.getRowNode?.(String(rowId));
        const row = node?.data || this.findSourceRow?.(String(rowId));
        if (!row) {
            return null;
        }

        const fakeNode = node || { data: row };
        if (!this.canStartRowReorder(fakeNode)) {
            return null;
        }

        const section = this.resolveRowReorderSection(row);
        const sourceRows = this.getRowReorderSourceRows(section);
        const ctx = resolveReorderContext(sourceRows, String(rowId), this.options);
        if (!ctx) {
            return null;
        }

        const toIndex = computeNudgeToIndex(
            ctx.list,
            ctx.index,
            ctx.blockSize,
            direction,
            this.options
        );
        if (toIndex == null) {
            return null;
        }

        const dropTarget = {
            position: direction < 0 ? ROW_REORDER_POSITIONS.BEFORE : ROW_REORDER_POSITIONS.AFTER,
            targetRowId: ctx.rowId,
            fromParentRowId: ctx.parentRowId,
            toParentRowId: ctx.parentRowId,
            fromIndex: ctx.index,
            toIndex,
            blockSize: ctx.blockSize,
            rowId: ctx.rowId,
            newRowId: ctx.rowId,
            indentLevel: ctx.parentRowId == null ? 0 : String(ctx.parentRowId).split(":").length,
            sameParent: true
        };

        return {
            section,
            ctx,
            dropTarget,
            fromOrderBefore: collectLocalRowIds(ctx.list, this.options)
        };
    }

    /**
     * Move a row (or merge atom) one sibling slot up/down — same commit path as gutter DnD.
     * @param {string} rowId
     * @param {-1|1} direction
     */
    nudgeRowReorder(rowId, direction) {
        const resolved = this.resolveNudgeRowReorder(rowId, direction);
        if (!resolved) {
            return false;
        }
        return this.commitRowReorder(resolved);
    }

    canNudgeRowReorder(rowId, direction) {
        return this.resolveNudgeRowReorder(rowId, direction) != null;
    }

    commitRowReorder({ section, ctx, dropTarget, fromOrderBefore }) {
        const sourceRows = this.getRowReorderSourceRows(section);
        const {
            fromParentRowId,
            toParentRowId,
            fromIndex,
            toIndex,
            blockSize,
            position,
            targetRowId,
            rowId,
            newRowId
        } = dropTarget;

        const destListBefore = getSiblingListForParent(sourceRows, toParentRowId, this.options);
        if (!destListBefore) {
            return false;
        }

        const toOrderBefore = dropTarget.sameParent
            ? fromOrderBefore
            : collectLocalRowIds(destListBefore, this.options);

        const movedLocalIds = [];
        for (let i = 0; i < blockSize; i++) {
            const row = ctx.list[fromIndex + i];
            if (row) {
                movedLocalIds.push(getLocalRowId(row, this.options));
            }
        }

        const validateMove = buildRowReorderMovePayload({
            section,
            position,
            targetRowId,
            fromParentRowId,
            toParentRowId,
            rowId,
            newRowId,
            fromIndex,
            toIndex,
            blockSize,
            destList: destListBefore,
            options: this.options
        });

        const onValidateRowReorder = this.options.onValidateRowReorder;
        if (typeof onValidateRowReorder === "function") {
            const validation = onValidateRowReorder({
                table: this,
                source: ROW_REORDER_SOURCES.REORDER,
                move: validateMove
            });
            if (validation !== true) {
                return false;
            }
        }

        const applied = moveRowBlock(sourceRows, {
            fromParentRowId,
            fromIndex,
            blockSize,
            toParentRowId,
            toIndex
        }, this.options);
        if (!applied) {
            return false;
        }

        this.remapRowPathIdsAfterReorder(fromParentRowId, toParentRowId, movedLocalIds);

        const destList = getSiblingListForParent(sourceRows, toParentRowId, this.options);
        const fromList = getSiblingListForParent(sourceRows, fromParentRowId, this.options);
        const toOrderAfter = collectLocalRowIds(destList, this.options);
        const fromOrderAfter = dropTarget.sameParent
            ? toOrderAfter
            : collectLocalRowIds(fromList, this.options);

        const move = {
            ...validateMove,
            orderedLocalRowIds: toOrderAfter,
            orderedRowIds: toOrderAfter.map((localId) => (
                toParentRowId ? `${toParentRowId}:${localId}` : localId
            )),
            rows: (destList || []).map((row) => ({ ...row })),
            fromOrderedLocalRowIds: fromOrderAfter
        };

        this.refreshAfterRowReorder(section);

        // No expand-on-hover. After drop under a collapsed parent — open it
        // so the moved row is visible (lazy: expandRow loads if children still empty).
        if (
            toParentRowId != null
            && typeof this.expandRow === "function"
            && !this.isRowExpanded?.(toParentRowId)
        ) {
            Promise.resolve(this.expandRow(toParentRowId)).catch((err) => {
                console.error("DinextTable: expand after row-reorder failed", err);
            });
        }

        this.recordRowReorderUndo({
            section,
            dropTarget,
            movedLocalIds,
            fromOrderBefore,
            toOrderBefore,
            fromOrderAfter,
            toOrderAfter
        });

        const onRowReorder = this.options.onRowReorder;
        if (typeof onRowReorder === "function") {
            const revert = () => {
                this.revertRowReorderMove({
                    section,
                    dropTarget,
                    movedLocalIds,
                    fromOrderBefore,
                    toOrderBefore
                });
            };

            Promise.resolve(onRowReorder({
                table: this,
                source: ROW_REORDER_SOURCES.REORDER,
                move
            }))
                .then((result) => {
                    if (result === false) {
                        revert();
                    }
                })
                .catch((err) => {
                    revert();
                    console.error("DinextTable: onRowReorder failed", err);
                });
        }

        return true;
    }

    rebuildCrossParentOrders(section, fromParentRowId, toParentRowId, fromOrder, toOrder) {
        const sourceRows = this.getRowReorderSourceRows(section);
        const fromList = getSiblingListForParent(sourceRows, fromParentRowId, this.options);
        const toList = getSiblingListForParent(sourceRows, toParentRowId, this.options);
        if (!fromList || !toList) {
            return false;
        }
        return restoreCrossParentOrders(fromList, toList, fromOrder, toOrder, this.options);
    }

    revertRowReorderMove({
        section,
        dropTarget,
        movedLocalIds,
        fromOrderBefore,
        toOrderBefore
    }) {
        const { fromParentRowId, toParentRowId, sameParent } = dropTarget;

        if (sameParent) {
            this.applySiblingListOrder(section, toParentRowId, fromOrderBefore);
            return;
        }

        this.rebuildCrossParentOrders(
            section,
            fromParentRowId,
            toParentRowId,
            fromOrderBefore,
            toOrderBefore
        );
        this.remapRowPathIdsAfterReorder(toParentRowId, fromParentRowId, movedLocalIds);
        this.refreshAfterRowReorder(section);
    }

    recordRowReorderUndo({
        section,
        dropTarget,
        movedLocalIds,
        fromOrderBefore,
        toOrderBefore,
        fromOrderAfter,
        toOrderAfter
    }) {
        if (typeof this.pushUndoCommand !== "function") {
            return;
        }

        const { fromParentRowId, toParentRowId, sameParent } = dropTarget;

        this.pushUndoCommand({
            undo: () => {
                this.revertRowReorderMove({
                    section,
                    dropTarget,
                    movedLocalIds,
                    fromOrderBefore,
                    toOrderBefore
                });
            },
            execute: () => {
                if (sameParent) {
                    this.applySiblingListOrder(section, toParentRowId, toOrderAfter);
                    return;
                }
                this.rebuildCrossParentOrders(
                    section,
                    fromParentRowId,
                    toParentRowId,
                    fromOrderAfter,
                    toOrderAfter
                );
                this.remapRowPathIdsAfterReorder(fromParentRowId, toParentRowId, movedLocalIds);
                if (toParentRowId != null) {
                    this.expandedIds?.add(String(toParentRowId));
                }
                this.refreshAfterRowReorder(section);
            }
        });
    }

    handleRowReorderBodyScroll() {
        if (this._rowReorderDrag) {
            this.hideRowReorderDropVisuals();
        }
    }

    handleSetOption(key, value) {
        if (key === "rowReorder") {
            this.options.rowReorder = value;
            const enabled = this.isRowReorderEnabled();
            this.container?.classList.toggle("dinext-table--row-reorder-enabled", enabled);
            if (enabled && this.api) {
                this.ensureRowReorderDropIndicator();
                this.bindRowReorderListeners();
                if (this.options.gridOptions?.animateRows === undefined) {
                    this.setGridOption("animateRows", true);
                }
            } else {
                this.destroyRowReorderListeners();
                this.clearRowReorderUi();
            }
            this.refreshToolbar?.();
            return true;
        }
        return super.handleSetOption?.(key, value) ?? false;
    }

    buildRowReorderGridOptions() {
        if (!this.isRowReorderEnabled()) {
            return {};
        }

        const opts = {
            onBodyScroll: () => this.handleRowReorderBodyScroll()
        };
        // Soften order changes (gutter + toolbar nudge). Domain may override via gridOptions.
        if (this.options.gridOptions?.animateRows === undefined) {
            opts.animateRows = true;
        }
        return opts;
    }
};
