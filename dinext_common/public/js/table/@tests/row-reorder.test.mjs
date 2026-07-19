import test from "node:test";
import assert from "node:assert/strict";

import {
    collectLocalRowIds,
    computeNudgeToIndex,
    computeTargetInsertIndex,
    reorderSiblingBlock,
    resolveMergeBlock,
    resolveReorderContext,
    restoreSiblingListOrder
} from "../core/row-reorder/ops.js";

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

test("computeTargetInsertIndex requires same parent", () => {
    const data = [
        { id: "p1", children: [{ id: "a" }] },
        { id: "p2", children: [{ id: "b" }] }
    ];
    const dragCtx = resolveReorderContext(data, "p1:a");
    const hoverCtx = resolveReorderContext(data, "p2:b");
    assert.equal(computeTargetInsertIndex(dragCtx, hoverCtx, true), null);
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
