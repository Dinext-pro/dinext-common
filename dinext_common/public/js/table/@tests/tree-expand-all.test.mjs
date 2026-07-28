import test from "node:test";
import assert from "node:assert/strict";

import { collectExpandableRowIds } from "../core/tree/model.js";

test("collectExpandableRowIds returns depth-first expandable ids", () => {
    const data = [
        {
            id: "p1",
            children: [
                { id: "c1", children: [{ id: "g1" }] },
                { id: "c2" }
            ]
        },
        { id: "p2", hasChildren: true }
    ];

    assert.deepEqual(collectExpandableRowIds(data), ["p1", "p1:c1", "p2"]);
});

test("collectExpandableRowIds includes lazy hasChildren markers", () => {
    const data = [{ id: "lazy", hasChildren: true }];
    assert.deepEqual(collectExpandableRowIds(data), ["lazy"]);
});
