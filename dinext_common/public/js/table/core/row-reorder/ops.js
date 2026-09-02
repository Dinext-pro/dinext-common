import { findSourceRowInData } from "../tree/model.js";
import {
    getChildrenField,
    getMergeGroupMeta,
    getRowIdField
} from "../shared/utils.js";
import { ROW_REORDER_POSITIONS, ROW_REORDER_TREE_MODES } from "./constants.js";

/** Index of merge head for a row inside a sibling list; plain rows → same index. */
export function findMergeBlockStartIndex(list, index, options = {}) {
    if (!Array.isArray(list) || index < 0 || index >= list.length) {
        return -1;
    }
    const meta = getMergeGroupMeta(list[index], options);
    if (!meta) {
        return index;
    }
    return index - meta.index;
}

/**
 * Destination `toIndex` for {@link reorderSiblingBlock} — one sibling slot up/down.
 * @param {number} direction — negative = up, positive = down
 * @returns {number|null}
 */
export function computeNudgeToIndex(list, fromIndex, blockSize, direction, options = {}) {
    if (!Array.isArray(list) || blockSize < 1 || fromIndex < 0) {
        return null;
    }

    if (direction < 0) {
        if (fromIndex <= 0) {
            return null;
        }
        const prevStart = findMergeBlockStartIndex(list, fromIndex - 1, options);
        return prevStart < 0 ? null : prevStart;
    }

    if (direction > 0) {
        const nextIndex = fromIndex + blockSize;
        if (nextIndex >= list.length) {
            return null;
        }
        const nextStart = findMergeBlockStartIndex(list, nextIndex, options);
        if (nextStart < 0) {
            return null;
        }
        const nextMeta = getMergeGroupMeta(list[nextStart], options);
        const nextSize = nextMeta ? nextMeta.size : 1;
        return nextStart + nextSize;
    }

    return null;
}

export function getStableRowId(row, options = {}) {
    if (row?._rowId !== undefined) {
        return String(row._rowId);
    }
    return String(row?.[getRowIdField(options)]);
}

export function getLocalRowId(row, options = {}) {
    return String(row?.[getRowIdField(options)]);
}

export function buildFullRowId(parentRowId, localId) {
    const local = String(localId);
    return parentRowId ? `${parentRowId}:${local}` : local;
}

