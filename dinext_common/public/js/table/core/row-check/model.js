import {
    getChildrenField,
    getMergeGroupMeta,
    getRowIdField
} from "../shared/utils.js";
import { getStableRowId } from "../row-reorder/ops.js";
import { isSummarySectionRow } from "../section/sections.js";
import { ROW_CHECK_UNITS } from "./constants.js";

export { getStableRowId };

export function isPlainRowData(value) {
    return !!value && typeof value === "object" && !Array.isArray(value);
}

export function cloneRowTree(rows) {
    const source = Array.isArray(rows) ? rows : [];
    if (typeof structuredClone === "function") {
        try {
            return structuredClone(source);
        } catch (_err) {
            // fall through (e.g. non-cloneable values)
        }
    }
    return JSON.parse(JSON.stringify(source));
}

export function replaceArrayContents(target, next) {
    if (!Array.isArray(target)) {
        return;
    }
    target.splice(0, target.length, ...(next || []));
}

/** Path id for a source row (`101` / `101:5`), preferring stamped `_rowId`. */
function resolveSourceRowPathId(row, parentPath, options = {}) {
    if (row?._rowId !== undefined) {
        return String(row._rowId);
    }
    const localId = String(row?.[getRowIdField(options)]);
    return parentPath ? `${parentPath}:${localId}` : localId;
}

/**
 * DFS over source tree.
 * @param {object[]} rows
 * @param {object} options
 * @param {(row: object, id: string, parentPath: string | null) => void} visitor
 */
function walkSourceTree(rows, options, visitor) {
    const childrenField = getChildrenField(options);

    function walk(list, parentPath) {
        for (const row of list || []) {
            const id = resolveSourceRowPathId(row, parentPath, options);
            visitor(row, id, parentPath);
            const children = row?.[childrenField];
            if (Array.isArray(children) && children.length) {
                walk(children, id);
            }
        }
    }

    walk(rows, null);
}

/**
 * Whether a source/displayed row may show a checkbox and enter the checked Set.
 * @param {object} row
 * @param {object} options — table options (mergeGroup, rowIdField, …)
 * @param {{ unit?: string, allowSummary?: boolean }} checkOpts
 */
export function isRowCheckable(row, options = {}, checkOpts = {}) {
    if (!row) {
        return false;
    }
    if (isSummarySectionRow(row) && !checkOpts.allowSummary) {
        return false;
    }

    const unit = checkOpts.unit || ROW_CHECK_UNITS.ROW;
    if (unit === ROW_CHECK_UNITS.MERGE_HEAD) {
        const meta = getMergeGroupMeta(row, options);
        if (meta && meta.index !== 0) {
            return false;
        }
        return true;
    }

    return true;
}

/**
 * DFS over source tree; returns stable path ids of checkable rows.
 */
export function collectCheckableRowIds(rows, options = {}, checkOpts = {}) {
    const ids = [];
    walkSourceTree(rows, options, (row, id) => {
        if (isRowCheckable(row, options, checkOpts)) {
            ids.push(id);
        }
    });
    return ids;
}

export function resolveCheckedRows(rows, checkedIds, options = {}) {
    // Accept Set or array (mixin passes `_checkedRowIds` Set).
    const want = new Set([...(checkedIds || [])].map(String));
    const found = [];
    walkSourceTree(rows, options, (row, id) => {
        if (want.has(id)) {
            found.push(row);
        }
    });
    return found;
}

function collectAllStableRowIds(rows, options = {}) {
    const ids = [];
    walkSourceTree(rows, options, (_row, id) => {
        ids.push(id);
    });
    return ids;
}

/** Drop ids that no longer exist in source trees. */
export function pruneCheckedIds(checkedIds, rows, options = {}) {
    const alive = new Set(collectAllStableRowIds(rows, options));
    return [...checkedIds].filter((id) => alive.has(String(id)));
}

/**
 * Select-all header state.
 * @returns {"checked"|"unchecked"|"indeterminate"}
 */
export function resolveSelectAllState(checkableIds, checkedIds) {
    const checkable = checkableIds || [];
    if (!checkable.length) {
        return "unchecked";
    }
    const checked = new Set([...(checkedIds || [])].map(String));
    let n = 0;
    for (const id of checkable) {
        if (checked.has(String(id))) {
            n += 1;
        }
    }
    if (n === 0) {
        return "unchecked";
    }
    if (n === checkable.length) {
        return "checked";
    }
    return "indeterminate";
}

/**
 * Remove checked rows (and merge blocks) from a mutable sibling list tree.
 * @returns {{ removed: object[], ok: boolean }}
 */
export function removeCheckedRowsFromSource(sourceRows, rowIds, options = {}) {
    if (!Array.isArray(sourceRows) || !rowIds?.length) {
        return { removed: [], ok: false };
    }

    const idSet = new Set(rowIds.map(String));
    const childrenField = getChildrenField(options);
    const removed = [];

    function removeFromList(list, parentPath) {
        if (!Array.isArray(list)) {
            return;
        }
        let i = 0;
        while (i < list.length) {
            const row = list[i];
            const stableId = resolveSourceRowPathId(row, parentPath, options);
            const meta = getMergeGroupMeta(row, options);

            if (idSet.has(stableId)) {
                if (meta && meta.index !== 0) {
                    i += 1;
                    continue;
                }
                const blockSize = meta && meta.index === 0 ? meta.size : 1;
                const block = list.splice(i, blockSize);
                removed.push(...block);
                continue;
            }

            const children = row[childrenField];
            if (Array.isArray(children) && children.length) {
                removeFromList(children, stableId);
            }
            i += 1;
        }
    }

    removeFromList(sourceRows, null);
    return { removed, ok: removed.length > 0 };
}

/**
 * Insert `newRows` into the sibling list immediately after the block of `afterRowId`.
 * `afterRowId == null` → append to top-level. Unknown afterRowId → false (no silent fallback).
 */
export function insertRowsAfter(sourceRows, afterRowId, newRows, options = {}) {
    if (!Array.isArray(sourceRows) || !newRows?.length) {
        return false;
    }

    if (afterRowId == null) {
        sourceRows.push(...newRows);
        return true;
    }

    const childrenField = getChildrenField(options);
    const target = String(afterRowId);

    function findAndInsert(list, parentPath) {
        for (let i = 0; i < list.length; i += 1) {
            const row = list[i];
            const stableId = resolveSourceRowPathId(row, parentPath, options);
            const meta = getMergeGroupMeta(row, options);

            if (stableId === target) {
                const size = meta && meta.index === 0 ? meta.size : 1;
                list.splice(i + size, 0, ...newRows);
                return true;
            }

            const children = row[childrenField];
            if (Array.isArray(children) && children.length) {
                if (findAndInsert(children, stableId)) {
                    return true;
                }
            }
        }
        return false;
    }

    return findAndInsert(sourceRows, null);
}
