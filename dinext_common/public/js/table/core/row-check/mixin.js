import { createMergeGroupSpanRows } from "../shared/utils.js";
import { TABLE_SECTIONS } from "../section/sections.js";
import { TOOLBAR_ICON_SVG } from "../toolbar/icons.js";
import { ROW_REORDER_COL_ID } from "../row-reorder/constants.js";
import { ROW_CHECK_COL_ID, ROW_CHECK_SOURCES, ROW_CHECK_UNITS } from "./constants.js";
import { remapPathIdsForBlockMove } from "../row-reorder/ops.js";
import {
    cloneRowTree,
    collectCheckableRowIds,
    getStableRowId,
    insertRowsAfter,
    isPlainRowData,
    isRowCheckable,
    pruneCheckedIds,
    removeCheckedRowsFromSource,
    replaceArrayContents,
    resolveCheckedRows,
    resolveSelectAllState
} from "./model.js";

const ROW_CHECK_DEFAULTS = {
    enabled: false,
    unit: ROW_CHECK_UNITS.ROW,
    allowSummary: false,
    /** Toolbar select-all icon control (not column header — keeps header slot empty). */
    selectAll: true,
    width: 36
};

function createCheckboxInput({ checked, indeterminate, disabled, onChange }) {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.className = "dinext-table-row-check-input";
    input.checked = !!checked;
    input.indeterminate = !!indeterminate;
    input.disabled = !!disabled;
    input.tabIndex = -1;
    input.addEventListener("click", (event) => event.stopPropagation());
    input.addEventListener("mousedown", (event) => event.stopPropagation());
    input.addEventListener("change", (event) => {
        event.stopPropagation();
        onChange?.(!!input.checked, event);
    });
    return input;
}

/**
 * Class renderer keeps checkbox DOM across refreshCells(force) — avoids remount blink.
 * Checked state is external (Set), so valueGetter is always null and force refresh is required.
 */
class RowCheckCellRenderer {
    init(params) {
        this.table = params.table || params.context?.dinextTable;
        this.eGui = document.createElement("div");
        this.eGui.className = "dinext-table-row-check-cell-inner";
        this.input = null;
        this.sync(params);
    }

    getGui() {
        return this.eGui;
    }

    refresh(params) {
        this.sync(params);
        return true;
    }

    destroy() {
        this.input = null;
        this.eGui = null;
        this.table = null;
    }

    sync(params) {
        const table = this.table;
        const row = params?.data;
        const checkable = !!table?.isRowCheckable?.(row);

        if (!checkable) {
            this.eGui.replaceChildren();
            this.input = null;
            this._boundRowId = null;
            return;
        }

        const rowId = table.getRowCheckId(row);
        const checked = table.isRowChecked(rowId);
        if (!this.input) {
            this.input = createCheckboxInput({
                checked,
                onChange: (value) => table.toggleRowCheck(rowId, value)
            });
            this.eGui.appendChild(this.input);
            this._boundRowId = rowId;
            return;
        }
        if (this._boundRowId !== rowId) {
            this.input.remove();
            this.input = createCheckboxInput({
                checked,
                onChange: (value) => table.toggleRowCheck(rowId, value)
            });
            this.eGui.appendChild(this.input);
            this._boundRowId = rowId;
            return;
        }
        if (this.input.checked !== checked) {
            this.input.checked = checked;
        }
    }
}

/**
 * Row checkbox selection layer (independent of cell range `selection`).
 * Injects reserved column {@link ROW_CHECK_COL_ID}; state lives in a Set of row ids.
 *
 * Mutations share one pipeline: optional validate (`false` rejects) → optimistic
 * source mutate → grid sync → persist hook (`false`/throw reverts) → undo command.
 */
