import test from "node:test";
import assert from "node:assert/strict";

import { chainRowClassHandlers, mergeGridOptions } from "../core/shared/utils.js";

test("chainRowClassHandlers merges string and array results", () => {
    const getRowClass = chainRowClassHandlers(
        () => "user-row",
        () => ["a", "b"],
        () => null
    );

    assert.deepEqual(getRowClass({}), ["user-row", "a", "b"]);
});

test("chainRowClassHandlers returns undefined when all empty", () => {
    const getRowClass = chainRowClassHandlers(
        () => null,
        () => []
    );
    assert.equal(getRowClass({}), undefined);
});

test("mergeGridOptions chains getRowClass across parts", () => {
    const merged = mergeGridOptions(
        {
            getRowClass: () => "from-user"
        },
        {
            getRowClass: (params) => (params.summary ? "dinext-table-row--summary" : undefined)
        }
    );

    assert.deepEqual(merged.getRowClass({ summary: true }), [
        "from-user",
        "dinext-table-row--summary"
    ]);
    assert.deepEqual(merged.getRowClass({ summary: false }), ["from-user"]);
});
