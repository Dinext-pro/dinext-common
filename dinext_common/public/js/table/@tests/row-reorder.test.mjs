import test from "node:test";
import assert from "node:assert/strict";

import {
    collectLocalRowIds,
    computeNudgeToIndex,
    isSelfOrDescendantId,
    moveRowBlock,
    remapPathIdSet,
    reorderSiblingBlock,
    resolveDropPosition,
    resolveDropTarget,
    resolveMergeBlock,
    resolveReorderContext,
    restoreCrossParentOrders,
    restoreSiblingListOrder
} from "../core/row-reorder/ops.js";
import { ROW_REORDER_POSITIONS } from "../core/row-reorder/constants.js";
import { RowReorderMixin } from "../core/row-reorder/mixin.js";
import {
    NEST_SHIFT_PX,
    SWAP_EDGE_PX,
    hitPreviewRow,
    isDraggedPreviewRowId,
    isHomePreviewHit,
    planRowReorderPreview,
    resolveReorderIntent
} from "../core/row-reorder/preview.js";

test("resolveReorderContext finds top-level row", () => {
    const data = [{ id: "a" }, { id: "b" }];
    const ctx = resolveReorderContext(data, "b");
    assert.equal(ctx.parentRowId, null);
    assert.equal(ctx.index, 1);
    assert.equal(ctx.blockSize, 1);
});

test("resolveReorderContext finds nested sibling list", () => {
    const data = [{
        id: "p",
        children: [{ id: "c1" }, { id: "c2" }]
    }];
    const ctx = resolveReorderContext(data, "p:c2");
    assert.equal(ctx.parentRowId, "p");
    assert.equal(ctx.index, 1);
});

test("resolveMergeBlock blocks merge tail drag", () => {
    const list = [
        { id: "h", mergeGroupId: "g1", mergeGroupIndex: 0, mergeGroupSize: 2 },
        { id: "t", mergeGroupId: "g1", mergeGroupIndex: 1, mergeGroupSize: 2 }
    ];
    assert.equal(resolveMergeBlock(list, 0).blockSize, 2);
    assert.equal(resolveMergeBlock(list, 1).blocked, true);
});

test("reorderSiblingBlock moves merge head block", () => {
    const list = [
        { id: "a" },
        { id: "h", mergeGroupId: "g1", mergeGroupIndex: 0, mergeGroupSize: 2 },
        { id: "t", mergeGroupId: "g1", mergeGroupIndex: 1, mergeGroupSize: 2 },
        { id: "z" }
    ];
    assert.equal(reorderSiblingBlock(list, 1, 2, 4), true);
    assert.deepEqual(collectLocalRowIds(list), ["a", "z", "h", "t"]);
});

test("resolveDropTarget siblings mode blocks cross-parent", () => {
    const data = [
        { id: "p1", children: [{ id: "a" }] },
        { id: "p2", children: [{ id: "b" }] }
    ];
    const dragCtx = resolveReorderContext(data, "p1:a");
    const drop = resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p2:b",
        position: ROW_REORDER_POSITIONS.BEFORE,
        allowTree: "siblings"
    });
    assert.equal(drop, null);
});

test("resolveDropTarget reparent allows before across parents", () => {
    const data = [
        { id: "p1", children: [{ id: "a" }] },
        { id: "p2", children: [{ id: "b" }] }
    ];
    const dragCtx = resolveReorderContext(data, "p1:a");
    const drop = resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p2:b",
        position: ROW_REORDER_POSITIONS.BEFORE,
        allowTree: "reparent"
    });
    assert.ok(drop);
    assert.equal(drop.toParentRowId, "p2");
    assert.equal(drop.toIndex, 0);
    assert.equal(drop.newRowId, "p2:a");
});

test("resolveDropTarget inside nests under hover", () => {
    const data = [
        { id: "a" },
        { id: "b", children: [{ id: "c" }] }
    ];
    const dragCtx = resolveReorderContext(data, "a");
    const drop = resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "b",
        position: ROW_REORDER_POSITIONS.INSIDE,
        allowTree: "reparent"
    });
    assert.ok(drop);
    assert.equal(drop.toParentRowId, "b");
    assert.equal(drop.toIndex, 1);
    assert.equal(drop.newRowId, "b:a");
});

