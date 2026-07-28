import test from "node:test";
import assert from "node:assert/strict";

import {
    cloneRowTree,
    collectCheckableRowIds,
    getStableRowId,
    insertRowsAfter,
    isPlainRowData,
    isRowCheckable,
    pruneCheckedIds,
    removeCheckedRowsFromSource,
    replaceArrayContents,
    resolveSelectAllState
} from "../core/row-check/model.js";
import { ROW_CHECK_COL_ID, ROW_CHECK_UNITS } from "../core/row-check/constants.js";
import { computeNudgeToIndex, reorderSiblingBlock, collectLocalRowIds } from "../core/row-reorder/ops.js";
import { resolveToolbarPresetItems } from "../core/toolbar/presets.js";

test("isRowCheckable blocks merge tails when unit=mergeHead", () => {
    const head = { id: "h", mergeGroupId: "g", mergeGroupIndex: 0, mergeGroupSize: 2 };
    const tail = { id: "t", mergeGroupId: "g", mergeGroupIndex: 1, mergeGroupSize: 2 };
    const opts = { unit: ROW_CHECK_UNITS.MERGE_HEAD };
    assert.equal(isRowCheckable(head, {}, opts), true);
    assert.equal(isRowCheckable(tail, {}, opts), false);
});

test("isRowCheckable blocks summary unless allowSummary", () => {
    const row = { id: "s", _section: "summary" };
    assert.equal(isRowCheckable(row, {}, { unit: "row" }), false);
    assert.equal(isRowCheckable(row, {}, { unit: "row", allowSummary: true }), true);
});

test("collectCheckableRowIds walks tree and respects mergeHead", () => {
    const data = [
        {
            id: "p",
            mergeGroupId: "g1",
            mergeGroupIndex: 0,
            mergeGroupSize: 2,
            children: [{ id: "c1" }]
        },
        { id: "t", mergeGroupId: "g1", mergeGroupIndex: 1, mergeGroupSize: 2 },
        { id: "z" }
    ];
    const ids = collectCheckableRowIds(data, {}, { unit: ROW_CHECK_UNITS.MERGE_HEAD });
    assert.deepEqual(ids, ["p", "p:c1", "z"]);
});

test("resolveSelectAllState returns indeterminate", () => {
    assert.equal(resolveSelectAllState(["a", "b", "c"], ["b"]), "indeterminate");
    assert.equal(resolveSelectAllState(["a", "b"], ["a", "b"]), "checked");
    assert.equal(resolveSelectAllState(["a"], []), "unchecked");
});

test("pruneCheckedIds drops missing rows", () => {
    const data = [{ id: "a" }, { id: "b" }];
    assert.deepEqual(pruneCheckedIds(["a", "gone", "b"], data, {}), ["a", "b"]);
});

test("removeCheckedRowsFromSource removes merge atom", () => {
    const data = [
        { id: "a" },
        { id: "h", mergeGroupId: "g", mergeGroupIndex: 0, mergeGroupSize: 2 },
        { id: "t", mergeGroupId: "g", mergeGroupIndex: 1, mergeGroupSize: 2 },
        { id: "z" }
    ];
    const { removed, ok } = removeCheckedRowsFromSource(data, ["h"], {});
    assert.equal(ok, true);
    assert.equal(removed.length, 2);
    assert.deepEqual(data.map((r) => r.id), ["a", "z"]);
});

test("insertRowsAfter places after merge block", () => {
    const data = [
        { id: "h", mergeGroupId: "g", mergeGroupIndex: 0, mergeGroupSize: 2 },
        { id: "t", mergeGroupId: "g", mergeGroupIndex: 1, mergeGroupSize: 2 },
        { id: "z" }
    ];
    assert.equal(insertRowsAfter(data, "h", [{ id: "n" }], {}), true);
    assert.deepEqual(data.map((r) => r.id), ["h", "t", "n", "z"]);
});

test("insertRowsAfter returns false for unknown afterRowId", () => {
    const data = [{ id: "a" }];
    assert.equal(insertRowsAfter(data, "missing", [{ id: "n" }], {}), false);
    assert.deepEqual(data.map((r) => r.id), ["a"]);
});

test("isPlainRowData rejects arrays and null", () => {
    assert.equal(isPlainRowData({ id: 1 }), true);
    assert.equal(isPlainRowData([1]), false);
    assert.equal(isPlainRowData(null), false);
    assert.equal(isPlainRowData("x"), false);
});

test("cloneRowTree + replaceArrayContents roundtrip", () => {
    const data = [{ id: "a", children: [{ id: "c" }] }];
    const snap = cloneRowTree(data);
    data[0].id = "mutated";
    data[0].children[0].id = "mutated-c";
    replaceArrayContents(data, snap);
    assert.deepEqual(data, [{ id: "a", children: [{ id: "c" }] }]);
});

test("computeNudgeToIndex moves one sibling slot incl. merge", () => {
    const list = [
        { id: "a" },
        { id: "h", mergeGroupId: "g", mergeGroupIndex: 0, mergeGroupSize: 2 },
        { id: "t", mergeGroupId: "g", mergeGroupIndex: 1, mergeGroupSize: 2 },
        { id: "z" }
    ];
    const down = computeNudgeToIndex(list, 1, 2, 1);
    const copy = list.map((r) => ({ ...r }));
    assert.equal(reorderSiblingBlock(copy, 1, 2, down), true);
    assert.deepEqual(collectLocalRowIds(copy), ["a", "z", "h", "t"]);

    const up = computeNudgeToIndex(list, 3, 1, -1);
    const copy2 = list.map((r) => ({ ...r }));
    assert.equal(reorderSiblingBlock(copy2, 3, 1, up), true);
    assert.deepEqual(collectLocalRowIds(copy2), ["a", "z", "h", "t"]);
});

test("toolbar preset rows empty without rowCheck", () => {
    const items = resolveToolbarPresetItems({ isRowCheckEnabled: () => false }, ["rows"]);
    assert.equal(items.length, 0);
});

test("toolbar preset rows: move arrows only when rowReorder enabled", () => {
    const base = {
        isRowCheckEnabled: () => true,
        getCheckedRowIds: () => [],
        hasRowCheckAddHook: () => false,
        hasRowCheckDuplicateHook: () => false,
        canNudgeCheckedRow: () => false
    };
    const withoutReorder = resolveToolbarPresetItems({
        ...base,
        isRowReorderEnabled: () => false
    }, ["rows"]);
    assert.ok(withoutReorder.some((i) => i.id === "delete-rows"));
    assert.ok(!withoutReorder.some((i) => i.id === "move-row-up"));

    const withReorder = resolveToolbarPresetItems({
        ...base,
        isRowReorderEnabled: () => true
    }, ["rows"]);
    const ids = withReorder.map((i) => i.id);
    assert.ok(ids.includes("move-row-up"));
    assert.ok(ids.includes("move-row-down"));
    assert.ok(!ids.includes("add-row"));
});

test("ROW_CHECK_COL_ID is reserved system id", () => {
    assert.equal(ROW_CHECK_COL_ID, "__dinext_row_check");
    assert.equal(getStableRowId({ id: "x", _rowId: "1:2" }), "1:2");
});
