import { isSummarySectionRow, TABLE_SECTIONS } from "../section/sections.js";
import { ROW_REORDER_SOURCES } from "./constants.js";
import {
    buildRowReorderMovePayload,
    collectLocalRowIds,
    computeTargetInsertIndex,
    getStableRowId,
    reorderSiblingBlock,
    resolveMergeBlock,
    resolveReorderContext,
    restoreSiblingListOrder
} from "./ops.js";

const ROW_REORDER_DEFAULTS = {
    enabled: true,
    handle: "gutter",
    gutterWidth: 12,
    allowSummary: false,
    /** `"siblings"` — reorder within same parent list; `false` — top-level body rows only */
    allowTree: "siblings"
};

/**
 * Row drag-and-drop reorder layer (custom gutter DnD, not AG Grid rowDrag module).
 * Client-first commit into source arrays + validate/save callbacks + undo stack.
 */
export const RowReorderMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._rowReorderDrag = null;
        this._rowReorderDropIndicatorEl = null;
        this._rowReorderGutterHoverRowId = null;
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

        if (this.getRowReorderOptions().allowTree === false && ctx.parentRowId != null) {
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
        if (this._rowReorderDropIndicatorEl || !this.container) {
            return;
        }
        const indicator = document.createElement("div");
        indicator.className = "dinext-table-row-reorder-drop-indicator";
        indicator.setAttribute("aria-hidden", "true");
        indicator.hidden = true;
        this.container.appendChild(indicator);
        this._rowReorderDropIndicatorEl = indicator;
    }

    clearRowReorderUi() {
        this.container?.classList.remove(
            "dinext-table--row-reorder-grabbing",
            "dinext-table--row-reorder-gutter-hover"
        );
        this._rowReorderGutterHoverRowId = null;
        if (this._rowReorderDropIndicatorEl) {
            this._rowReorderDropIndicatorEl.hidden = true;
        }
        this.container?.querySelectorAll(".ag-row.dinext-table-row--dragging").forEach((el) => {
            el.classList.remove("dinext-table-row--dragging");
        });
        this.container?.querySelectorAll(".ag-row.dinext-table-row-reorder-drop-target").forEach((el) => {
            el.classList.remove("dinext-table-row-reorder-drop-target");
        });
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

            event.preventDefault();
            event.stopPropagation();
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

        this.container.addEventListener("mousedown", this._onRowReorderMouseDown);
        document.addEventListener("mousemove", this._onRowReorderMouseMove);
        document.addEventListener("mouseup", this._onRowReorderMouseUp);
    }

    destroyRowReorderListeners() {
        if (this._onRowReorderMouseDown && this.container) {
            this.container.removeEventListener("mousedown", this._onRowReorderMouseDown);
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
            this._rowReorderGutterHoverRowId = null;
            return;
        }

        const rowEl = this.getRowElementFromPoint(event.clientX, event.clientY);
        if (!rowEl || !this.isRowReorderGutterHit(rowEl, event.clientX)) {
            this.container?.classList.remove("dinext-table--row-reorder-gutter-hover");
            this._rowReorderGutterHoverRowId = null;
            return;
        }

        const rowNode = this.getDisplayedRowNodeFromElement(rowEl);
        if (!this.canStartRowReorder(rowNode)) {
            this.container?.classList.remove("dinext-table--row-reorder-gutter-hover");
            return;
        }

        this.container.classList.add("dinext-table--row-reorder-gutter-hover");
        this._rowReorderGutterHoverRowId = getStableRowId(rowNode.data, this.options);
    }

    beginRowReorderDrag(rowNode, rowEl) {
        const rowId = getStableRowId(rowNode.data, this.options);
        const section = this.resolveRowReorderSection(rowNode.data);
        const sourceRows = this.getRowReorderSourceRows(section);
        const ctx = resolveReorderContext(sourceRows, rowId, this.options);
        if (!ctx) {
            return;
        }

        const orderBefore = collectLocalRowIds(ctx.list, this.options);
        this._rowReorderDrag = {
            rowId,
            section,
            sourceRows,
            ctx,
            orderBefore,
            dropTargetIndex: null,
            dropRowEl: null,
            dragRowEls: this.collectDisplayedRowElementsForBlock(ctx, section)
        };

        this.container.classList.add("dinext-table--row-reorder-grabbing");
        for (const el of this._rowReorderDrag.dragRowEls) {
            el.classList.add("dinext-table-row--dragging");
        }
    }

    collectDisplayedRowElementsForBlock(ctx, section) {
        const elements = [];
        if (!this.api) {
            return elements;
        }

        const rowIdField = this.options.rowIdField || "id";
        const blockLocalIds = new Set(
            ctx.list
                .slice(ctx.index, ctx.index + ctx.blockSize)
                .map((row) => String(row[rowIdField]))
        );

        this.api.forEachNode((node) => {
            if (!node.data || this.resolveRowReorderSection(node.data) !== section) {
                return;
            }
            const stableId = getStableRowId(node.data, this.options);
            const localId = String(stableId).split(":").pop();
            if (!blockLocalIds.has(localId)) {
                return;
            }
            if (ctx.parentRowId != null && !String(stableId).startsWith(`${ctx.parentRowId}:`)) {
                return;
            }
            if (ctx.parentRowId == null && String(stableId).includes(":")) {
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

        drag.dropRowEl?.classList.remove("dinext-table-row-reorder-drop-target");
        drag.dropRowEl = null;
        drag.dropTargetIndex = null;

        const hoverRowEl = this.getRowElementFromPoint(event.clientX, event.clientY);
        if (!hoverRowEl) {
            this.hideRowReorderDropIndicator();
            return;
        }

        const hoverNode = this.getDisplayedRowNodeFromElement(hoverRowEl);
        if (!hoverNode?.data) {
            this.hideRowReorderDropIndicator();
            return;
        }

        const hoverRowId = getStableRowId(hoverNode.data, this.options);
        const hoverCtx = resolveReorderContext(drag.sourceRows, hoverRowId, this.options);
        if (!hoverCtx) {
            this.hideRowReorderDropIndicator();
            return;
        }

        const rect = hoverRowEl.getBoundingClientRect();
        const insertBefore = event.clientY < rect.top + rect.height / 2;
        const targetIndex = computeTargetInsertIndex(drag.ctx, hoverCtx, insertBefore);
        if (targetIndex == null) {
            this.hideRowReorderDropIndicator();
            return;
        }

        drag.dropTargetIndex = targetIndex;
        drag.dropRowEl = hoverRowEl;
        hoverRowEl.classList.add("dinext-table-row-reorder-drop-target");
        this.showRowReorderDropIndicator(hoverRowEl, insertBefore);
    }

    showRowReorderDropIndicator(rowEl, insertBefore) {
        const indicator = this._rowReorderDropIndicatorEl;
        if (!indicator || !this.container) {
            return;
        }

        const containerRect = this.container.getBoundingClientRect();
        const rowRect = rowEl.getBoundingClientRect();
        const top = insertBefore ? rowRect.top : rowRect.bottom;

        indicator.hidden = false;
        indicator.style.top = `${top - containerRect.top + this.container.scrollTop}px`;
        indicator.style.left = "0";
        indicator.style.right = "0";
    }

    hideRowReorderDropIndicator() {
        if (this._rowReorderDropIndicatorEl) {
            this._rowReorderDropIndicatorEl.hidden = true;
        }
    }

    finishRowReorderDrag() {
        const drag = this._rowReorderDrag;
        this._rowReorderDrag = null;
        this.clearRowReorderUi();

        if (!drag || drag.dropTargetIndex == null) {
            return;
        }

        this.commitRowReorder({
            section: drag.section,
            ctx: drag.ctx,
            toIndex: drag.dropTargetIndex,
            orderBefore: drag.orderBefore
        });
    }

    applySiblingListOrder(section, ctx, orderedLocalIds) {
        restoreSiblingListOrder(ctx.list, orderedLocalIds, this.options);
        this.refreshAfterRowReorder(section);
    }

    refreshAfterRowReorder(section) {
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
    }

    commitRowReorder({ section, ctx, toIndex, orderBefore }) {
        const fromIndex = ctx.index;
        const blockSize = ctx.blockSize;
        const listSnapshot = ctx.list.map((row) => ({ ...row }));

        const move = buildRowReorderMovePayload({
            section,
            parentRowId: ctx.parentRowId,
            rowId: ctx.rowId,
            fromIndex,
            toIndex,
            blockSize,
            list: listSnapshot,
            options: this.options
        });

        const onValidateRowReorder = this.options.onValidateRowReorder;
        if (typeof onValidateRowReorder === "function") {
            const validation = onValidateRowReorder({
                table: this,
                source: ROW_REORDER_SOURCES.REORDER,
                move
            });
            if (validation !== true) {
                return false;
            }
        }

        const applied = reorderSiblingBlock(ctx.list, fromIndex, blockSize, toIndex);
        if (!applied) {
            return false;
        }

        const orderAfter = collectLocalRowIds(ctx.list, this.options);
        move.orderedLocalRowIds = orderAfter;
        move.orderedRowIds = orderAfter.map((localId) => (
            ctx.parentRowId ? `${ctx.parentRowId}:${localId}` : localId
        ));
        move.rows = ctx.list.map((row) => ({ ...row }));
        move.toIndex = toIndex;

        this.refreshAfterRowReorder(section);
        this.recordRowReorderUndo({
            section,
            ctx,
            orderBefore,
            orderAfter
        });

        const onRowReorder = this.options.onRowReorder;
        if (typeof onRowReorder === "function") {
            const revert = () => {
                this.applySiblingListOrder(section, ctx, orderBefore);
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

    recordRowReorderUndo({ section, ctx, orderBefore, orderAfter }) {
        if (typeof this.pushUndoCommand !== "function") {
            return;
        }

        this.pushUndoCommand({
            undo: () => {
                this.applySiblingListOrder(section, ctx, orderBefore);
            },
            execute: () => {
                this.applySiblingListOrder(section, ctx, orderAfter);
            }
        });
    }

    handleRowReorderBodyScroll() {
        if (this._rowReorderDrag) {
            this.hideRowReorderDropIndicator();
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
            } else {
                this.destroyRowReorderListeners();
                this.clearRowReorderUi();
            }
            return true;
        }
        return super.handleSetOption?.(key, value) ?? false;
    }

    buildRowReorderGridOptions() {
        if (!this.isRowReorderEnabled()) {
            return {};
        }

        return {
            onBodyScroll: () => this.handleRowReorderBodyScroll()
        };
    }
};

export {
    buildRowReorderMovePayload,
    collectLocalRowIds,
    computeTargetInsertIndex,
    reorderSiblingBlock,
    resolveMergeBlock,
    resolveReorderContext,
    restoreSiblingListOrder
} from "./ops.js";
