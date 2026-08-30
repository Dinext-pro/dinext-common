/**
 * In-memory trees for table_row_reorder scenario.
 * Keep in sync with tests/scenarios/table_row_reorder/data_setup.py
 */
import { ROW_REORDER_TREE_MODES } from "../../core/row-reorder/constants.js";
import {
    buildRowReorderMovePayload,
    collectDraggedRowIds,
    collectLocalRowIds,
    getSiblingListForParent,
    moveRowBlock,
    remapPathIdsForBlockMove,
    resolveDropTarget,
    resolveReorderContext
} from "../../core/row-reorder/ops.js";
import {
    NEST_SHIFT_PX,
    SWAP_EDGE_PX,
    isDraggedPreviewRowId,
    planRowReorderPreview,
    resolveReorderIntent
} from "../../core/row-reorder/preview.js";

export { NEST_SHIFT_PX, SWAP_EDGE_PX };

export const ROW_H = 28;
export const START_X = 10;

export function clone(value) {
    return structuredClone(value);
}

export function flatAbc() {
    return [{ id: "a" }, { id: "b" }, { id: "c" }];
}

export function flatAbcd() {
    return [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
}

export function treeTwoRootsOneChild() {
    return [
        { id: "a", children: [{ id: "a1" }] },
        { id: "b", children: [{ id: "b1" }] }
    ];
}

export function treeParentWithTwoChildren() {
    return [
        { id: "p", children: [{ id: "c1" }, { id: "c2" }] },
        { id: "z" }
    ];
}

export function treeDeepThreeLevels() {
    return [
        {
            id: "a",
            children: [
                { id: "a1", children: [{ id: "a1x" }, { id: "a1y" }] },
                { id: "a2" }
            ]
        },
        { id: "b", children: [{ id: "b1", children: [{ id: "b1x" }] }] },
        { id: "c" }
    ];
}

export function treeExpandedBranchPair() {
    return [
        { id: "p", children: [{ id: "pc1" }, { id: "pc2" }] },
        { id: "q", children: [{ id: "qc1" }] },
        { id: "r" }
    ];
}

export function treeSelfNestGuard() {
    return [{ id: "p", children: [{ id: "c", children: [{ id: "g" }] }] }];
}

export function mergeHeadTailPlusPlain() {
    return [
        { id: "a" },
        { id: "h", mergeGroupId: "g1", mergeGroupIndex: 0, mergeGroupSize: 2 },
        { id: "t", mergeGroupId: "g1", mergeGroupIndex: 1, mergeGroupSize: 2 },
        { id: "z" }
    ];
}

export function flattenVisible(rows, expanded, parentId = null, level = 0, out = []) {
    for (const row of rows || []) {
        const id = parentId ? `${parentId}:${row.id}` : row.id;
        out.push({ id, level, row });
        if (expanded.has(id) && Array.isArray(row.children) && row.children.length) {
            flattenVisible(row.children, expanded, id, level + 1, out);
        }
    }
    return out;
}

export function expandedSet(...ids) {
    return new Set(ids.map(String));
}

export function localIds(rows) {
    return (rows || []).map((row) => row.id);
}

export function childIds(rows, parentId) {
    const parent = (rows || []).find((row) => row.id === parentId);
    return localIds(parent?.children);
}

export function hitsFromVisible(visibleIds, draggedIds, rowH = ROW_H) {
    return visibleIds.map((id, index) => ({
        rowId: id,
        top: index * rowH,
        bottom: (index + 1) * rowH,
        height: rowH,
        isDragged: isDraggedPreviewRowId(id, draggedIds)
    }));
}

export function hitY(hits, rowId, edge = "mid") {
    const hit = hits.find((item) => item.rowId === rowId);
    if (!hit) {
        throw new Error(`hit not found: ${rowId}`);
    }
    if (edge === "mid") {
        return (hit.top + hit.bottom) / 2;
    }
    if (edge === "swapDown") {
        return hit.top + SWAP_EDGE_PX + 1;
    }
    if (edge === "swapUp") {
        return hit.bottom - SWAP_EDGE_PX - 1;
    }
    if (edge === "homeDown") {
        return hit.top + SWAP_EDGE_PX - 1;
    }
    if (edge === "homeUp") {
        return hit.bottom - SWAP_EDGE_PX + 1;
    }
    return (hit.top + hit.bottom) / 2;
}

export function previewRowsFromVisible(visible, draggedIds, rowH = ROW_H) {
    return visible.map((item, index) => ({
        rowId: item.id,
        y: index * rowH,
        height: rowH,
        level: item.level,
        isDragged: isDraggedPreviewRowId(item.id, draggedIds)
    }));
}

/**
 * Mixin pipeline without DOM: intent → drop → preview → move → onRowReorder payload.
 */
export function simulateRowReorder({
    data,
    draggedId,
    visibleIds,
    expanded,
    clientY,
    hoverRowId,
    hoverEdge = "mid",
    shiftX = 0,
    allowTree = ROW_REORDER_TREE_MODES.REPARENT
}) {
    const source = clone(data);
    const ctx = resolveReorderContext(source, draggedId);
    if (!ctx) {
        return { kind: "blocked", data: source };
    }

    const draggedIds = collectDraggedRowIds(ctx);
    const visible = visibleIds
        ? visibleIds.map((id) => ({
            id,
            level: String(id).split(":").length - 1
        }))
        : flattenVisible(source, expanded || new Set());
    const ids = visible.map((item) => item.id);
    const hits = hitsFromVisible(ids, draggedIds);
    const y = clientY != null
        ? clientY
        : hitY(hits, hoverRowId, hoverEdge);

    const intent = resolveReorderIntent({
        hits,
        clientY: y,
        clientX: START_X + shiftX,
        startClientX: START_X,
        allowNest: allowTree === ROW_REORDER_TREE_MODES.REPARENT,
        draggedIds
    });

    if (!intent) {
        return { kind: "invalid", intent, ctx, draggedIds, hits, data: source };
    }
    if (intent.home) {
        return { kind: "home", intent, ctx, draggedIds, hits, data: source };
    }

    const drop = resolveDropTarget({
        sourceRows: source,
        dragCtx: ctx,
        hoverRowId: intent.hoverRowId,
        position: intent.position,
        allowTree
    });

    if (drop?.noop) {
        return { kind: "home", intent, drop, ctx, draggedIds, hits, data: source };
    }
    if (!drop) {
        return { kind: "invalid", intent, drop, ctx, draggedIds, hits, data: source };
    }

    const preview = planRowReorderPreview(
        previewRowsFromVisible(visible, draggedIds),
        drop
    );

    const fromList = getSiblingListForParent(source, drop.fromParentRowId);
    const destBefore = getSiblingListForParent(source, drop.toParentRowId);
    const fromOrderBefore = collectLocalRowIds(fromList);
    const toOrderBefore = drop.sameParent
        ? fromOrderBefore
        : collectLocalRowIds(destBefore);

    const movedLocalIds = [];
    for (let i = 0; i < drop.blockSize; i++) {
        const row = ctx.list[drop.fromIndex + i];
        if (row) {
            movedLocalIds.push(row.id);
        }
    }

    const applied = moveRowBlock(source, {
        fromParentRowId: drop.fromParentRowId,
        fromIndex: drop.fromIndex,
        blockSize: drop.blockSize,
        toParentRowId: drop.toParentRowId,
        toIndex: drop.toIndex
    });

    const idSet = new Set(ids);
    remapPathIdsForBlockMove(idSet, {
        fromParentRowId: drop.fromParentRowId,
        toParentRowId: drop.toParentRowId,
        localIds: movedLocalIds
    });

    const destList = getSiblingListForParent(source, drop.toParentRowId);
    const fromAfter = getSiblingListForParent(source, drop.fromParentRowId);
    const toOrderAfter = collectLocalRowIds(destList);
    const fromOrderAfter = drop.sameParent
        ? toOrderAfter
        : collectLocalRowIds(fromAfter);

    const payload = {
        ...buildRowReorderMovePayload({
            section: "body",
            position: drop.position,
            targetRowId: drop.targetRowId,
            fromParentRowId: drop.fromParentRowId,
            toParentRowId: drop.toParentRowId,
            rowId: drop.rowId,
            newRowId: drop.newRowId,
            fromIndex: drop.fromIndex,
            toIndex: drop.toIndex,
            blockSize: drop.blockSize,
            destList
        }),
        orderedLocalRowIds: toOrderAfter,
        orderedRowIds: toOrderAfter.map((localId) => (
            drop.toParentRowId ? `${drop.toParentRowId}:${localId}` : localId
        )),
        fromOrderedLocalRowIds: fromOrderAfter
    };

    return {
        kind: applied ? "commit" : "invalid",
        intent,
        drop,
        preview,
        payload,
        ctx,
        draggedIds,
        hits,
        remappedIds: [...idSet].sort(),
        fromOrderBefore,
        toOrderBefore,
        data: source
    };
}
