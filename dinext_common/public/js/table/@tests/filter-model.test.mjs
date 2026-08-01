import test from "node:test";
import assert from "node:assert/strict";

import {
    FILTER_KINDS,
    FILTER_OPS,
    filterFlatRows,
    filterTreeRows,
    isFilterStateEmpty,
    normalizeFilterState,
    parseFilterQuery,
    resolveFilterKind,
    rowMatchesFilter,
    valueMatchesQuery
} from "../core/filter/model.js";
import { makeMergeHead, makeMergeTail, makeRow } from "./helpers/fixtures.mjs";

test("normalizeFilterState drops empty/blank and trims", () => {
    assert.deepEqual(
        normalizeFilterState({
            name: "  Foo  ",
            empty: "",
            spaces: "   ",
            nil: null,
            zero: 0,
            "": "x"
        }),
        { name: "Foo", zero: "0" }
    );
    assert.deepEqual(normalizeFilterState(null), {});
    assert.deepEqual(normalizeFilterState([]), {});
});

test("isFilterStateEmpty", () => {
    assert.equal(isFilterStateEmpty({}), true);
    assert.equal(isFilterStateEmpty({ a: "x" }), false);
});

test("resolveFilterKind from column type", () => {
    assert.equal(resolveFilterKind({ type: "number" }), FILTER_KINDS.NUMBER);
    assert.equal(resolveFilterKind({ type: "integer" }), FILTER_KINDS.NUMBER);
    assert.equal(resolveFilterKind({ type: "date" }), FILTER_KINDS.DATE);
    assert.equal(resolveFilterKind({ type: "text" }), FILTER_KINDS.TEXT);
    assert.equal(resolveFilterKind({}), FILTER_KINDS.TEXT);
});

test("parseFilterQuery number compare ops", () => {
    assert.deepEqual(parseFilterQuery(">1", FILTER_KINDS.NUMBER), {
        op: FILTER_OPS.GT,
        operand: "1"
    });
    assert.deepEqual(parseFilterQuery(">= 10", FILTER_KINDS.NUMBER), {
        op: FILTER_OPS.GTE,
        operand: "10"
    });
    assert.deepEqual(parseFilterQuery("<>2", FILTER_KINDS.NUMBER), {
        op: FILTER_OPS.NE,
        operand: "2"
    });
    assert.deepEqual(parseFilterQuery("!=2", FILTER_KINDS.NUMBER), {
        op: FILTER_OPS.NE,
        operand: "2"
    });
    assert.deepEqual(parseFilterQuery("<=-5", FILTER_KINDS.NUMBER), {
        op: FILTER_OPS.LTE,
        operand: "-5"
    });
});

test("parseFilterQuery text ops; > stays contains", () => {
    assert.deepEqual(parseFilterQuery(">1", FILTER_KINDS.TEXT), {
        op: FILTER_OPS.CONTAINS,
        operand: ">1"
    });
    assert.deepEqual(parseFilterQuery("=Exact", FILTER_KINDS.TEXT), {
        op: FILTER_OPS.EQ,
        operand: "Exact"
    });
    assert.deepEqual(parseFilterQuery("!foo", FILTER_KINDS.TEXT), {
        op: FILTER_OPS.NOT_CONTAINS,
        operand: "foo"
    });
    assert.deepEqual(parseFilterQuery("-bar", FILTER_KINDS.TEXT), {
        op: FILTER_OPS.NOT_CONTAINS,
        operand: "bar"
    });
    assert.deepEqual(parseFilterQuery('">1"', FILTER_KINDS.TEXT), {
        op: FILTER_OPS.CONTAINS,
        operand: ">1",
        literal: true
    });
});

test("valueMatchesQuery case-insensitive contains", () => {
    assert.equal(valueMatchesQuery("Hello World", "world"), true);
    assert.equal(valueMatchesQuery("Hello", "xyz"), false);
    assert.equal(valueMatchesQuery(null, "a"), false);
    assert.equal(valueMatchesQuery("x", ""), true);
    assert.equal(valueMatchesQuery(42, "4"), true);
});

test("valueMatchesQuery number operators", () => {
    assert.equal(valueMatchesQuery(5, ">1", FILTER_KINDS.NUMBER), true);
    assert.equal(valueMatchesQuery(5, ">10", FILTER_KINDS.NUMBER), false);
    assert.equal(valueMatchesQuery(2, "<>2", FILTER_KINDS.NUMBER), false);
    assert.equal(valueMatchesQuery(3, "<>2", FILTER_KINDS.NUMBER), true);
    assert.equal(valueMatchesQuery(10, ">=10", FILTER_KINDS.NUMBER), true);
    assert.equal(valueMatchesQuery(-3, "<=-1", FILTER_KINDS.NUMBER), true);
    assert.equal(valueMatchesQuery("12.5", "<13", FILTER_KINDS.NUMBER), true);
    assert.equal(valueMatchesQuery(5, ">abc", FILTER_KINDS.NUMBER), false);
    assert.equal(valueMatchesQuery(null, ">0", FILTER_KINDS.NUMBER), false);
});

