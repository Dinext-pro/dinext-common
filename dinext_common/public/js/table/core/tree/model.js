import {
    getChildrenField,
    getMergeGroupMeta,
    getRowIdField,
    isMergeGroupHead
} from "../shared/utils.js";

/** Depth-first walk over leaf columns (skips column groups). Visitor return `true` stops walk. */
export function walkLeafColumns(columns, visitor) {
    if (!Array.isArray(columns)) {
        return false;
    }
    for (const col of columns) {
        if (Array.isArray(col.children) && col.children.length) {
            if (walkLeafColumns(col.children, visitor)) {
                return true;
            }
            continue;
        }
        if (!col?.field) {
            continue;
        }
        if (visitor(col) === true) {
            return true;
        }
    }
    return false;
}

export function getFirstLeafColumn(columns) {
    let first = null;
    walkLeafColumns(columns, (col) => {
        first = col;
        return true;
    });
    return first;
}

export function findRawColumnByField(columns, field) {
    let match = null;
    walkLeafColumns(columns, (col) => {
        if (col.field === field) {
            match = col;
            return true;
        }
    });
    return match;
}

/**
 * Which column field receives indent + chevron.
 * Priority: options.treeColumnField → first `tree: true` → first leaf unless `tree: false`.
 */
export function resolveTreeColumnField(columns, options = {}) {
    const explicitField = options.treeColumnField;
    if (explicitField != null && explicitField !== "") {
        return String(explicitField);
    }

    let markedField = null;
    walkLeafColumns(columns, (col) => {
        if (col.tree === true) {
            markedField = col.field;
            return true;
        }
    });
    if (markedField) {
        return markedField;
    }

    const firstLeaf = getFirstLeafColumn(columns);
    if (firstLeaf?.field && firstLeaf.tree !== false) {
        return firstLeaf.field;
    }
    return null;
}

function rowHasChildren(row, childrenField) {
    const children = row?.[childrenField];
    return Array.isArray(children) && children.length > 0;
}

/** Eager children or lazy marker `hasChildren: true`. Merge tail rows never expand. */
export function rowIsExpandable(row, childrenField, options = {}) {
    const meta = getMergeGroupMeta(row, options);
    if (meta && meta.index !== 0) {
        return false;
    }
    if (row?.hasChildren === true) {
        return true;
    }
    return rowHasChildren(row, childrenField);
}

export function treeHasExpandable(rows, childrenField, options = {}) {
    if (!Array.isArray(rows)) {
        return false;
    }
    for (const row of rows) {
        if (rowIsExpandable(row, childrenField, options)) {
            return true;
        }
        const children = row[childrenField];
        if (Array.isArray(children) && children.length && treeHasExpandable(children, childrenField, options)) {
            return true;
        }
    }
    return false;
}

function walkNestedExpandableIds(children, parentRowId, childrenField, rowIdField, options, ids) {
    for (const child of children) {
        const childRowId = `${parentRowId}:${String(child[rowIdField])}`;
        if (rowIsExpandable(child, childrenField, options)) {
            ids.push(childRowId);
        }
        const nested = child[childrenField];
        if (Array.isArray(nested) && nested.length) {
            walkNestedExpandableIds(nested, childRowId, childrenField, rowIdField, options, ids);
        }
    }
}

/** Depth-first list of expandable row ids (parents before children). */
export function collectExpandableRowIds(sourceRows, options = {}) {
    const ids = [];
    const childrenField = getChildrenField(options);
    const rowIdField = getRowIdField(options);

    if (!Array.isArray(sourceRows)) {
        return ids;
    }

    for (let i = 0; i < sourceRows.length; ) {
        const row = sourceRows[i];
        const meta = getMergeGroupMeta(row, options);

        if (meta && isMergeGroupHead(row, options) && mergeGroupRowsAreValid(sourceRows, i, meta, options)) {
            const headRowId = String(row[rowIdField]);
            if (rowIsExpandable(row, childrenField, options)) {
                ids.push(headRowId);
            }
            const children = row[childrenField];
            if (Array.isArray(children) && children.length) {
                walkNestedExpandableIds(children, headRowId, childrenField, rowIdField, options, ids);
            }
            i += meta.size;
            continue;
        }

        if (meta && meta.index > 0) {
            i += 1;
            continue;
        }

        const rowId = String(row[rowIdField]);
        if (rowIsExpandable(row, childrenField, options)) {
            ids.push(rowId);
        }
        const children = row[childrenField];
        if (Array.isArray(children) && children.length) {
            walkNestedExpandableIds(children, rowId, childrenField, rowIdField, options, ids);
        }
        i += 1;
    }

    return ids;
}

