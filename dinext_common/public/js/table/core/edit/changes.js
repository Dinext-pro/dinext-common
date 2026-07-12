import { getRowSection } from "../section/sections.js";

/** @layer edit — batch cell mutation sources (onValidateCells / onSaveCells). */
export const CELL_CHANGE_SOURCES = {
    EDIT: "edit",
    PASTE: "paste",
    FILL_DOWN: "fillDown",
    FILL_HANDLE: "fillHandle",
    CLEAR: "clear",
    UNDO: "undo",
    REDO: "redo"
};

/**
 * @param {Array<{ rowId?: string, rowIndex?: number, colId?: string, colIndex?: number, field?: string, oldValue?: unknown, newValue?: unknown, row?: object }>} changes
 */
export function computeRangeFromChanges(changes) {
    if (!Array.isArray(changes) || !changes.length) {
        return null;
    }

    let minRowIndex = Infinity;
    let maxRowIndex = -Infinity;
    let minColIndex = Infinity;
    let maxColIndex = -Infinity;
    let startRowId;
    let endRowId;
    let startColId;
    let endColId;

    for (const change of changes) {
        if (change.rowIndex != null) {
            minRowIndex = Math.min(minRowIndex, change.rowIndex);
            maxRowIndex = Math.max(maxRowIndex, change.rowIndex);
        }
        if (change.colIndex != null && change.colIndex >= 0) {
            minColIndex = Math.min(minColIndex, change.colIndex);
            maxColIndex = Math.max(maxColIndex, change.colIndex);
        }
        if (change.rowId != null) {
            startRowId = startRowId == null ? change.rowId : startRowId;
            endRowId = change.rowId;
        }
        if (change.colId != null) {
            startColId = startColId == null ? change.colId : startColId;
            endColId = change.colId;
        }
    }

    const range = {
        startRowId,
        endRowId,
        startColId,
        endColId
    };

    if (Number.isFinite(minRowIndex)) {
        range.minRowIndex = minRowIndex;
        range.maxRowIndex = maxRowIndex;
    }
    if (Number.isFinite(minColIndex)) {
        range.minColIndex = minColIndex;
        range.maxColIndex = maxColIndex;
    }

    return range;
}

/** Public callback payload item — no grid node handles. */
export function toPublicCellChange(change) {
    return {
        rowId: change.rowId,
        rowIndex: change.rowIndex,
        colId: change.colId,
        field: change.field,
        oldValue: change.oldValue,
        newValue: change.newValue,
        row: change.row,
        section: change.section ?? getRowSection(change.row)
    };
}

export function toPublicCellChanges(changes) {
    return (changes || []).map(toPublicCellChange);
}
