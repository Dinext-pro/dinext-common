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
