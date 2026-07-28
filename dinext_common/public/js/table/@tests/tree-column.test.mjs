import test from "node:test";
import assert from "node:assert/strict";

import {
    resolveTreeColumnField,
    getFirstLeafColumn,
    findRawColumnByField
} from "../core/tree/model.js";

const columns = [
    { field: "a", headerName: "A" },
    { field: "b", headerName: "B", tree: true },
    { field: "c", headerName: "C" }
];

test("resolveTreeColumnField defaults to first leaf column", () => {
    assert.equal(resolveTreeColumnField([{ field: "a" }, { field: "b" }]), "a");
});

test("resolveTreeColumnField honors tree: true on any column", () => {
    assert.equal(resolveTreeColumnField(columns), "b");
});

test("resolveTreeColumnField honors tree: false on first leaf", () => {
    assert.equal(resolveTreeColumnField([
        { field: "a", tree: false },
        { field: "b", tree: true }
    ]), "b");
});

test("resolveTreeColumnField returns null when first leaf opts out and no tree: true", () => {
    assert.equal(resolveTreeColumnField([
        { field: "a", tree: false },
        { field: "b" }
    ]), null);
});

test("resolveTreeColumnField honors options.treeColumnField", () => {
    assert.equal(resolveTreeColumnField(columns, { treeColumnField: "c" }), "c");
});

test("resolveTreeColumnField walks nested column groups", () => {
    const grouped = [
        {
            headerName: "Group",
            children: [
                { field: "a" },
                { field: "b", tree: true }
            ]
        },
        { field: "c" }
    ];
    assert.equal(resolveTreeColumnField(grouped), "b");
    assert.equal(getFirstLeafColumn(grouped).field, "a");
    assert.equal(findRawColumnByField(grouped, "b").tree, true);
});
