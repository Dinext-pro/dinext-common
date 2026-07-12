import { findSourceRowInData } from "../tree/model.js";
import {
    getChildrenField,
    getMergeGroupMeta,
    getRowIdField
} from "../shared/utils.js";

export function getStableRowId(row, options = {}) {
    if (row?._rowId !== undefined) {
        return String(row._rowId);
    }
    return String(row?.[getRowIdField(options)]);
}

export function getLocalRowId(row, options = {}) {
    return String(row?.[getRowIdField(options)]);
}

/** Mutable sibling array + parent path id (`null` = top-level body list). */
export function resolveSiblingContainer(sourceRows, rowId, options = {}) {
    if (!Array.isArray(sourceRows)) {
        return null;
    }

    const parts = String(rowId).split(":");
    if (parts.length === 1) {
        return { list: sourceRows, parentRowId: null };
    }

    const parentRowId = parts.slice(0, -1).join(":");
    const parent = findSourceRowInData(sourceRows, parentRowId, options);
    if (!parent) {
        return null;
    }

    const childrenField = getChildrenField(options);
    if (!Array.isArray(parent[childrenField])) {
        parent[childrenField] = [];
    }

    return { list: parent[childrenField], parentRowId };
}

export function findIndexInSiblingList(list, rowId, options = {}) {
    if (!Array.isArray(list)) {
        return -1;
    }
    const localId = String(rowId).split(":").pop();
    const rowIdField = getRowIdField(options);
    return list.findIndex((row) => String(row[rowIdField]) === localId);
}

/** Merge tail rows cannot be dragged alone; head moves the whole block. */
export function resolveMergeBlock(list, index, options = {}) {
    const row = list[index];
    if (!row) {
        return { blocked: true };
    }

    const meta = getMergeGroupMeta(row, options);
    if (!meta) {
        return { blockStart: index, blockSize: 1 };
    }
    if (meta.index !== 0) {
        return { blocked: true };
    }
    return { blockStart: index, blockSize: meta.size };
}

export function resolveReorderContext(sourceRows, rowId, options = {}) {
    const container = resolveSiblingContainer(sourceRows, rowId, options);
    if (!container) {
        return null;
    }

    const index = findIndexInSiblingList(container.list, rowId, options);
    if (index < 0) {
        return null;
    }

    const block = resolveMergeBlock(container.list, index, options);
    if (block.blocked) {
        return null;
    }

    return {
        list: container.list,
        parentRowId: container.parentRowId,
        index: block.blockStart,
        blockSize: block.blockSize,
        rowId: String(rowId)
    };
}

export function collectLocalRowIds(list, options = {}) {
    return (list || []).map((row) => getLocalRowId(row, options));
}

export function collectFullRowIds(list, parentRowId, options = {}) {
    return (list || []).map((row) => {
        const localId = getLocalRowId(row, options);
        return parentRowId ? `${parentRowId}:${localId}` : localId;
    });
}

/**
 * @param {object} dragCtx — resolveReorderContext result
 * @param {object} hoverCtx — resolveReorderContext for hover row
 * @param {boolean} insertBefore — drop above hover block midpoint
 */
export function computeTargetInsertIndex(dragCtx, hoverCtx, insertBefore) {
    if (!dragCtx || !hoverCtx) {
        return null;
    }
    if (dragCtx.parentRowId !== hoverCtx.parentRowId) {
        return null;
    }

    let targetIndex = insertBefore ? hoverCtx.index : hoverCtx.index + hoverCtx.blockSize;
    const fromIndex = dragCtx.index;
    const blockSize = dragCtx.blockSize;

    if (fromIndex < targetIndex) {
        targetIndex -= blockSize;
    }

    if (targetIndex === fromIndex) {
        return null;
    }

    return targetIndex;
}

export function reorderSiblingBlock(list, fromIndex, blockSize, toIndex) {
    if (!Array.isArray(list) || blockSize < 1) {
        return false;
    }
    if (fromIndex < 0 || fromIndex + blockSize > list.length) {
        return false;
    }
    if (toIndex < 0 || toIndex > list.length) {
        return false;
    }
    if (toIndex >= fromIndex && toIndex < fromIndex + blockSize) {
        return false;
    }

    const block = list.splice(fromIndex, blockSize);
    let insertAt = toIndex;
    if (fromIndex < toIndex) {
        insertAt -= blockSize;
    }
    list.splice(insertAt, 0, ...block);
    return true;
}

export function restoreSiblingListOrder(list, orderedLocalIds, options = {}) {
    if (!Array.isArray(list) || !Array.isArray(orderedLocalIds)) {
        return false;
    }

    const rowIdField = getRowIdField(options);
    const byId = new Map(list.map((row) => [String(row[rowIdField]), row]));
    const reordered = [];

    for (const id of orderedLocalIds) {
        const row = byId.get(String(id));
        if (row) {
            reordered.push(row);
            byId.delete(String(id));
        }
    }

    for (const row of byId.values()) {
        reordered.push(row);
    }

    list.splice(0, list.length, ...reordered);
    return true;
}

export function buildRowReorderMovePayload({
    section,
    parentRowId,
    rowId,
    fromIndex,
    toIndex,
    blockSize,
    list,
    options = {}
}) {
    const orderedLocalRowIds = collectLocalRowIds(list, options);
    const orderedRowIds = collectFullRowIds(list, parentRowId, options);

    return {
        section,
        parentRowId,
        rowId,
        fromIndex,
        toIndex,
        blockSize,
        orderedLocalRowIds,
        orderedRowIds,
        rows: list.map((row) => ({ ...row }))
    };
}