/** True when `candidateId` is `ancestorId` or nested under it. */
export function isSelfOrDescendantId(ancestorId, candidateId) {
    if (ancestorId == null || candidateId == null) {
        return false;
    }
    const ancestor = String(ancestorId);
    const candidate = String(candidateId);
    return candidate === ancestor || candidate.startsWith(`${ancestor}:`);
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

/** Sibling list for a parent id; creates `children` array when missing. */
export function getSiblingListForParent(sourceRows, parentRowId, options = {}) {
    if (!Array.isArray(sourceRows)) {
        return null;
    }
    if (parentRowId == null || parentRowId === "") {
        return sourceRows;
    }

    const parent = findSourceRowInData(sourceRows, parentRowId, options);
    if (!parent) {
        return null;
    }

    const childrenField = getChildrenField(options);
    if (!Array.isArray(parent[childrenField])) {
        parent[childrenField] = [];
    }
    return parent[childrenField];
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

/**
 * Drop anchor for any visible row (merge tails resolve to their block).
 * Unlike {@link resolveReorderContext}, tails are valid hover targets.
 */
export function resolveDropAnchorContext(sourceRows, rowId, options = {}) {
    const container = resolveSiblingContainer(sourceRows, rowId, options);
    if (!container) {
        return null;
    }

    const index = findIndexInSiblingList(container.list, rowId, options);
    if (index < 0) {
        return null;
    }

    const meta = getMergeGroupMeta(container.list[index], options);
    if (!meta) {
        return {
            list: container.list,
            parentRowId: container.parentRowId,
            index,
            blockSize: 1,
            rowId: String(rowId),
            headRowId: String(rowId)
        };
    }

    const blockStart = index - meta.index;
    const head = container.list[blockStart];
    const headLocalId = getLocalRowId(head, options);
    const headRowId = buildFullRowId(container.parentRowId, headLocalId);

    return {
        list: container.list,
        parentRowId: container.parentRowId,
        index: blockStart,
        blockSize: meta.size,
        rowId: String(rowId),
        headRowId
    };
}

export function collectLocalRowIds(list, options = {}) {
    return (list || []).map((row) => getLocalRowId(row, options));
}

export function collectFullRowIds(list, parentRowId, options = {}) {
    return (list || []).map((row) => buildFullRowId(parentRowId, getLocalRowId(row, options)));
}

export function collectDraggedRowIds(dragCtx, options = {}) {
    const ids = [];
    for (let i = 0; i < dragCtx.blockSize; i++) {
        const row = dragCtx.list[dragCtx.index + i];
        if (!row) {
            continue;
        }
        ids.push(buildFullRowId(dragCtx.parentRowId, getLocalRowId(row, options)));
    }
    return ids;
}

export function canNestIntoRow(row, options = {}) {
    if (!row) {
        return false;
    }
    const meta = getMergeGroupMeta(row, options);
    if (meta && meta.index !== 0) {
        return false;
    }
    return true;
}

/**
 * @param {number} offsetY — pointer Y relative to row top
 * @param {number} height — row height
 * @param {boolean} allowInside
 * @returns {"before"|"after"|"inside"}
 */
export function resolveDropPosition(offsetY, height, allowInside) {
    if (!(height > 0)) {
        return ROW_REORDER_POSITIONS.AFTER;
    }
    const ratio = offsetY / height;
    if (allowInside) {
        if (ratio < 0.28) {
            return ROW_REORDER_POSITIONS.BEFORE;
        }
        if (ratio > 0.72) {
            return ROW_REORDER_POSITIONS.AFTER;
        }
        return ROW_REORDER_POSITIONS.INSIDE;
    }
    return ratio < 0.5 ? ROW_REORDER_POSITIONS.BEFORE : ROW_REORDER_POSITIONS.AFTER;
}

/**
 * Resolve a concrete drop into sourceData coordinates.
 * `toIndex` is always the pre-removal insert index in the destination list
 * (same convention as {@link computeNudgeToIndex} / {@link reorderSiblingBlock}).
 *
 * @returns {null|{ noop: true }|{
 *   position: string,
 *   targetRowId: string,
 *   fromParentRowId: string|null,
 *   toParentRowId: string|null,
 *   fromIndex: number,
 *   toIndex: number,
 *   blockSize: number,
 *   rowId: string,
 *   newRowId: string,
 *   indentLevel: number,
 *   sameParent: boolean
 * }}
 *
 * `orderLocked` — display order is owned by sort: reject same-parent
 * slot drops; nesting (inside / cross-parent) still allowed.
 */
export function resolveDropTarget({
    sourceRows,
    dragCtx,
    hoverRowId,
    position,
    allowTree = ROW_REORDER_TREE_MODES.SIBLINGS,
    orderLocked = false,
    options = {}
}) {
    if (!dragCtx || hoverRowId == null || !position) {
        return null;
    }

    if (allowTree === ROW_REORDER_TREE_MODES.OFF && dragCtx.parentRowId != null) {
        return null;
    }

    const draggedIds = collectDraggedRowIds(dragCtx, options);
    const anchor = resolveDropAnchorContext(sourceRows, hoverRowId, options);
    if (!anchor) {
        return null;
    }

    let toParentRowId;
    let toIndex;
    let indentLevel;

    if (position === ROW_REORDER_POSITIONS.INSIDE) {
        if (allowTree !== ROW_REORDER_TREE_MODES.REPARENT) {
            return null;
        }
        const nestRow = findSourceRowInData(sourceRows, anchor.headRowId, options);
        if (!canNestIntoRow(nestRow, options)) {
            return null;
        }
        if (draggedIds.some((id) => isSelfOrDescendantId(id, anchor.headRowId))) {
            return null;
        }
        // Merge atoms stay top-level only (visible tree flatten assumes that).
        if (dragCtx.blockSize > 1) {
            return null;
        }

        toParentRowId = anchor.headRowId;
        const destList = getSiblingListForParent(sourceRows, toParentRowId, options);
        if (!destList) {
            return null;
        }
        toIndex = destList.length;
        indentLevel = String(toParentRowId).split(":").length;
    } else {
        toParentRowId = anchor.parentRowId;
        toIndex = position === ROW_REORDER_POSITIONS.BEFORE
            ? anchor.index
            : anchor.index + anchor.blockSize;
        indentLevel = toParentRowId == null ? 0 : String(toParentRowId).split(":").length;

        if (allowTree === ROW_REORDER_TREE_MODES.OFF && toParentRowId != null) {
            return null;
        }
        if (allowTree === ROW_REORDER_TREE_MODES.SIBLINGS && toParentRowId !== dragCtx.parentRowId) {
            return null;
        }
        if (dragCtx.blockSize > 1 && toParentRowId != null && toParentRowId !== dragCtx.parentRowId) {
            return null;
        }
        if (toParentRowId != null
            && draggedIds.some((id) => isSelfOrDescendantId(id, toParentRowId))) {
            return null;
        }
    }

    const sameParent = dragCtx.parentRowId === toParentRowId;
    if (sameParent
        && toIndex >= dragCtx.index
        && toIndex <= dragCtx.index + dragCtx.blockSize) {
        return { noop: true };
    }
    if (orderLocked && sameParent) {
        return null;
    }

    const localId = String(dragCtx.rowId).split(":").pop();
    const newRowId = buildFullRowId(toParentRowId, localId);

    return {
        position,
        targetRowId: String(hoverRowId),
        fromParentRowId: dragCtx.parentRowId,
        toParentRowId,
        fromIndex: dragCtx.index,
        toIndex,
        blockSize: dragCtx.blockSize,
        rowId: dragCtx.rowId,
        newRowId,
        indentLevel,
        sameParent
    };
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

/**
 * Move a block between sibling lists (or within one).
 * `toIndex` — pre-removal insert index in the destination list.
 */
export function moveRowBlock(sourceRows, {
    fromParentRowId,
    fromIndex,
    blockSize,
    toParentRowId,
    toIndex
}, options = {}) {
    const fromList = getSiblingListForParent(sourceRows, fromParentRowId, options);
    const toList = getSiblingListForParent(sourceRows, toParentRowId, options);
    if (!fromList || !toList || blockSize < 1) {
        return false;
    }
    if (fromIndex < 0 || fromIndex + blockSize > fromList.length) {
        return false;
    }
    if (toIndex < 0 || toIndex > toList.length) {
        return false;
    }

    if (fromList === toList) {
        return reorderSiblingBlock(fromList, fromIndex, blockSize, toIndex);
    }

    const block = fromList.splice(fromIndex, blockSize);
    toList.splice(toIndex, 0, ...block);
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

/**
 * Rebuild two sibling lists after a cross-parent move (undo/redo).
 * `rowPool` must contain every row referenced by either order (moved + stayers).
 */
export function restoreCrossParentOrders(
    fromList,
    toList,
    fromOrderedLocalIds,
    toOrderedLocalIds,
    options = {}
) {
    if (!Array.isArray(fromList) || !Array.isArray(toList)) {
        return false;
    }

    const rowIdField = getRowIdField(options);
    const pool = new Map();
    for (const row of fromList) {
        pool.set(String(row[rowIdField]), row);
    }
    for (const row of toList) {
        pool.set(String(row[rowIdField]), row);
    }

    const build = (order) => (order || []).map((id) => pool.get(String(id))).filter(Boolean);
    const nextFrom = build(fromOrderedLocalIds);
    const nextTo = build(toOrderedLocalIds);

    fromList.splice(0, fromList.length, ...nextFrom);
    toList.splice(0, toList.length, ...nextTo);
    return true;
}

/** Remap path ids in a Set when a row (subtree root) changes parent path. */
export function remapPathIdSet(idSet, fromRowId, toRowId) {
    if (!idSet || fromRowId == null || toRowId == null) {
        return;
    }
    const from = String(fromRowId);
    const to = String(toRowId);
    if (from === to) {
        return;
    }

    const next = [];
    for (const id of [...idSet]) {
        const cur = String(id);
        if (cur === from) {
            idSet.delete(cur);
            next.push(to);
        } else if (cur.startsWith(`${from}:`)) {
            idSet.delete(cur);
            next.push(`${to}${cur.slice(from.length)}`);
        }
    }
    for (const id of next) {
        idSet.add(id);
    }
}

/**
 * Remap every moved top-level block row (merge heads/tails) and their descendant paths.
 */
export function remapPathIdsForBlockMove(idSet, {
    fromParentRowId,
    toParentRowId,
    localIds
}) {
    if (!idSet || fromParentRowId === toParentRowId) {
        return;
    }
    for (const localId of localIds || []) {
        remapPathIdSet(
            idSet,
            buildFullRowId(fromParentRowId, localId),
            buildFullRowId(toParentRowId, localId)
        );
    }
}

export function buildRowReorderMovePayload({
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
    destList,
    options = {}
}) {
    const orderedLocalRowIds = collectLocalRowIds(destList, options);
    const orderedRowIds = collectFullRowIds(destList, toParentRowId, options);

    return {
        section,
        position,
        targetRowId,
        parentRowId: toParentRowId,
        fromParentRowId,
        toParentRowId,
        rowId,
        newRowId,
        fromIndex,
        toIndex,
        blockSize,
        orderedLocalRowIds,
        orderedRowIds,
        rows: (destList || []).map((row) => ({ ...row }))
    };
}
