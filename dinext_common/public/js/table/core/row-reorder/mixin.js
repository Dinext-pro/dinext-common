import { isSummarySectionRow, TABLE_SECTIONS } from "../section/sections.js";
import {
    ROW_REORDER_COL_ID,
    ROW_REORDER_POSITIONS,
    ROW_REORDER_SOURCES,
    ROW_REORDER_TREE_MODES,
    ROW_REORDER_EXPAND_DWELL_MS
} from "./constants.js";
import { getChildrenField } from "../shared/utils.js";
import { rowIsExpandable } from "../tree/model.js";
import { RowReorderHandleCellRenderer } from "./handle.js";
import {
    buildRowReorderMovePayload,
    collectDraggedRowIds,
    collectLocalRowIds,
    computeNudgeToIndex,
    getLocalRowId,
    getSiblingListForParent,
    getStableRowId,
    isSelfOrDescendantId,
    moveRowBlock,
    remapPathIdsForBlockMove,
    resolveDropTarget,
    resolveReorderContext,
    restoreCrossParentOrders,
    restoreSiblingListOrder
} from "./ops.js";
import {
    applyRowReorderPreviewPlan,
    buildPreviewHitMap,
    clearRowReorderPreview,
    collectPreviewRows,
    planRowReorderPreview,
    previewTargetKey,
    resolveReorderIntent,
    resolveRowReorderExpandId
} from "./preview.js";

const ROW_REORDER_DEFAULTS = {
    enabled: false,
    /** Drag starts on the 6-dot handle in reserved left column (not full-row gutter). */
    handle: "icon",
    /** System column width (px). */
    width: 18,
    gutterWidth: 14,
    allowSummary: false,
    /**
     * `false` | `"siblings"` | `"reparent"`
     * Default `"siblings"` — safe for existing consumers; set `"reparent"` for full tree DnD.
     */
    allowTree: ROW_REORDER_TREE_MODES.SIBLINGS,
    /** Toolbar ↑↓ in preset `rows`. Keep false for tree UIs that only want gutter DnD. */
    toolbarMove: true
};