test("resolveDropTarget inside blocked into self/descendant", () => {
    const data = [{
        id: "p",
        children: [{ id: "c", children: [{ id: "g" }] }]
    }];
    const dragCtx = resolveReorderContext(data, "p");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p:c",
        position: ROW_REORDER_POSITIONS.INSIDE,
        allowTree: "reparent"
    }), null);
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p:c:g",
        position: ROW_REORDER_POSITIONS.BEFORE,
        allowTree: "reparent"
    }), null);
});

test("resolveDropTarget after parent outdents child", () => {
    const data = [
        { id: "p", children: [{ id: "c1" }, { id: "c2" }] },
        { id: "z" }
    ];
    const dragCtx = resolveReorderContext(data, "p:c1");
    const drop = resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p",
        position: ROW_REORDER_POSITIONS.AFTER,
        allowTree: "reparent"
    });
    assert.ok(drop);
    assert.equal(drop.toParentRowId, null);
    assert.equal(drop.toIndex, 1);
    assert.equal(drop.newRowId, "c1");
});

test("moveRowBlock reparents and restoreCrossParentOrders undoes", () => {
    const data = [
        { id: "p1", children: [{ id: "a" }, { id: "x" }] },
        { id: "p2", children: [{ id: "b" }] }
    ];
    const fromBefore = ["a", "x"];
    const toBefore = ["b"];
    assert.equal(moveRowBlock(data, {
        fromParentRowId: "p1",
        fromIndex: 0,
        blockSize: 1,
        toParentRowId: "p2",
        toIndex: 1
    }), true);
    assert.deepEqual(collectLocalRowIds(data[0].children), ["x"]);
    assert.deepEqual(collectLocalRowIds(data[1].children), ["b", "a"]);

    restoreCrossParentOrders(
        data[0].children,
        data[1].children,
        fromBefore,
        toBefore
    );
    assert.deepEqual(collectLocalRowIds(data[0].children), ["a", "x"]);
    assert.deepEqual(collectLocalRowIds(data[1].children), ["b"]);
});

test("resolveDropPosition zones", () => {
    assert.equal(resolveDropPosition(5, 100, true), ROW_REORDER_POSITIONS.BEFORE);
    assert.equal(resolveDropPosition(50, 100, true), ROW_REORDER_POSITIONS.INSIDE);
    assert.equal(resolveDropPosition(90, 100, true), ROW_REORDER_POSITIONS.AFTER);
    assert.equal(resolveDropPosition(50, 100, false), ROW_REORDER_POSITIONS.AFTER);
    assert.equal(resolveDropPosition(40, 100, false), ROW_REORDER_POSITIONS.BEFORE);
});

test("remapPathIdSet rewrites subtree ids", () => {
    const ids = new Set(["p:a", "p:a:c", "other"]);
    remapPathIdSet(ids, "p:a", "q:a");
    assert.deepEqual([...ids].sort(), ["other", "q:a", "q:a:c"]);
});

test("isSelfOrDescendantId", () => {
    assert.equal(isSelfOrDescendantId("p", "p"), true);
    assert.equal(isSelfOrDescendantId("p", "p:c"), true);
    assert.equal(isSelfOrDescendantId("p", "px"), false);
});

test("restoreSiblingListOrder reverts permutation", () => {
    const list = [{ id: "a" }, { id: "b" }, { id: "c" }];
    reorderSiblingBlock(list, 0, 1, 3);
    assert.deepEqual(collectLocalRowIds(list), ["b", "c", "a"]);
    restoreSiblingListOrder(list, ["a", "b", "c"]);
    assert.deepEqual(collectLocalRowIds(list), ["a", "b", "c"]);
});

test("computeNudgeToIndex moves single row down/up", () => {
    const list = [{ id: "a" }, { id: "b" }, { id: "c" }];
    const down = computeNudgeToIndex(list, 1, 1, 1);
    assert.equal(down, 3);
    const copy = list.map((r) => ({ ...r }));
    assert.equal(reorderSiblingBlock(copy, 1, 1, down), true);
    assert.deepEqual(collectLocalRowIds(copy), ["a", "c", "b"]);

    const up = computeNudgeToIndex(list, 1, 1, -1);
    assert.equal(up, 0);
    const copy2 = list.map((r) => ({ ...r }));
    assert.equal(reorderSiblingBlock(copy2, 1, 1, up), true);
    assert.deepEqual(collectLocalRowIds(copy2), ["b", "a", "c"]);
});

