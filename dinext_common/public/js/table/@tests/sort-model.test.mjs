import test from "node:test";
import assert from "node:assert/strict";

import {
    buildSortAtoms,
    captureSortOrder,
    compareSortValues,
    cycleSortState,
    normalizeSortState,
    patchSortOrderChildren,
    restoreSortOrder,
    sortTreeInPlace,
    sortTreeCopy
} from "../core/sort/model.js";
import { makeMergeHead, makeMergeTail, makeRow } from "./helpers/fixtures.mjs";

test("normalizeSortState drops empty/dupes and defaults dir to asc", () => {
    assert.deepEqual(
        normalizeSortState([
            { field: "a", dir: "desc" },
            { field: "a", dir: "asc" },
            { field: "", dir: "asc" },
            { field: "b" }
        ]),
        [
            { field: "a", dir: "desc" },
            { field: "b", dir: "asc" }
        ]
    );
});

test("compareSortValues numbers and strings", () => {
    assert.ok(compareSortValues(1, 2) < 0);
    assert.ok(compareSortValues("b", "a") > 0);
    assert.equal(compareSortValues(true, false) > 0, true);
});

test("buildSortAtoms keeps merge block together", () => {
    const list = [
        makeMergeHead("1", 2, { name: "B" }),
        makeMergeTail("2", "1", 2, { name: "" }),
        makeRow("3", { name: "A" })
    ];
    const atoms = buildSortAtoms(list);
    assert.equal(atoms.length, 2);
    assert.equal(atoms[0].rows.length, 2);
    assert.equal(atoms[0].head.id, "1");
    assert.equal(atoms[1].head.id, "3");
});

test("sortTreeInPlace sorts siblings and nested children", () => {
    const rows = [
        makeRow("2", {
            name: "B",
            children: [makeRow("2.2", { name: "z" }), makeRow("2.1", { name: "a" })]
        }),
        makeRow("1", { name: "A", children: [] })
    ];
    sortTreeInPlace(rows, [{ field: "name", dir: "asc" }]);
    assert.deepEqual(
        rows.map((r) => r.id),
        ["1", "2"]
    );
    assert.deepEqual(
        rows[1].children.map((r) => r.id),
        ["2.1", "2.2"]
    );
});

test("sortTreeInPlace moves merge atom by head key", () => {
    const rows = [
        makeRow("x", { name: "C" }),
        makeMergeHead("1", 2, { name: "A" }),
        makeMergeTail("2", "1", 2, { name: "Z" }),
        makeRow("y", { name: "B" })
    ];
    sortTreeInPlace(rows, [{ field: "name", dir: "asc" }]);
    assert.deepEqual(
        rows.map((r) => r.id),
        ["1", "2", "y", "x"]
    );
});

test("sort nulls last by default", () => {
    const rows = [
        makeRow("1", { name: null }),
        makeRow("2", { name: "A" }),
        makeRow("3", { name: "" })
    ];
    sortTreeInPlace(rows, [{ field: "name", dir: "asc" }], { sort: { nulls: "last" } });
    assert.deepEqual(
        rows.map((r) => r.id),
        ["2", "1", "3"]
    );
});

test("cycleSortState single column", () => {
    assert.deepEqual(cycleSortState([], "name"), [{ field: "name", dir: "asc" }]);
    assert.deepEqual(cycleSortState([{ field: "name", dir: "asc" }], "name"), [
        { field: "name", dir: "desc" }
    ]);
    assert.deepEqual(cycleSortState([{ field: "name", dir: "desc" }], "name"), []);
    assert.deepEqual(cycleSortState([{ field: "name", dir: "asc" }], "other"), [
        { field: "other", dir: "asc" }
    ]);
});

test("restoreSortOrder after in-place sort returns original tree", () => {
    const rows = [
        makeRow("2", {
            name: "B",
            children: [makeRow("2.2", { name: "z" }), makeRow("2.1", { name: "a" })]
        }),
        makeRow("1", { name: "A", children: [] })
    ];
    const baseline = captureSortOrder(rows);
    sortTreeInPlace(rows, [{ field: "name", dir: "asc" }]);
    sortTreeInPlace(rows, [{ field: "name", dir: "desc" }]);
    restoreSortOrder(rows, baseline);
    assert.deepEqual(
        rows.map((r) => r.id),
        ["2", "1"]
    );
    assert.deepEqual(
        rows[0].children.map((r) => r.id),
        ["2.2", "2.1"]
    );
});

test("restoreSortOrder appends rows missing from snapshot", () => {
    const rows = [makeRow("b", { name: "B" }), makeRow("a", { name: "A" })];
    const baseline = captureSortOrder(rows);
    rows.push(makeRow("c", { name: "C" }));
    sortTreeInPlace(rows, [{ field: "name", dir: "asc" }]);
    restoreSortOrder(rows, baseline);
    assert.deepEqual(
        rows.map((r) => r.id),
        ["b", "a", "c"]
    );
});

test("patchSortOrderChildren records lazy-loaded sibling order", () => {
    const rows = [makeRow("p", { name: "P", children: [] })];
    const baseline = captureSortOrder(rows);
    const incoming = [makeRow("z", { name: "Z" }), makeRow("a", { name: "A" })];
    patchSortOrderChildren(baseline, "p", incoming);
    rows[0].children = incoming.slice();
    sortTreeInPlace(rows[0].children, [{ field: "name", dir: "asc" }]);
    restoreSortOrder(rows, baseline);
    assert.deepEqual(
        rows[0].children.map((r) => r.id),
        ["z", "a"]
    );
});

test("sortTreeCopy does not mutate original", () => {
    const rows = [makeRow("2", { name: "B" }), makeRow("1", { name: "A" })];
    const copy = sortTreeCopy(rows, [{ field: "name", dir: "asc" }]);
    assert.deepEqual(
        rows.map((r) => r.id),
        ["2", "1"]
    );
    assert.deepEqual(
        copy.map((r) => r.id),
        ["1", "2"]
    );
});