test("valueMatchesQuery date operators", () => {
    assert.equal(valueMatchesQuery("2024-06-01", ">=2024-01-01", FILTER_KINDS.DATE), true);
    assert.equal(valueMatchesQuery("2024-06-01", "<2024-01-01", FILTER_KINDS.DATE), false);
    assert.equal(valueMatchesQuery("01.06.2024", "=2024-06-01", FILTER_KINDS.DATE), true);
});

test("valueMatchesQuery text = / ! ", () => {
    assert.equal(valueMatchesQuery("Alpha", "=alpha", FILTER_KINDS.TEXT), true);
    assert.equal(valueMatchesQuery("Alpha", "=alp", FILTER_KINDS.TEXT), false);
    assert.equal(valueMatchesQuery("Alpha", "!alp", FILTER_KINDS.TEXT), false);
    assert.equal(valueMatchesQuery("Alpha", "!zzz", FILTER_KINDS.TEXT), true);
    assert.equal(valueMatchesQuery("x>1", '">1"', FILTER_KINDS.TEXT), true);
});

test("rowMatchesFilter uses column types from options", () => {
    const row = makeRow("1", { name: "Alpha", hours: 8 });
    const options = {
        columns: [
            { field: "name", type: "text" },
            { field: "hours", type: "number" }
        ]
    };
    assert.equal(rowMatchesFilter(row, { hours: ">5" }, options), true);
    assert.equal(rowMatchesFilter(row, { hours: ">20" }, options), false);
    assert.equal(rowMatchesFilter(row, { name: ">5" }, options), false);
    assert.equal(rowMatchesFilter(row, { name: "alp", hours: ">=8" }, options), true);
});

test("rowMatchesFilter AND across fields", () => {
    const row = makeRow("1", { name: "Alpha", code: "A1" });
    assert.equal(rowMatchesFilter(row, { name: "alp", code: "a1" }), true);
    assert.equal(rowMatchesFilter(row, { name: "alp", code: "b" }), false);
    assert.equal(rowMatchesFilter(row, {}), true);
});

test("filterFlatRows keeps merge atom when any row matches", () => {
    const rows = [
        makeMergeHead("1", 2, { name: "Alpha" }),
        makeMergeTail("2", "1", 2, { name: "HiddenTail" }),
        makeRow("3", { name: "Beta" })
    ];
    const byTail = filterFlatRows(rows, { name: "hiddentail" });
    assert.deepEqual(
        byTail.map((r) => r.id),
        ["1", "2"]
    );

    const byHead = filterFlatRows(rows, { name: "alpha" });
    assert.deepEqual(
        byHead.map((r) => r.id),
        ["1", "2"]
    );

    const none = filterFlatRows(rows, { name: "zzz" });
    assert.deepEqual(none, []);
});

test("filterFlatRows number op with column type", () => {
    const rows = [
        makeRow("1", { hours: 2 }),
        makeRow("2", { hours: 10 }),
        makeRow("3", { hours: 5 })
    ];
    const options = { columns: [{ field: "hours", type: "number" }] };
    assert.deepEqual(
        filterFlatRows(rows, { hours: ">5" }, options).map((r) => r.id),
        ["2"]
    );
});

test("filterFlatRows does not recurse children", () => {
    const rows = [
        makeRow("1", {
            name: "Parent",
            children: [makeRow("1.1", { name: "ChildMatch" })]
        }),
        makeRow("2", { name: "Other" })
    ];
    const filtered = filterFlatRows(rows, { name: "childmatch" });
    assert.deepEqual(filtered.map((r) => r.id), []);
});

test("filterTreeRows keeps match + ancestors and expandIds", () => {
    const rows = [
        makeRow("1", {
            name: "Parent",
            children: [
                makeRow("1.1", { name: "ChildMatch" }),
                makeRow("1.2", { name: "Sibling" })
            ]
        }),
        makeRow("2", { name: "Other" })
    ];
    const { rows: pruned, expandIds } = filterTreeRows(rows, { name: "childmatch" });
    assert.deepEqual(pruned.map((r) => r.id), ["1"]);
    assert.deepEqual(pruned[0].children.map((r) => r.id), ["1.1"]);
    assert.ok(expandIds.has("1"));
    assert.equal(expandIds.has("1:1.1"), false);
});

test("filterTreeRows keeps merge atom when child under head matches", () => {
    const head = makeMergeHead("1", 2, {
        name: "Head",
        children: [makeRow("1.1", { name: "NestedHit" })]
    });
    const tail = makeMergeTail("2", "1", 2, { name: "Tail" });
    const { rows: pruned, expandIds } = filterTreeRows([head, tail], { name: "nestedhit" });
    assert.deepEqual(pruned.map((r) => r.id), ["1", "2"]);
    assert.deepEqual(pruned[0].children.map((r) => r.id), ["1.1"]);
    assert.ok(expandIds.has("1"));
});