function mergeGroupRowsAreValid(sourceRows, startIndex, meta, options) {
    for (let j = 0; j < meta.size; j++) {
        const groupRow = sourceRows[startIndex + j];
        const groupMeta = getMergeGroupMeta(groupRow, options);
        if (!groupMeta || groupMeta.id !== meta.id || groupMeta.index !== j) {
            return false;
        }
    }
    return true;
}

function makeVisibleRow(row, rowId, level, parentRowId, childrenField, options = {}) {
    const expandable = rowIsExpandable(row, childrenField, options);
    return {
        ...row,
        _rowId: rowId,
        _level: level,
        _hasChildren: expandable,
        _parentRowId: parentRowId || undefined
    };
}

export function flattenExpandedChildren(parentRow, parentRowId, parentLevel, expandedIds, options) {
    const childrenField = getChildrenField(options);
    const rowIdField = getRowIdField(options);
    const rows = [];

    for (const child of parentRow[childrenField] || []) {
        const childLocalId = String(child[rowIdField]);
        const childRowId = `${parentRowId}:${childLocalId}`;
        const childLevel = parentLevel + 1;
        const visibleChild = makeVisibleRow(child, childRowId, childLevel, parentRowId, childrenField, options);
        rows.push(visibleChild);

        if (visibleChild._hasChildren && expandedIds.has(childRowId)) {
            rows.push(...flattenExpandedChildren(child, childRowId, childLevel, expandedIds, options));
        }
    }

    return rows;
}

function walkVisibleRow(row, rowId, level, parentRowId, visible, expandedIds, options) {
    const childrenField = getChildrenField(options);
    visible.push(makeVisibleRow(row, rowId, level, parentRowId, childrenField, options));

    if (!rowIsExpandable(row, childrenField, options) || !expandedIds.has(rowId)) {
        return;
    }

    visible.push(...flattenExpandedChildren(row, rowId, level, expandedIds, options));
}

function walkVisibleMergeGroup(sourceRows, startIndex, visible, expandedIds, options) {
    const rowIdField = getRowIdField(options);
    const childrenField = getChildrenField(options);
    const headRow = sourceRows[startIndex];
    const meta = getMergeGroupMeta(headRow, options);
    const headRowId = String(headRow[rowIdField]);

    for (let j = 0; j < meta.size; j++) {
        const groupRow = sourceRows[startIndex + j];
        visible.push(makeVisibleRow(
            groupRow,
            String(groupRow[rowIdField]),
            0,
            null,
            childrenField,
            options
        ));
    }

    if (rowIsExpandable(headRow, childrenField, options) && expandedIds.has(headRowId)) {
        visible.push(...flattenExpandedChildren(headRow, headRowId, 0, expandedIds, options));
    }
}

function normalizeExpandedIds(expandedIds) {
    if (expandedIds instanceof Set) return expandedIds;
    if (Array.isArray(expandedIds)) return new Set(expandedIds.map((id) => String(id)));
    return new Set();
}

export function toVisibleRows(sourceRows, expandedIds, options = {}) {
    const ids = normalizeExpandedIds(expandedIds);
    const rowIdField = getRowIdField(options);
    const visible = [];

    for (let i = 0; i < sourceRows.length; ) {
        const row = sourceRows[i];
        const meta = getMergeGroupMeta(row, options);

        if (meta && isMergeGroupHead(row, options) && mergeGroupRowsAreValid(sourceRows, i, meta, options)) {
            walkVisibleMergeGroup(sourceRows, i, visible, ids, options);
            i += meta.size;
            continue;
        }

        if (meta && meta.index > 0) {
            i += 1;
            continue;
        }

        walkVisibleRow(
            row,
            String(row[rowIdField]),
            0,
            null,
            visible,
            ids,
            options
        );
        i += 1;
    }

    return visible;
}

export function findSourceRowInData(sourceRows, rowId, options = {}) {
    rowId = String(rowId);
    const parts = rowId.split(":");
    const rowIdField = getRowIdField(options);
    const childrenField = getChildrenField(options);

    let rows = sourceRows;
    let row = null;

    for (let i = 0; i < parts.length; i++) {
        row = rows.find((item) => String(item[rowIdField]) === parts[i]);
        if (!row) {
            return null;
        }
        if (i < parts.length - 1) {
            rows = row[childrenField] || [];
        }
    }

    return row;
}
