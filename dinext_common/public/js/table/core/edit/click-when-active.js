/** True when any leaf column opts into edit (global `edit: false` + per-column edit). */
export function columnsAllowEdit(columns) {
    for (const col of columns || []) {
        if (Array.isArray(col.children) && col.children.length) {
            if (columnsAllowEdit(col.children)) {
                return true;
            }
            continue;
        }
        if (col.edit !== undefined && col.edit !== false) {
            return true;
        }
    }
    return false;
}

/**
 * Default on when global `edit` or any column has `edit` (not `false`).
 * Explicit `clickWhenActive: false|true` wins.
 */
export function resolveClickWhenActiveEnabled(options = {}, columns = []) {
    if (options.clickWhenActive === false) {
        return false;
    }
    if (options.clickWhenActive === true) {
        return true;
    }
    if (options.edit) {
        return true;
    }
    return columnsAllowEdit(columns);
}

export function isCheckboxColumnDef(colDef) {
    if (!colDef) {
        return false;
    }
    if (colDef.cellDataType === "boolean") {
        return true;
    }
    if (colDef.cellEditor === "agCheckboxCellEditor") {
        return true;
    }
    if (colDef.cellRenderer === "agCheckboxCellRenderer") {
        return true;
    }
    const type = colDef.type;
    if (type === "checkbox" || type === "boolean") {
        return true;
    }
    if (Array.isArray(type) && (type.includes("checkbox") || type.includes("boolean"))) {
        return true;
    }
    return false;
}

/** Multi-cell / multi-range selection must not enter edit on click. */
export function selectionBlocksClickWhenActive(ranges) {
    if (!ranges?.length) {
        return false;
    }
    if (ranges.length !== 1) {
        return true;
    }
    const range = ranges[0];
    return range.startRowId !== range.endRowId || range.startColId !== range.endColId;
}

export function sameCellRef(a, b) {
    return !!a && !!b && a.rowIndex === b.rowIndex && a.colId === b.colId;
}

/**
 * Sheets-like: second plain click on the same cell → start edit.
 * `committedFocus` must be the previous *completed click* cell ref
 * (`_lastClickedCell`), never live AG `getFocusedCell()` / `cellFocused`.
 * `detail === 1` skips the second half of a double-click (keeps onCellDoubleClicked).
 */
export function shouldStartEditOnActiveClick({
    committedFocus,
    rowIndex,
    colId,
    domEvent,
    isEditing = false,
    isEditable = false,
    isCheckboxColumn = false,
    selectionBlocks = false,
    targetIsFillHandle = false,
    suppressClickEdit = false
} = {}) {
    if (!domEvent || rowIndex == null || colId == null) {
        return false;
    }
    if (domEvent.button != null && domEvent.button !== 0) {
        return false;
    }
    if (domEvent.detail !== 1) {
        return false;
    }
    if (domEvent.shiftKey || domEvent.ctrlKey || domEvent.metaKey || domEvent.altKey) {
        return false;
    }
    if (
        isEditing
        || !isEditable
        || isCheckboxColumn
        || selectionBlocks
        || targetIsFillHandle
        || suppressClickEdit
    ) {
        return false;
    }
    return sameCellRef(committedFocus, { rowIndex, colId });
}

export function snapshotFocusedCell(api) {
    const focused = api?.getFocusedCell?.();
    if (!focused || focused.rowIndex == null || !focused.column) {
        return null;
    }
    const colId = typeof focused.column.getColId === "function"
        ? focused.column.getColId()
        : focused.column.colId;
    if (colId == null) {
        return null;
    }
    return { rowIndex: focused.rowIndex, colId };
}

export function cellRefFromFocusEvent(event) {
    if (event?.rowIndex == null || !event.column) {
        return null;
    }
    const colId = typeof event.column.getColId === "function"
        ? event.column.getColId()
        : event.column.colId;
    if (colId == null) {
        return null;
    }
    return { rowIndex: event.rowIndex, colId };
}
