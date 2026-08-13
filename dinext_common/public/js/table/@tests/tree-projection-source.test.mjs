import test from "node:test";
import assert from "node:assert/strict";

import { asProjectedMergeGroupRow } from "../core/shared/utils.js";
import { TreeMixin } from "../core/tree/mixin.js";
import { makeMergeHead, makeMergeTail } from "./helpers/fixtures.mjs";

class FakeBase {}

const TestTree = TreeMixin(FakeBase);

test("projected merge heads preserve edit row and resolve tree source head", () => {
    const childHead = makeMergeHead("1.1", 2, { children: [] });
    const childTail = makeMergeTail("1.2", "1.1", 2);
    const head = makeMergeHead("1", 2, { children: [childHead, childTail] });
    const tail = makeMergeTail("2", "1", 2);
    const table = new TestTree();

    table.options = {};
    table.sourceData = [head, tail];
    table.rowData = [
        { ...asProjectedMergeGroupRow(tail, null, "1"), _rowId: "2" },
        {
            ...asProjectedMergeGroupRow(childTail, null, "1.1"),
            _rowId: "2:1.2"
        }
    ];

    assert.equal(table.findSourceRow("2"), tail);
    assert.equal(table.findTreeSourceRow("2"), head);
    assert.equal(table.findSourceRow("2:1.2"), childTail);
    assert.equal(table.findTreeSourceRow("2:1.2"), childHead);
});
