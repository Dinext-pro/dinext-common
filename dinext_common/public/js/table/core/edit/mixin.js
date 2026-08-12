import {
    CELL_CHANGE_SOURCES,
    computeRangeFromChanges,
    toPublicCellChanges
} from "./changes.js";
import {
    isCheckboxColumnDef,
    resolveClickWhenActiveEnabled,
    selectionBlocksClickWhenActive,
    shouldStartEditOnActiveClick
} from "./click-when-active.js";
import { getRowSection } from "../section/sections.js";
import { getRowIdField } from "../shared/utils.js";
import { findSourceRowByBusinessId } from "../tree/model.js";

/** cellClassRules: marks non-editable cells (per colDef.editable / column.edit). */
function isReadOnlyCellClass(params) {
    if (!params.colDef?.field) {
        return false;
    }
    const editable = params.colDef.editable;
    if (typeof editable === "function") {
        return !editable(params);
    }
    return !editable;
}

export const EditMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        // Only previous completed click counts as "active". Never seed from
        // getFocusedCell / cellFocused — AG Grid moves focus before click.
        this._lastClickedCell = null;
    }

    destroyFeatures() {
        this._lastClickedCell = null;
        super.destroyFeatures();
    }

    isClickWhenActiveEnabled() {
        return resolveClickWhenActiveEnabled(this.options, this.columns);
    }

    /** `_rowId` (tree path) when present, else the plain `rowIdField` value (flat). */
    getEditRowId(row) {
        if (!row) {
            return undefined;
        }
        if (row._rowId !== undefined) {
            return String(row._rowId);
        }
        return String(row[getRowIdField(this.options)]);
    }

    /** `findSourceRow` already degrades to a direct top-level lookup for flat data. */
    writeSourceField(rowId, field, value) {
        const row = this.findSourceRow(rowId);
        if (row) {
            row[field] = value;
        }
        return row;
    }

    applyCellValue(node, field, value) {
        node.data[field] = value;
        this.api?.refreshCells({ rowNodes: [node], columns: [field], force: true });
    }

    /** Visible grid node by business id (`rowIdField`), not `_rowId` path. */
    findGridNodeByBusinessId(businessId) {
        if (businessId == null || businessId === "" || !this.api?.forEachNode) {
            return null;
        }
        const id = String(businessId);
        const rowIdField = getRowIdField(this.options);
        let found = null;
        this.api.forEachNode((node) => {
            if (!found && node?.data && String(node.data[rowIdField]) === id) {
                found = node;
            }
        });
        return found;
    }

    /**
     * Apply values already persisted externally (server side-effects).
     * Updates grid copy + sourceData. Does NOT validate or call onSaveCells.
     *
     * Each item: `{ field, value, rowId? }` (tree path / flat id) and/or `{ id }`
     * (business `rowIdField` when path unknown).
     *
     * @returns {number} field writes applied
     */
    applyExternalCellValues(changes) {
        if (!Array.isArray(changes) || !changes.length) {
            return 0;
        }

        let applied = 0;

        for (const change of changes) {
            const field = change?.field;
            if (!field) {
                continue;
            }
            const value = change.value;

            let node = null;
            let rowId = change.rowId != null && change.rowId !== ""
                ? String(change.rowId)
                : null;

            if (rowId) {
                node = this.api?.getRowNode(rowId) || null;
            }
            if (!node && change.id != null && change.id !== "") {
                node = this.findGridNodeByBusinessId(change.id);
                if (node) {
                    rowId = this.getEditRowId(node.data);
                }
            }

            if (node?.data && !Object.is(node.data[field], value)) {
                this.applyCellValue(node, field, value);
                applied += 1;
            }

            if (rowId != null) {
                const sourceRow = this.writeSourceField(rowId, field, value);
                if (sourceRow && !node) {
                    applied += 1;
                }
            } else if (change.id != null && change.id !== "") {
                const sourceRow = findSourceRowByBusinessId(
                    this.sourceData,
                    change.id,
                    this.options
                );
                if (sourceRow && !Object.is(sourceRow[field], value)) {
                    sourceRow[field] = value;
                    applied += 1;
                }
            }
        }

        return applied;
    }

    resolveChangeColMeta(field, colId, columns) {
        if (!columns?.length) {
            return { colId: colId || field, colIndex: undefined };
        }
        if (colId) {
            const colIndex = columns.findIndex((column) => column.getColId() === colId);
            return { colId, colIndex: colIndex >= 0 ? colIndex : undefined };
        }
        const column = columns.find((item) => item.getColDef().field === field);
        if (!column) {
            return { colId: field, colIndex: undefined };
        }
        return {
            colId: column.getColId(),
            colIndex: columns.indexOf(column)
        };
    }

    buildChangeEntry(rawChange, columns) {
        const { node, field, oldValue, newValue } = rawChange;
        const row = node?.data;
        const rowId = this.getEditRowId(row);
        const rowIndex = rawChange.rowIndex ?? node?.rowIndex;
        const colMeta = this.resolveChangeColMeta(field, rawChange.colId, columns);

        return {
            node,
            field,
            oldValue,
            newValue,
            row,
            rowId,
            rowIndex,
            colId: colMeta.colId,
            colIndex: colMeta.colIndex,
            section: getRowSection(row)
        };
    }

    computeRangeFromRawChanges(rawChanges) {
        const columns = this.api?.getAllDisplayedColumns() || [];
        const entries = (rawChanges || []).map((raw) => this.buildChangeEntry(raw, columns));
        return computeRangeFromChanges(entries);
    }

    revertChangeEntries(entries, { gridOnly = false } = {}) {
        for (const change of entries) {
            if (change.node) {
                this.applyCellValue(change.node, change.field, change.oldValue);
            }
            if (!gridOnly && change.rowId != null) {
                this.writeSourceField(change.rowId, change.field, change.oldValue);
            }
        }
    }

    applyChangeEntries(entries, { grid = true, sourceData = true } = {}) {
        for (const change of entries) {
            if (grid && change.node) {
                this.applyCellValue(change.node, change.field, change.newValue);
            }
            if (sourceData && change.rowId != null) {
                this.writeSourceField(change.rowId, change.field, change.newValue);
            }
        }
    }

    /**
     * Unified batch commit: validate → apply grid + sourceData → onSaveCells.
     * @returns {{ applied: number, entries: object[] }}
     */
    commitCellChanges({
        source = CELL_CHANGE_SOURCES.EDIT,
        changes: rawChanges = [],
        range: rangeOverride = null,
        alreadyApplied = false
    }) {
        if (!rawChanges.length) {
            return { applied: 0, entries: [] };
        }

        const columns = this.api?.getAllDisplayedColumns() || [];
        const entries = rawChanges.map((raw) => this.buildChangeEntry(raw, columns));
        const range = rangeOverride || computeRangeFromChanges(entries);
        const publicChanges = toPublicCellChanges(entries);

        const onValidateCells = this.options.onValidateCells;
        if (typeof onValidateCells === "function") {
            const validation = onValidateCells({
                table: this,
                source,
                range,
                changes: publicChanges
            });
            if (validation !== true) {
                if (alreadyApplied) {
                    this.revertChangeEntries(entries, { gridOnly: true });
                }
                return { applied: 0, entries: [] };
            }
        }

        if (!alreadyApplied) {
            this.applyChangeEntries(entries, { grid: true, sourceData: false });
        }
        this.applyChangeEntries(entries, { grid: false, sourceData: true });

        const onSaveCells = this.options.onSaveCells;
        if (typeof onSaveCells === "function") {
            const revertAll = () => {
                this.revertChangeEntries(entries);
            };

            Promise.resolve(onSaveCells({
                table: this,
                source,
                range,
                changes: publicChanges
            }))
                .then((result) => {
                    if (result === false) {
                        revertAll();
                    }
                })
                .catch((err) => {
                    revertAll();
                    console.error("DinextTable: onSaveCells failed", err);
                });
        }

        const appliedCount = entries.length;
        if (appliedCount && source === CELL_CHANGE_SOURCES.EDIT && typeof this.recordCellChangesForUndo === "function") {
            this.recordCellChangesForUndo(entries, range);
        }

        return { applied: appliedCount, entries };
    }

    handleCellValueChanged(event) {
        const field = event.colDef?.field;
        if (!field || !event.node) {
            return;
        }
        this.commitCellChanges({
            source: CELL_CHANGE_SOURCES.EDIT,
            changes: [{
                node: event.node,
                field,
                oldValue: event.oldValue,
                newValue: event.newValue,
                rowIndex: event.node.rowIndex,
                colId: event.column?.getColId?.()
            }],
            alreadyApplied: true
        });
    }

    /** Extension seam for later mixins (navigation/selection); no-op for now. */
    handleCellEditingStopped(event) {}

    handleEditCellClicked(event) {
        if (!this.isClickWhenActiveEnabled() || !this.api) {
            return;
        }

        const domEvent = event.event;
        const column = event.column;
        const node = event.node;
        if (!domEvent || !column || !node || node.rowIndex == null) {
            return;
        }

        if (this.isSelectionBlockedByRowReorder?.(domEvent)) {
            return;
        }

        const colId = column.getColId();
        const colDef = column.getColDef?.() || event.colDef;
        const cellRef = { rowIndex: node.rowIndex, colId };
        const shouldEdit = shouldStartEditOnActiveClick({
            committedFocus: this._lastClickedCell,
            rowIndex: cellRef.rowIndex,
            colId: cellRef.colId,
            domEvent,
            isEditing: !!this.api.getEditingCells?.()?.length,
            isEditable: !!this.isColumnEditableForRow?.(column, node),
            isCheckboxColumn: isCheckboxColumnDef(colDef),
            selectionBlocks: this.isSelectionEnabled?.()
                ? selectionBlocksClickWhenActive(this.cellRanges)
                : false,
            targetIsFillHandle: !!domEvent.target?.closest?.(".dinext-table-fill-handle")
        });

        this._lastClickedCell = cellRef;

        if (!shouldEdit) {
            return;
        }

        this.api.startEditingCell({ rowIndex: cellRef.rowIndex, colKey: cellRef.colId });
    }

    handleCellEditRequest(event) {
        const field = event.colDef?.field;
        if (!field || !event.node) {
            return;
        }
        this.commitCellChanges({
            source: CELL_CHANGE_SOURCES.EDIT,
            changes: [{
                node: event.node,
                field,
                oldValue: event.oldValue,
                newValue: event.newValue,
                rowIndex: event.node.rowIndex,
                colId: event.column?.getColId?.()
            }],
            alreadyApplied: false
        });
    }

    buildEditGridOptions() {
        const gridOptions = {
            undoRedoCellEditing: false,
            stopEditingWhenCellsLoseFocus: true,
            defaultColDef: {
                enableCellChangeFlash: true,
                cellClassRules: {
                    "dinext-table-cell--readonly": isReadOnlyCellClass
                }
            },
            onCellValueChanged: (event) => this.handleCellValueChanged(event),
            onCellEditingStopped: (event) => this.handleCellEditingStopped(event),
            // Always chained; gated by clickWhenActive / edit availability at click time.
            onCellClicked: (event) => this.handleEditCellClicked(event)
        };

        if (this.options.readOnlyEdit) {
            gridOptions.readOnlyEdit = true;
            gridOptions.onCellEditRequest = (event) => this.handleCellEditRequest(event);
        }

        return gridOptions;
    }
};

export { CELL_CHANGE_SOURCES };