export const RowCheckMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._checkedRowIds = new Set();
        this._rowCheckWarnedConflict = false;
    }

    getRowCheckOptions() {
        return { ...ROW_CHECK_DEFAULTS, ...(this.options.rowCheck || {}) };
    }

    isRowCheckEnabled() {
        return !!this.getRowCheckOptions().enabled;
    }

    /** @layer rowReorder — keep checked ids in sync when path prefix changes. */
    remapRowPathIdsAfterReorder(fromParentRowId, toParentRowId, localIds) {
        if (this._checkedRowIds?.size) {
            remapPathIdsForBlockMove(this._checkedRowIds, {
                fromParentRowId,
                toParentRowId,
                localIds
            });
        }
        super.remapRowPathIdsAfterReorder?.(fromParentRowId, toParentRowId, localIds);
    }

    /**
     * Auto-injected into toolbar when rowCheck is on (leading select/deselect icon control).
     * Hidden when `rowCheck.selectAll === false`.
     */
    getRowCheckToolbarItems() {
        if (!this.isRowCheckEnabled() || this.getRowCheckOptions().selectAll === false) {
            return [];
        }

        const getState = (instance) => resolveSelectAllState(
            instance.collectCheckableRowIds(),
            instance.getCheckedRowIds()
        );

        return [{
            id: "select-all-rows",
            title: ({ table }) => (
                getState(table) === "checked" ? "Clear selection" : "Select all rows"
            ),
            iconSvg: ({ table }) => (
                getState(table) === "checked"
                    ? TOOLBAR_ICON_SVG.selectNone
                    : TOOLBAR_ICON_SVG.selectAll
            ),
            onClick: ({ table }) => {
                table.setAllRowsChecked(getState(table) !== "checked");
            }
        }];
    }

    getRowCheckUnit() {
        return this.getRowCheckOptions().unit === ROW_CHECK_UNITS.MERGE_HEAD
            ? ROW_CHECK_UNITS.MERGE_HEAD
            : ROW_CHECK_UNITS.ROW;
    }

    getRowCheckGuardOpts() {
        return {
            unit: this.getRowCheckUnit(),
            allowSummary: !!this.getRowCheckOptions().allowSummary
        };
    }

    getRowCheckId(row) {
        const rowId = getStableRowId(row, this.options);
        if (
            this.getRowCheckUnit() === ROW_CHECK_UNITS.MERGE_HEAD
            && typeof this.resolveProjectedSourceRowId === "function"
        ) {
            return this.resolveProjectedSourceRowId(rowId, { includeLeaf: true });
        }
        return rowId;
    }

    isRowCheckable(row) {
        if (!this.isRowCheckEnabled() || !row) {
            return false;
        }
        if (!isRowCheckable(row, this.options, this.getRowCheckGuardOpts())) {
            return false;
        }
        const canCheckRow = this.options.canCheckRow;
        if (typeof canCheckRow !== "function") {
            return true;
        }
        const rowId = this.getRowCheckId(row);
        const section = row._section === TABLE_SECTIONS.SUMMARY
            ? TABLE_SECTIONS.SUMMARY
            : TABLE_SECTIONS.BODY;
        return canCheckRow({ table: this, row, rowId, section }) !== false;
    }

    getCheckedRowIds() {
        return [...this._checkedRowIds];
    }

    getCheckedRows() {
        const body = resolveCheckedRows(
            this.sourceData || [],
            this._checkedRowIds,
            this.options
        );
        if (!this.getRowCheckOptions().allowSummary) {
            return body;
        }
        return [
            ...body,
            ...resolveCheckedRows(
                this.summarySourceData || [],
                this._checkedRowIds,
                this.options
            )
        ];
    }

    isRowChecked(rowOrId) {
        const id = typeof rowOrId === "string" || typeof rowOrId === "number"
            ? String(rowOrId)
            : this.getRowCheckId(rowOrId);
        return this._checkedRowIds.has(id);
    }

    applyRowCheckSelectionUi({ silent = false } = {}) {
        this.refreshRowCheckCells();
        if (!silent) {
            this.emitRowCheckChange();
        }
        this.refreshToolbar();
    }

    setCheckedRowIds(ids, { silent = false } = {}) {
        this._checkedRowIds = new Set((ids || []).map(String));
        this.pruneRowCheckState({ silent: true });
        this.applyRowCheckSelectionUi({ silent });
    }

    clearRowCheck({ silent = false } = {}) {
        if (!this._checkedRowIds.size) {
            return;
        }
        this._checkedRowIds.clear();
        this.applyRowCheckSelectionUi({ silent });
    }

    toggleRowCheck(rowId, checked) {
        if (!this.isRowCheckEnabled() || rowId == null) {
            return;
        }
        const id = String(rowId);
        const row = this.findSourceRow?.(id);
        if (row && !this.isRowCheckable(row)) {
            return;
        }

        const next = checked != null ? !!checked : !this._checkedRowIds.has(id);
        if (next) {
            this._checkedRowIds.add(id);
        } else {
            this._checkedRowIds.delete(id);
        }
        this.applyRowCheckSelectionUi();
    }

    setAllRowsChecked(checked) {
        if (!this.isRowCheckEnabled()) {
            return;
        }
        const ids = this.collectCheckableRowIds();
        if (checked) {
            for (const id of ids) {
                this._checkedRowIds.add(id);
            }
        } else {
            for (const id of ids) {
                this._checkedRowIds.delete(id);
            }
        }
        this.applyRowCheckSelectionUi();
    }

    collectCheckableRowIds() {
        const opts = this.getRowCheckGuardOpts();
        const passCanCheck = (id) => {
            const row = this.findSourceRow?.(id);
            if (!row) {
                return false;
            }
            return this.isRowCheckable(row);
        };

        const bodyIds = collectCheckableRowIds(this.sourceData || [], this.options, opts)
            .filter(passCanCheck);
        if (!opts.allowSummary) {
            return bodyIds;
        }
        const summaryIds = collectCheckableRowIds(
            this.summarySourceData || [],
            this.options,
            opts
        ).filter(passCanCheck);
        return [...bodyIds, ...summaryIds];
    }

    pruneRowCheckState({ silent = false } = {}) {
        if (!this._checkedRowIds.size) {
            return false;
        }
        const before = this._checkedRowIds.size;
        const bodyAlive = pruneCheckedIds(
            this._checkedRowIds,
            this.sourceData || [],
            this.options
        );
        const summaryAlive = this.getRowCheckOptions().allowSummary
            ? pruneCheckedIds(
                this._checkedRowIds,
                this.summarySourceData || [],
                this.options
            )
            : [];
        const alive = new Set([...bodyAlive, ...summaryAlive]);
        for (const id of [...this._checkedRowIds]) {
            if (!alive.has(id)) {
                this._checkedRowIds.delete(id);
            }
        }
        const changed = this._checkedRowIds.size !== before;
        if (changed && !silent) {
            this.emitRowCheckChange();
        }
        return changed;
    }

    emitRowCheckChange() {
        const onRowCheckChange = this.options.onRowCheckChange;
        if (typeof onRowCheckChange !== "function") {
            return;
        }
        onRowCheckChange({
            table: this,
            source: ROW_CHECK_SOURCES.CHECK,
            selectedRowIds: this.getCheckedRowIds(),
            selectedRows: this.getCheckedRows()
        });
    }

    refreshRowCheckCells() {
        if (!this.api || !this.isRowCheckEnabled()) {
            return;
        }
        // force: valueGetter is always null (state in Set). suppressFlash: avoid edit-flash
        // from grid-wide enableCellChangeFlash on this system column.
        this.api.refreshCells?.({
            columns: [ROW_CHECK_COL_ID],
            force: true,
            suppressFlash: true
        });
    }

    syncRowCheckGrid({ syncSummary = false } = {}) {
        this.options.data = this.sourceData;
        this.syncVisibleRows?.();
        this.setGridOption("rowData", [...(this.rowData || [])]);
        if (syncSummary && typeof this.syncSummarySection === "function") {
            this.syncSummarySection();
        }
        // rowData replace remounts cells; no force refresh (that was flashing all checks).
        this.refreshToolbar();
    }

    restoreRowCheckSnapshot({ body, summary, checked, syncSummary }) {
        replaceArrayContents(this.sourceData, body);
        if (syncSummary && summary != null) {
            replaceArrayContents(this.summarySourceData, summary);
        }
        this._checkedRowIds = new Set(checked);
        this.syncRowCheckGrid({ syncSummary });
        this.emitRowCheckChange();
    }

    recordRowCheckUndo({ beforeBody, afterBody, beforeSummary, afterSummary, beforeChecked, afterChecked, syncSummary }) {
        if (typeof this.pushUndoCommand !== "function") {
            return;
        }
        this.pushUndoCommand({
            undo: () => {
                this.restoreRowCheckSnapshot({
                    body: beforeBody,
                    summary: beforeSummary,
                    checked: beforeChecked,
                    syncSummary
                });
            },
            execute: () => {
                this.restoreRowCheckSnapshot({
                    body: afterBody,
                    summary: afterSummary,
                    checked: afterChecked,
                    syncSummary
                });
            }
        });
    }

    shouldApplySelectionToColumn(column) {
        if (column?.getColId?.() === ROW_CHECK_COL_ID) {
            return false;
        }
        return super.shouldApplySelectionToColumn?.(column) ?? true;
    }

    buildColumnDefs() {
        const defs = super.buildColumnDefs() || [];
        if (!this.isRowCheckEnabled()) {
            return defs;
        }

        const filtered = defs.filter((col) => {
            const id = col.colId || col.field;
            if (id !== ROW_CHECK_COL_ID) {
                return true;
            }
            if (!this._rowCheckWarnedConflict) {
                console.warn(
                    `DinextTable: columns must not define colId/field "${ROW_CHECK_COL_ID}" — reserved by rowCheck layer`
                );
                this._rowCheckWarnedConflict = true;
            }
            return false;
        });

        const checkCol = this.buildRowCheckColumnDef();
        // Keep order: [rowReorder?, rowCheck, ...domain] — handle never inside checkbox.
        const reorderIdx = filtered.findIndex(
            (col) => (col.colId || col.field) === ROW_REORDER_COL_ID
        );
        if (reorderIdx >= 0) {
            return [
                ...filtered.slice(0, reorderIdx + 1),
                checkCol,
                ...filtered.slice(reorderIdx + 1)
            ];
        }
        return [checkCol, ...filtered];
    }

    buildRowCheckColumnDef() {
        const opts = this.getRowCheckOptions();
        const width = opts.width ?? 36;
        const table = this;
        const colDef = {
            colId: ROW_CHECK_COL_ID,
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
            cellClass: "dinext-table-cell--align-center dinext-table-row-check-cell",
            headerClass: "dinext-table-header--align-center dinext-table-row-check-header",
            valueGetter: () => null,
            cellRenderer: RowCheckCellRenderer,
            cellRendererParams: { table }
        };

        if (this.getRowCheckUnit() === ROW_CHECK_UNITS.MERGE_HEAD) {
            colDef.spanRows = createMergeGroupSpanRows(this.options);
        }

        return colDef;
    }

    refresh(data) {
        super.refresh?.(data);
        if (!this.isRowCheckEnabled()) {
            return;
        }
        this.pruneRowCheckState();
        // Data refresh already remounts/repaints rows; only toolbar select-all state.
        this.refreshToolbar();
    }

    afterGridCreated() {
        super.afterGridCreated();
        if (this.isRowCheckEnabled()) {
            this.container?.classList.add("dinext-table--row-check-enabled");
        }
    }

    destroyFeatures() {
        this.container?.classList.remove("dinext-table--row-check-enabled");
        this._checkedRowIds?.clear();
        super.destroyFeatures();
    }

    handleSetOption(key, value) {
        if (key !== "rowCheck") {
            return super.handleSetOption?.(key, value) ?? false;
        }
        this.options.rowCheck = value;
        const enabled = this.isRowCheckEnabled();
        this.container?.classList.toggle("dinext-table--row-check-enabled", enabled);
        this.setGridOption("columnDefs", this.buildColumnDefs());
        if (enabled && this.getRowCheckUnit() === ROW_CHECK_UNITS.MERGE_HEAD) {
            this.setGridOption("enableCellSpan", true);
        }
        this.pruneRowCheckState();
        this.refreshRowCheckCells();
        this.refreshToolbar();
        return true;
    }

    buildRowCheckGridOptions() {
        if (!this.isRowCheckEnabled()) {
            return {};
        }
        if (this.getRowCheckUnit() === ROW_CHECK_UNITS.MERGE_HEAD) {
            return { enableCellSpan: true };
        }
        return {};
    }

    hasRowCheckAddHook() {
        return typeof this.options.onAddRow === "function";
    }

    hasRowCheckDuplicateHook() {
        return typeof this.options.onDuplicateRows === "function";
    }

    /**
     * Factory hook must return a plain row object. Core inserts at end of body.
     */
    async addRow() {
        if (!this.isRowCheckEnabled() || !this.hasRowCheckAddHook()) {
            return false;
        }

        const row = await Promise.resolve(this.options.onAddRow({
            table: this,
            source: ROW_CHECK_SOURCES.ADD
        }));
        if (!isPlainRowData(row)) {
            return false;
        }

        if (!Array.isArray(this.sourceData)) {
            this.sourceData = [];
        }

        const beforeBody = cloneRowTree(this.sourceData);
        const beforeChecked = this.getCheckedRowIds();

        insertRowsAfter(this.sourceData, null, [row], this.options);
        const newId = getStableRowId(row, this.options);
        this._checkedRowIds.add(newId);
        this.syncRowCheckGrid();
        this.emitRowCheckChange();

        this.recordRowCheckUndo({
            beforeBody,
            afterBody: cloneRowTree(this.sourceData),
            beforeSummary: null,
            afterSummary: null,
            beforeChecked,
            afterChecked: this.getCheckedRowIds(),
            syncSummary: false
        });
        return true;
    }

    async deleteCheckedRows() {
        if (!this.isRowCheckEnabled()) {
            return false;
        }

        const rowIds = this.getCheckedRowIds();
        const rows = this.getCheckedRows();
        if (!rowIds.length) {
            return false;
        }

        const ctx = {
            table: this,
            source: ROW_CHECK_SOURCES.DELETE,
            rowIds,
            rows
        };

        if (this.options.onValidateDeleteRows?.(ctx) === false) {
            return false;
        }

        if (typeof this.options.onBeforeDeleteRows === "function") {
            try {
                const beforeOk = await Promise.resolve(this.options.onBeforeDeleteRows(ctx));
                if (beforeOk === false) {
                    return false;
                }
            } catch (err) {
                console.error("DinextTable: onBeforeDeleteRows failed", err);
                return false;
            }
        }

        const allowSummary = !!this.getRowCheckOptions().allowSummary;
        if (allowSummary && !Array.isArray(this.summarySourceData)) {
            this.summarySourceData = [];
        }
        if (!Array.isArray(this.sourceData)) {
            this.sourceData = [];
        }

        const beforeBody = cloneRowTree(this.sourceData);
        const beforeSummary = allowSummary ? cloneRowTree(this.summarySourceData) : null;
        const beforeChecked = [...rowIds];

        const bodyResult = removeCheckedRowsFromSource(this.sourceData, rowIds, this.options);
        const summaryResult = allowSummary
            ? removeCheckedRowsFromSource(this.summarySourceData, rowIds, this.options)
            : { ok: false };

        if (!bodyResult.ok && !summaryResult.ok) {
            return false;
        }

        this._checkedRowIds.clear();
        this.syncRowCheckGrid({ syncSummary: allowSummary && summaryResult.ok });
        this.emitRowCheckChange();

        const afterBody = cloneRowTree(this.sourceData);
        const afterSummary = allowSummary ? cloneRowTree(this.summarySourceData) : null;

        const revert = () => {
            this.restoreRowCheckSnapshot({
                body: beforeBody,
                summary: beforeSummary,
                checked: beforeChecked,
                syncSummary: allowSummary
            });
        };

        const onDeleteRows = this.options.onDeleteRows;
        if (typeof onDeleteRows === "function") {
            try {
                const result = await Promise.resolve(onDeleteRows(ctx));
                if (result === false) {
                    revert();
                    return false;
                }
            } catch (err) {
                revert();
                console.error("DinextTable: onDeleteRows failed", err);
                return false;
            }
        }

        this.recordRowCheckUndo({
            beforeBody,
            afterBody,
            beforeSummary,
            afterSummary,
            beforeChecked,
            afterChecked: [],
            syncSummary: allowSummary
        });
        return true;
    }

    /**
     * Factory hook must return a non-empty array of plain rows. Core inserts after last checked id.
     */
    async duplicateCheckedRows() {
        if (!this.isRowCheckEnabled() || !this.hasRowCheckDuplicateHook()) {
            return false;
        }

        const rowIds = this.getCheckedRowIds();
        const rows = this.getCheckedRows();
        if (!rowIds.length) {
            return false;
        }

        const ctx = {
            table: this,
            source: ROW_CHECK_SOURCES.DUPLICATE,
            rowIds,
            rows
        };

        if (this.options.onValidateDuplicateRows?.(ctx) === false) {
            return false;
        }

        const newRows = await Promise.resolve(this.options.onDuplicateRows(ctx));
        if (!Array.isArray(newRows) || !newRows.length || !newRows.every(isPlainRowData)) {
            return false;
        }

        if (!Array.isArray(this.sourceData)) {
            this.sourceData = [];
        }

        const beforeBody = cloneRowTree(this.sourceData);
        const beforeChecked = this.getCheckedRowIds();
        const afterId = rowIds[rowIds.length - 1];

        if (!insertRowsAfter(this.sourceData, afterId, newRows, this.options)) {
            return false;
        }

        const newIds = newRows.map((row) => getStableRowId(row, this.options));
        this._checkedRowIds = new Set(newIds);
        this.syncRowCheckGrid();
        this.emitRowCheckChange();

        this.recordRowCheckUndo({
            beforeBody,
            afterBody: cloneRowTree(this.sourceData),
            beforeSummary: null,
            afterSummary: null,
            beforeChecked,
            afterChecked: newIds,
            syncSummary: false
        });
        return true;
    }

    nudgeCheckedRow(direction) {
        if (!this.isRowReorderEnabled?.()) {
            return false;
        }
        const ids = this.getCheckedRowIds();
        if (ids.length !== 1) {
            return false;
        }
        const ok = this.nudgeRowReorder?.(ids[0], direction) ?? false;
        if (ok) {
            this.refreshToolbar();
        }
        return ok;
    }

    canNudgeCheckedRow(direction) {
        if (!this.isRowReorderEnabled?.()) {
            return false;
        }
        const ids = this.getCheckedRowIds();
        if (ids.length !== 1) {
            return false;
        }
        return this.canNudgeRowReorder?.(ids[0], direction) ?? false;
    }
};
