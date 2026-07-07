import test from "node:test";
import assert from "node:assert/strict";

import { toVisibleRows } from "../core/tree.js";
import {
    expandedSet,
    makeChild,
    makeMergePair,
    makeMergeHead,
    makeRow,
    visibleRowIds
} from "./helpers/fixtures.mjs";

test("merge group collapsed preserves head then tail order", () => {
    const [head, tail] = makeMergePair("1", "2");
    const visible = toVisibleRows([head, tail, makeRow("3")], expandedSet());

    assert.deepEqual(visibleRowIds(visible), ["1", "2", "3"]);
});

test("merge group expanded inserts children after tail not after head", () => {
    const [head, tail] = makeMergePair("1", "2", {
        children: [makeChild("1.1", "1"), makeChild("1.2", "1")]
    });

    const visible = toVisibleRows([head, tail, makeRow("3")], expandedSet("1"));

    assert.deepEqual(visibleRowIds(visible), ["1", "2", "1:1.1", "1:1.2", "3"]);
});

test("merge group lazy head collapsed has no children rows", () => {
    const [head, tail] = makeMergePair("3", "4", { hasChildren: true });

    const visible = toVisibleRows([head, tail], expandedSet());

    assert.deepEqual(visibleRowIds(visible), ["3", "4"]);
    assert.equal(visible[0]._hasChildren, true);
    assert.equal(visible[1]._hasChildren, false);
});

test("plain tree row still expands children immediately after parent", () => {
    const row = makeRow("5", {
        children: [makeChild("5.1", "5"), makeChild("5.2", "5")]
    });

    const visible = toVisibleRows([row], expandedSet("5"));

    assert.deepEqual(visibleRowIds(visible), ["5", "5:5.1", "5:5.2"]);
});

test("invalid merge tail without contiguous head falls back to skipping orphan tail index", () => {
    const orphanTail = makeRow("2", {
        mergeGroupId: "g-1",
        mergeGroupIndex: 1,
        mergeGroupSize: 2
    });
    const plain = makeRow("3");

    const visible = toVisibleRows([orphanTail, plain], expandedSet());

    assert.deepEqual(visibleRowIds(visible), ["3"]);
});

test("three-row merge group expanded keeps all tails before children", () => {
    const head = makeMergeHead("10", 3, {
        children: [makeChild("10.1", "10")]
    });
    const tail1 = makeRow("11", {
        mergeGroupId: "g-10",
        mergeGroupIndex: 1,
        mergeGroupSize: 3
    });
    const tail2 = makeRow("12", {
        mergeGroupId: "g-10",
        mergeGroupIndex: 2,
        mergeGroupSize: 3
    });

    const visible = toVisibleRows([head, tail1, tail2], expandedSet("10"));

    assert.deepEqual(visibleRowIds(visible), ["10", "11", "12", "10:10.1"]);
});

test("toVisibleRows tolerates missing expandedIds (empty Set)", () => {
    const row = makeRow("1", { children: [makeChild("1.1", "1")] });
    const visible = toVisibleRows([row], undefined);

    assert.deepEqual(visibleRowIds(visible), ["1"]);
    assert.equal(visible[0]._hasChildren, true);
});