function previewRows(specs) {
    return specs.map((spec) => ({
        rowId: spec.id,
        y: spec.y,
        height: spec.height ?? 28,
        level: spec.level ?? 0,
        isDragged: !!spec.dragged
    }));
}

test("planRowReorderPreview moves block down between siblings", () => {
    const rows = previewRows([
        { id: "a", y: 0, dragged: true },
        { id: "b", y: 28 },
        { id: "c", y: 56 },
        { id: "d", y: 84 }
    ]);
    const plan = planRowReorderPreview(rows, {
        position: ROW_REORDER_POSITIONS.AFTER,
        targetRowId: "c",
        indentLevel: 0
    });
    const byId = Object.fromEntries(plan.map((item) => [item.rowId, item.y]));
    assert.equal(byId.b, 0);
    assert.equal(byId.c, 28);
    assert.equal(byId.a, 56);
    assert.equal(byId.d, 84);
});

test("planRowReorderPreview moves block up before sibling", () => {
    const rows = previewRows([
        { id: "a", y: 0 },
        { id: "b", y: 28 },
        { id: "c", y: 56, dragged: true }
    ]);
    const plan = planRowReorderPreview(rows, {
        position: ROW_REORDER_POSITIONS.BEFORE,
        targetRowId: "a",
        indentLevel: 0
    });
    const byId = Object.fromEntries(plan.map((item) => [item.rowId, item.y]));
    assert.equal(byId.c, 0);
    assert.equal(byId.a, 28);
    assert.equal(byId.b, 56);
});

test("planRowReorderPreview nests after visible children and bumps indent", () => {
    const rows = previewRows([
        { id: "move", y: 0, dragged: true, level: 0 },
        { id: "p", y: 28, level: 0 },
        { id: "p:c1", y: 56, level: 1 }
    ]);
    const plan = planRowReorderPreview(rows, {
        position: ROW_REORDER_POSITIONS.INSIDE,
        targetRowId: "p",
        indentLevel: 1
    });
    const byId = Object.fromEntries(plan.map((item) => [item.rowId, item]));
    assert.equal(byId.p.y, 0);
    assert.equal(byId["p:c1"].y, 28);
    assert.equal(byId.move.y, 56);
    assert.equal(byId.move.indentDelta, 20);
});

test("isDraggedPreviewRowId includes visible descendants", () => {
    assert.equal(isDraggedPreviewRowId("p:c", ["p"]), true);
    assert.equal(isDraggedPreviewRowId("q", ["p"]), false);
});

test("hitPreviewRow ignores gaps between mapped rows", () => {
    const hits = [
        { rowId: "b", top: 0, bottom: 28, height: 28 },
        { rowId: "c", top: 56, bottom: 84, height: 28 }
    ];
    assert.equal(hitPreviewRow(hits, 10)?.rowId, "b");
    assert.equal(hitPreviewRow(hits, 40), null);
    assert.equal(hitPreviewRow(hits, 60)?.rowId, "c");
});

test("resolveReorderIntent swaps after SWAP_EDGE_PX into neighbor, same up and down", () => {
    const hits = [
        { rowId: "a", top: 0, bottom: 28, height: 28, isDragged: true },
        { rowId: "b", top: 28, bottom: 56, height: 28 }
    ];
    const stillHome = resolveReorderIntent({
        hits,
        clientY: 28 + SWAP_EDGE_PX - 1,
        clientX: 10,
        startClientX: 10,
        allowNest: true,
        draggedIds: ["a"]
    });
    assert.equal(stillHome.home, true);

    const down = resolveReorderIntent({
        hits,
        clientY: 28 + SWAP_EDGE_PX + 1,
        clientX: 10,
        startClientX: 10,
        allowNest: true,
        draggedIds: ["a"]
    });
    assert.equal(down.position, ROW_REORDER_POSITIONS.AFTER);
    assert.equal(down.hoverRowId, "b");

    const upHits = [
        { rowId: "b", top: 0, bottom: 28, height: 28 },
        { rowId: "a", top: 28, bottom: 56, height: 28, isDragged: true }
    ];
    const upHome = resolveReorderIntent({
        hits: upHits,
        clientY: 28 - SWAP_EDGE_PX + 1,
        clientX: 10,
        startClientX: 10,
        allowNest: true,
        draggedIds: ["a"]
    });
    assert.equal(upHome.home, true);

    const up = resolveReorderIntent({
        hits: upHits,
        clientY: 28 - SWAP_EDGE_PX - 1,
        clientX: 10,
        startClientX: 10,
        allowNest: true,
        draggedIds: ["a"]
    });
    assert.equal(up.position, ROW_REORDER_POSITIONS.BEFORE);
    assert.equal(up.hoverRowId, "b");
});

