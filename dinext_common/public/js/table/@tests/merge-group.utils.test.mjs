import test from "node:test";
import assert from "node:assert/strict";

import {
    asStandaloneMergeGroupRow,
    getMergeGroupMeta,
    getMergeGroupChildInsertOffset,
    isMergeGroupHead,
    shouldSpanMergeGroupRows
} from "../core/shared/utils.js";
import { rowIsExpandable } from "../core/tree/model.js";
import { makeMergeHead, makeMergeTail, makeRow } from "./helpers/fixtures.mjs";

test("getMergeGroupMeta returns null when size < 2", () => {
    const row = makeRow("1", { mergeGroupId: "g-1", mergeGroupIndex: 0, mergeGroupSize: 1 });
    assert.equal(getMergeGroupMeta(row), null);
});

test("getMergeGroupMeta parses valid merge group row", () => {
    const row = makeMergeHead("1", 2);
    assert.deepEqual(getMergeGroupMeta(row), { id: "g-1", index: 0, size: 2 });
});

test("standalone merge projection preserves source fields but disables display merge", () => {
    const source = makeMergeHead("1", 2);
    const projected = asStandaloneMergeGroupRow(source);

    assert.notEqual(projected, source);
    assert.equal(projected.mergeGroupId, source.mergeGroupId);
    assert.equal(projected.mergeGroupIndex, source.mergeGroupIndex);
    assert.equal(projected.mergeGroupSize, source.mergeGroupSize);
    assert.equal(getMergeGroupMeta(projected), null);
    assert.deepEqual(getMergeGroupMeta(source), { id: "g-1", index: 0, size: 2 });
});

test("getMergeGroupChildInsertOffset inserts after tail for merge head", () => {
    assert.equal(getMergeGroupChildInsertOffset(makeMergeHead("1", 2)), 2);
    assert.equal(getMergeGroupChildInsertOffset(makeRow("9")), 1);
    assert.equal(getMergeGroupChildInsertOffset(makeMergeTail("2", "1", 2)), 1);
});

test("isMergeGroupHead identifies head only", () => {
    assert.equal(isMergeGroupHead(makeMergeHead("1", 2)), true);
    assert.equal(isMergeGroupHead(makeMergeTail("2", "1", 2)), false);
});

test("rowIsExpandable rejects tail even with hasChildren", () => {
    const tail = makeMergeTail("2", "1", 2, { hasChildren: true });
    assert.equal(rowIsExpandable(tail, "children"), false);
});

test("rowIsExpandable allows lazy marker on merge head", () => {
    const head = makeMergeHead("3", 2, { hasChildren: true });
    assert.equal(rowIsExpandable(head, "children"), true);
});

test("shouldSpanMergeGroupRows merges same group only", () => {
    const head = makeMergeHead("1", 2);
    const tail = makeMergeTail("2", "1", 2);
    const other = makeRow("9");

    assert.equal(shouldSpanMergeGroupRows({ data: head }, { data: tail }), true);
    assert.equal(shouldSpanMergeGroupRows({ data: head }, { data: other }), false);
});