const TREE_INDENT_PX = 20;
const SCROLL_EDGE_PX = 36;
const SCROLL_STEP_PX = 14;
const DROP_GAP_HEIGHT = 7;

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
        this._rowReorderExpandTimer = 0;
        this._rowReorderExpandHoverId = null;
        this._rowReorderExpandingId = null;
    }

    destroyFeatures() {
        this.destroyRowReorderListeners();
        this.clearRowReorderExpandDwell();
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

    /** Toolbar move arrows (preset `rows`); independent of gutter DnD. */
    isRowReorderToolbarMoveEnabled() {
        return this.isRowReorderEnabled()
            && this.getRowReorderOptions().toolbarMove !== false;
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
        if (typeof this.isFilterActive === "function" && this.isFilterActive()) {
            return true;
        }
        if (this._rowReorderDrag) {
            return true;
        }
        return false;
    }

    /**
     * Dinext sort owns sibling display order — DnD stays for nesting only.
     * AG column sort (`isGridSorted`) still blocks all reorder.
     */
    isRowReorderOrderLocked() {
        return typeof this.isSortActive === "function" && this.isSortActive();
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
        const gutterWidth = this.getRowReorderOptions().gutterWidth ?? 14;
        const rect = rowEl.getBoundingClientRect();
        return clientX - rect.left <= gutterWidth;
    }

    /** Prefer visible handle; fall back to left gutter for legacy CSS-only affordance. */
    isRowReorderHandleHit(event, rowEl) {
        const handle = event?.target?.closest?.(".dinext-table-row-reorder-handle");
        if (handle && rowEl?.contains?.(handle)) {
            return true;
        }
        if (this.getRowReorderOptions().handle === "gutter") {
            return this.isRowReorderGutterHit(rowEl, event?.clientX);
        }
        return false;
    }

    buildColumnDefs() {
        const defs = super.buildColumnDefs() || [];
        if (!this.isRowReorderEnabled()) {
            return defs.filter((col) => (col.colId || col.field) !== ROW_REORDER_COL_ID);
        }

        const filtered = defs.filter((col) => {
            const id = col.colId || col.field;
            if (id !== ROW_REORDER_COL_ID) {
                return true;
            }
            if (!this._rowReorderWarnedConflict) {
                console.warn(
                    `DinextTable: columns must not define colId/field "${ROW_REORDER_COL_ID}" — reserved by rowReorder layer`
                );
                this._rowReorderWarnedConflict = true;
            }
            return false;
        });

        // Own system column — independent of rowCheck (check may be off).
        return [this.buildRowReorderColumnDef(), ...filtered];
    }

    buildRowReorderColumnDef() {
        const opts = this.getRowReorderOptions();
        const width = opts.width ?? 18;
        return {
            colId: ROW_REORDER_COL_ID,
            headerName: "",
            width,
            minWidth: width,
            maxWidth: width,
            pinned: "left",
            sortable: false,
            resizable: false,
            suppressMovable: true,
            editable: false,
            tree: false,
            cellClass: "dinext-table-cell--align-center dinext-table-row-reorder-cell",
            headerClass: "dinext-table-header--align-center dinext-table-row-reorder-header",
            valueGetter: () => null,
            cellRenderer: RowReorderHandleCellRenderer
        };
    }

    shouldApplySelectionToColumn(column) {
        if (column?.getColId?.() === ROW_REORDER_COL_ID) {
            return false;
        }
        return super.shouldApplySelectionToColumn?.(column) ?? true;
    }

    getRowElementFromPoint(clientX, clientY) {
        const stack = typeof document.elementsFromPoint === "function"
            ? document.elementsFromPoint(clientX, clientY)
            : [document.elementFromPoint(clientX, clientY)];
        for (const el of stack) {
            const rowEl = el?.closest?.(".ag-row");
            if (!rowEl || !this.container?.contains(rowEl)) {
                continue;
            }
            if (rowEl.classList.contains("dinext-table-row--reorder-preview-drag")) {
                continue;
            }
            if (rowEl.closest(".ag-floating-bottom, .ag-pinned-left-floating-bottom, .ag-pinned-right-floating-bottom")) {
                return null;
            }
            return rowEl;
        }
        return null;
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
            const label = document.createElement("span");
            label.className = "dinext-table-row-reorder-drop-inside-label";
            label.textContent = __("Inside");
            frame.appendChild(label);
            this.container.appendChild(frame);
            this._rowReorderDropInsideEl = frame;
        }
    }

    autoScrollRowReorderViewport(clientY) {
        const viewport = this.container?.querySelector(".ag-body-viewport");
        if (!viewport) {
            return;
        }
        const rect = viewport.getBoundingClientRect();
        if (clientY < rect.top + SCROLL_EDGE_PX) {
            viewport.scrollTop -= SCROLL_STEP_PX;
        } else if (clientY > rect.bottom - SCROLL_EDGE_PX) {
            viewport.scrollTop += SCROLL_STEP_PX;
        }
    }

    clearRowReorderUi() {
        this.container?.classList.remove(
            "dinext-table--row-reorder-grabbing",
            "dinext-table--row-reorder-gutter-hover",
            "dinext-table--row-reorder-drop-invalid"
        );
        this.hideRowReorderDropVisuals();
        this.clearRowReorderPreview();
        this.container?.querySelectorAll(".ag-row.dinext-table-row--dragging").forEach((el) => {
            el.classList.remove("dinext-table-row--dragging");
        });
    }

    setRowReorderDropInvalid(invalid) {
        this.container?.classList.toggle("dinext-table--row-reorder-drop-invalid", !!invalid);
    }

    bindRowReorderListeners() {
        this.destroyRowReorderListeners();

        this._onRowReorderMouseDown = (event) => {
            if (event.button !== 0 || !this.isRowReorderEnabled()) {
                return;
            }
            const handle = event.target.closest?.(".dinext-table-row-reorder-handle");
            const rowEl = handle?.closest?.(".ag-row") || event.target.closest?.(".ag-row");
            if (!rowEl || !this.container.contains(rowEl)) {
                return;
            }
            if (!this.isRowReorderHandleHit(event, rowEl)) {
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
            this.beginRowReorderDrag(rowNode, rowEl, event);
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

        const el = document.elementFromPoint(event.clientX, event.clientY);
        const handle = el?.closest?.(".dinext-table-row-reorder-handle");
        const rowEl = handle?.closest?.(".ag-row")
            || this.getRowElementFromPoint(event.clientX, event.clientY);
        if (!rowEl || !this.container?.contains(rowEl)) {
            this.container?.classList.remove("dinext-table--row-reorder-gutter-hover");
            return;
        }
        if (!this.isRowReorderHandleHit(
            { target: handle || el, clientX: event.clientX },
            rowEl
        )) {
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

    beginRowReorderDrag(rowNode, rowEl, event) {
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
            previewKey: "",
            startClientX: event?.clientX ?? 0,
            lastClientX: event?.clientX ?? 0,
            lastClientY: event?.clientY ?? 0,
            draggedIds: collectDraggedRowIds(ctx, this.options),
            hitMap: [],
            dragRowEls: this.collectDisplayedRowElementsForBlock(ctx, section)
        };

        // DnD and cell range selection must not run together.
        this.suppressSelectionForRowReorder?.();

        this.container.classList.add("dinext-table--row-reorder-grabbing");
        for (const el of this._rowReorderDrag.dragRowEls) {
            el.classList.add("dinext-table-row--dragging");
        }
        this.refreshRowReorderHitMap();
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
            const safeIndex = typeof CSS !== "undefined" && typeof CSS.escape === "function"
                ? CSS.escape(String(rowIndex))
                : String(rowIndex);
            elements.push(...this.container.querySelectorAll(`.ag-row[row-index="${safeIndex}"]`));
        });

        return elements;
    }

    updateRowReorderDrag(event) {
        const drag = this._rowReorderDrag;
        if (!drag) {
            return;
        }

        this.autoScrollRowReorderViewport(event.clientY);
        drag.lastClientX = event.clientX;
        drag.lastClientY = event.clientY;

        if (!this.isRowReorderPointerInGrid(event.clientX, event.clientY)) {
            this.clearRowReorderExpandDwell();
            this.clearRowReorderDragPreview();
            drag.dropTarget = null;
            this.setRowReorderDropInvalid(true);
            return;
        }

        const allowTree = this.getRowReorderTreeMode();
        const intent = resolveReorderIntent({
            hits: drag.hitMap,
            clientY: event.clientY,
            clientX: event.clientX,
            startClientX: drag.startClientX,
            allowNest: allowTree === ROW_REORDER_TREE_MODES.REPARENT,
            draggedIds: drag.draggedIds
        });
        this.syncRowReorderExpandDwell(intent);
        if (!intent) {
            if (drag.dropTarget) {
                this.setRowReorderDropInvalid(false);
            }
            return;
        }
        if (intent.home) {
            this.restoreRowReorderHome();
            return;
        }

        const dropTarget = resolveDropTarget({
            sourceRows: drag.sourceRows,
            dragCtx: drag.ctx,
            hoverRowId: intent.hoverRowId,
            position: intent.position,
            allowTree,
            orderLocked: this.isRowReorderOrderLocked(),
            options: this.options
        });

        if (dropTarget?.noop) {
            this.restoreRowReorderHome();
            return;
        }

        if (!dropTarget) {
            if (drag.dropTarget) {
                this.setRowReorderDropInvalid(false);
            } else {
                this.setRowReorderDropInvalid(true);
            }
            return;
        }

        drag.dropTarget = dropTarget;
        this.setRowReorderDropInvalid(false);
        this.syncRowReorderPreview(dropTarget);
        this.hideRowReorderDropVisuals();
    }

    isRowReorderPointerInGrid(clientX, clientY) {
        const viewport = this.container?.querySelector(".ag-body-viewport") || this.container;
        if (!viewport) {
            return false;
        }
        const rect = viewport.getBoundingClientRect();
        return clientX >= rect.left
            && clientX <= rect.right
            && clientY >= rect.top
            && clientY <= rect.bottom;
    }

    refreshRowReorderHitMap() {
        const drag = this._rowReorderDrag;
        if (!drag) {
            return;
        }
        const rows = collectPreviewRows(this, drag.section, drag.draggedIds);
        drag.hitMap = buildPreviewHitMap(rows);
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

    showRowReorderDropGap(rowEl, dropTarget, level = 0) {
        const gapEl = this._rowReorderDropGapEl;
        if (!gapEl || !this.container || !dropTarget) {
            return;
        }

        const containerRect = this.container.getBoundingClientRect();
        const rowRect = rowEl.getBoundingClientRect();
        const edge = dropTarget.position === ROW_REORDER_POSITIONS.BEFORE
            ? rowRect.top
            : rowRect.bottom;
        const top = edge - (DROP_GAP_HEIGHT / 2) - containerRect.top + this.container.scrollTop;
        const indent = Math.max(0, Number(level) || 0) * TREE_INDENT_PX;

        gapEl.hidden = false;
        gapEl.style.height = `${DROP_GAP_HEIGHT}px`;
        gapEl.style.top = `${top}px`;
        gapEl.style.left = `${indent}px`;
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

    clearRowReorderPreview() {
        clearRowReorderPreview(this.container);
        if (this._rowReorderDrag) {
            this._rowReorderDrag.previewKey = "";
        }
    }

    clearRowReorderDragPreview() {
        this.hideRowReorderDropVisuals();
        this.clearRowReorderPreview();
    }

    restoreRowReorderHome() {
        const drag = this._rowReorderDrag;
        if (!drag) {
            return;
        }
        this.clearRowReorderDragPreview();
        drag.dropTarget = null;
        this.setRowReorderDropInvalid(false);
    }

    syncRowReorderPreview(dropTarget) {
        const drag = this._rowReorderDrag;
        if (!drag || !dropTarget) {
            return;
        }

        const key = previewTargetKey(dropTarget);
        if (key && key === drag.previewKey) {
            return;
        }

        this.clearRowReorderPreview();
        const rows = collectPreviewRows(this, drag.section, drag.draggedIds);
        const plan = planRowReorderPreview(rows, dropTarget);
        if (!applyRowReorderPreviewPlan(rows, plan)) {
            this.fallbackRowReorderDropVisual(dropTarget);
            return;
        }

        drag.previewKey = key;
    }

    fallbackRowReorderDropVisual(dropTarget) {
        const hoverRowId = dropTarget?.targetRowId;
        if (!hoverRowId || !this.api) {
            return;
        }
        const node = this.api.getRowNode?.(String(hoverRowId));
        const rowIndex = node?.rowIndex;
        if (rowIndex == null) {
            return;
        }
        const hoverRowEl = this.container?.querySelector(`.ag-row[row-index="${rowIndex}"]`);
        if (!hoverRowEl) {
            return;
        }
        if (dropTarget.position === ROW_REORDER_POSITIONS.INSIDE) {
            this.showRowReorderDropInside(hoverRowEl);
        } else {
            this.showRowReorderDropGap(hoverRowEl, dropTarget, node.data?._level || 0);
        }
    }

    finishRowReorderDrag() {
        const drag = this._rowReorderDrag;
        this._rowReorderDrag = null;
        this.clearRowReorderExpandDwell();
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
        // Inner mixins (Sort) re-apply derived sibling order before we rebind rows.
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
        if (this.isRowReorderOrderLocked()) {
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

        // After drop under a collapsed parent — open it so the moved row
        // is visible (lazy: expandRow loads if children still empty).
        // Hover-dwell expand during drag is separate (see scheduleRowReorderExpandDwell).
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

    syncRowReorderExpandDwell(intent) {
        const expandId = resolveRowReorderExpandId({
            intent,
            draggedIds: this._rowReorderDrag?.draggedIds || []
        });
        if (!expandId) {
            this.clearRowReorderExpandDwell();
            return;
        }
        const node = this.api?.getRowNode?.(String(expandId));
        const row = node?.data || this.findSourceRow?.(String(expandId));
        this.scheduleRowReorderExpandDwell(expandId, node || (row ? { data: row } : null));
    }

    clearRowReorderExpandDwell() {
        if (this._rowReorderExpandTimer) {
            clearTimeout(this._rowReorderExpandTimer);
            this._rowReorderExpandTimer = 0;
        }
        this._rowReorderExpandHoverId = null;
    }

    shouldExpandOnRowReorderHover(hoverRowId, hoverNode) {
        if (!hoverRowId || typeof this.expandRow !== "function") {
            return false;
        }
        if (this.isRowExpanded?.(hoverRowId)) {
            return false;
        }
        const row = hoverNode?.data;
        if (!rowIsExpandable(row, getChildrenField(this.options), this.options)) {
            return false;
        }
        const drag = this._rowReorderDrag;
        if (!drag?.ctx) {
            return false;
        }
        const draggedIds = collectDraggedRowIds(drag.ctx, this.options);
        if (draggedIds.includes(hoverRowId)) {
            return false;
        }
        if (draggedIds.some((id) => isSelfOrDescendantId(id, hoverRowId))) {
            return false;
        }
        return true;
    }

    scheduleRowReorderExpandDwell(hoverRowId, hoverNode) {
        if (this._rowReorderExpandHoverId === hoverRowId) {
            return;
        }
        this.clearRowReorderExpandDwell();
        if (!this.shouldExpandOnRowReorderHover(hoverRowId, hoverNode)) {
            return;
        }
        this._rowReorderExpandHoverId = hoverRowId;
        this._rowReorderExpandTimer = setTimeout(() => {
            this._rowReorderExpandTimer = 0;
            const id = this._rowReorderExpandHoverId;
            if (!id || !this._rowReorderDrag) {
                return;
            }
            void this.expandCollapsedRowDuringReorder(id);
        }, ROW_REORDER_EXPAND_DWELL_MS);
    }

    restampRowReorderDragEls() {
        const drag = this._rowReorderDrag;
        if (!drag) {
            return;
        }
        this.container?.classList.add("dinext-table--row-reorder-grabbing");
        drag.dragRowEls = this.collectDisplayedRowElementsForBlock(drag.ctx, drag.section);
        for (const el of drag.dragRowEls) {
            el.classList.add("dinext-table-row--dragging");
        }
    }

    async expandCollapsedRowDuringReorder(rowId) {
        if (!this._rowReorderDrag || this._rowReorderExpandingId === rowId) {
            return;
        }
        if (this.isRowExpanded?.(rowId)) {
            return;
        }
        this._rowReorderExpandingId = rowId;
        try {
            await this.expandRow(rowId);
        } catch (err) {
            console.error("DinextTable: expand during row-reorder failed", err);
            return;
        } finally {
            if (this._rowReorderExpandingId === rowId) {
                this._rowReorderExpandingId = null;
            }
        }
        if (!this._rowReorderDrag) {
            return;
        }
        this.restampRowReorderDragEls();
        this.refreshRowReorderHitMap();
        const drag = this._rowReorderDrag;
        if (drag.lastClientX || drag.lastClientY) {
            this.updateRowReorderDrag({
                clientX: drag.lastClientX,
                clientY: drag.lastClientY
            });
        }
    }

    handleRowReorderBodyScroll() {
        const drag = this._rowReorderDrag;
        if (!drag) {
            return;
        }
        this.clearRowReorderPreview();
        this.refreshRowReorderHitMap();
        if (drag.dropTarget) {
            this.syncRowReorderPreview(drag.dropTarget);
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
                this.clearRowReorderExpandDwell();
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