test("resolveReorderIntent right shift nests into row above", () => {
    const hits = [
        { rowId: "a", top: 0, bottom: 28, height: 28 },
        { rowId: "b", top: 28, bottom: 56, height: 28, isDragged: true }
    ];
    const nestAfter = resolveReorderIntent({
        hits: [
            { rowId: "a", top: 0, bottom: 28, height: 28, isDragged: true },
            { rowId: "b", top: 28, bottom: 56, height: 28 }
        ],
        clientY: 28 + SWAP_EDGE_PX + 1,
        clientX: 10 + NEST_SHIFT_PX,
        startClientX: 10,
        allowNest: true,
        draggedIds: ["a"]
    });
    assert.equal(nestAfter.position, ROW_REORDER_POSITIONS.INSIDE);
    assert.equal(nestAfter.hoverRowId, "b");
});

test("resolveReorderIntent nest after swap with b is parent a, not b", () => {
    const hits = [
        { rowId: "a", top: 0, bottom: 28, height: 28 },
        { rowId: "b", top: 28, bottom: 56, height: 28 },
        { rowId: "c", top: 56, bottom: 84, height: 28, isDragged: true }
    ];
    const nest = resolveReorderIntent({
        hits,
        clientY: 56 - SWAP_EDGE_PX - 1,
        clientX: 10 + NEST_SHIFT_PX,
        startClientX: 10,
        allowNest: true,
        draggedIds: ["c"]
    });
    assert.equal(nest.position, ROW_REORDER_POSITIONS.INSIDE);
    assert.equal(nest.hoverRowId, "a");
});

test("resolveReorderIntent home plus right nests under the row above", () => {
    const hits = [
        { rowId: "a", top: 0, bottom: 28, height: 28 },
        { rowId: "b", top: 28, bottom: 56, height: 28 },
        { rowId: "c", top: 56, bottom: 84, height: 28, isDragged: true }
    ];
    const nest = resolveReorderIntent({
        hits,
        clientY: 70,
        clientX: 10 + NEST_SHIFT_PX,
        startClientX: 10,
        allowNest: true,
        draggedIds: ["c"]
    });
    assert.equal(nest.position, ROW_REORDER_POSITIONS.INSIDE);
    assert.equal(nest.hoverRowId, "b");
});

test("resolveDropTarget same slot is noop so preview can return home", () => {
    const data = [{ id: "a" }, { id: "b" }];
    const dragCtx = resolveReorderContext(data, "a");
    const drop = resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "b",
        position: ROW_REORDER_POSITIONS.BEFORE,
        allowTree: "siblings"
    });
    assert.equal(drop.noop, true);
});

test("isHomePreviewHit treats original dragged slot as home", () => {
    assert.equal(isHomePreviewHit({ rowId: "a", isDragged: true }, ["a"]), true);
    assert.equal(isHomePreviewHit({ rowId: "b", isDragged: false }, ["a"]), false);
});

test("resolveReorderIntent does not nest when tree reparent off", () => {
    const hits = [
        { rowId: "a", top: 0, bottom: 28, height: 28, isDragged: true },
        { rowId: "b", top: 28, bottom: 56, height: 28 }
    ];
    const intent = resolveReorderIntent({
        hits,
        clientY: 28 + SWAP_EDGE_PX + 1,
        clientX: 80,
        startClientX: 10,
        allowNest: false,
        draggedIds: ["a"]
    });
    assert.equal(intent.position, ROW_REORDER_POSITIONS.AFTER);
    assert.equal(intent.hoverRowId, "b");
});

test("shouldShowRowReorderHandle skips pinned-bottom summary", () => {
    class FakeBase {
        initFeatures() {}
        destroyFeatures() {}
        afterGridCreated() {}
        buildColumnDefs() {
            return [];
        }
        handleSetOption() {
            return false;
        }
    }
    const Table = RowReorderMixin(FakeBase);
    const table = new Table();
    table.options = { rowReorder: { enabled: true, allowSummary: false } };
    assert.equal(
        table.shouldShowRowReorderHandle({
            data: { id: "sum", _section: "summary" },
            rowPinned: "bottom"
        }),
        false
    );
    assert.equal(
        table.shouldShowRowReorderHandle({ data: { id: "a" }, rowPinned: null }),
        true
    );
});

test("resolveDropTarget rejects hover on canReorderRow=false", () => {
    const data = [
        { id: "p", rowType: "position" },
        { id: "s", rowType: "section" },
        { id: "l", rowType: "leave" }
    ];
    const options = { canReorderRow: ({ row }) => row.rowType === "position" };
    const dragCtx = resolveReorderContext(data, "p");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "s",
        position: ROW_REORDER_POSITIONS.AFTER,
        options
    }), null);
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "l",
        position: ROW_REORDER_POSITIONS.BEFORE,
        options
    }), null);
});

test("resolveDropTarget rejects drop onto locked tree child", () => {
    const data = [
        { id: "p", rowType: "position" },
        { id: "leave", rowType: "leave", children: [{ id: "child" }] }
    ];
    const options = { canReorderRow: ({ row }) => row.rowType === "position" };
    const dragCtx = resolveReorderContext(data, "p");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "leave:child",
        position: ROW_REORDER_POSITIONS.BEFORE,
        allowTree: "reparent",
        options
    }), null);
});

test("resolveDropTarget rejects insert between two locked siblings", () => {
    const data = [
        { id: "p", rowType: "position" },
        { id: "s", rowType: "section" },
        { id: "l", rowType: "leave" }
    ];
    const options = { canReorderRow: ({ row }) => row.rowType === "position" };
    const dragCtx = resolveReorderContext(data, "p");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "s",
        position: ROW_REORDER_POSITIONS.AFTER,
        options
    }), null);
});

test("canAcceptRowReorder fences drop past first locked row", () => {
    const data = [
        { id: "p1", rowType: "position" },
        { id: "s", rowType: "section" },
        { id: "p2", rowType: "position" },
        { id: "l", rowType: "leave" }
    ];
    const options = {
        canReorderRow: ({ row }) => row.rowType === "position",
        canAcceptRowReorder: ({ dropTarget, sourceRows }) => {
            const fence = sourceRows.findIndex((row) => row.rowType === "section");
            return dropTarget.toIndex <= fence;
        }
    };
    const dragCtx = resolveReorderContext(data, "p1");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p2",
        position: ROW_REORDER_POSITIONS.AFTER,
        options
    }), null);
    const beforeFence = resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p1",
        position: ROW_REORDER_POSITIONS.AFTER,
        options
    });
    assert.equal(beforeFence?.noop, true);
});

test("resolveDropTarget allows after last position before locked block", () => {
    const data = [
        { id: "p1", rowType: "position" },
        { id: "p2", rowType: "position" },
        { id: "s", rowType: "section" },
        { id: "l", rowType: "leave" }
    ];
    const options = { canReorderRow: ({ row }) => row.rowType === "position" };
    const dragCtx = resolveReorderContext(data, "p1");
    const drop = resolveDropTarget({
        sourceRows: data,
        dragCtx,
        hoverRowId: "p2",
        position: ROW_REORDER_POSITIONS.AFTER,
        options
    });
    assert.equal(drop?.toIndex, 2);
    assert.equal(drop?.sameParent, true);
});

test("shouldShowRowReorderHandle honors canReorderRow", () => {
    class FakeBase {
        initFeatures() {}
        destroyFeatures() {}
        afterGridCreated() {}
        buildColumnDefs() {
            return [];
        }
        handleSetOption() {
            return false;
        }
    }
    const Table = RowReorderMixin(FakeBase);
    const table = new Table();
    table.options = {
        rowReorder: { enabled: true },
        canReorderRow: ({ row }) => row.rowType === "position"
    };
    assert.equal(
        table.shouldShowRowReorderHandle({ data: { id: "s", rowType: "section" } }),
        false
    );
    assert.equal(
        table.shouldShowRowReorderHandle({ data: { id: "p", rowType: "position" } }),
        true
    );
});
