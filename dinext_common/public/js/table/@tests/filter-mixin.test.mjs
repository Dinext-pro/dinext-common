import test from "node:test";
import assert from "node:assert/strict";

import { FilterMixin } from "../core/filter/mixin.js";

class FakeTreeBase {
    constructor() {
        this.options = { filter: { enabled: true } };
        this._filterState = { name: "hit" };
        this.rowData = [];
        this.calls = [];
    }

    insertVisibleChildren(rowId) {
        this.calls.push(["insert", rowId]);
    }

    setRowChildren(rowId, children) {
        this.calls.push(["setChildren", rowId, children]);
        this.insertVisibleChildren(rowId);
        return "updated";
    }

    syncVisibleRows() {
        this.calls.push(["sync"]);
        this.rowData = [{ id: "filtered", name: "hit" }];
    }

    setGridOption(key, value) {
        this.calls.push(["grid", key, value]);
    }
}

const FilterTree = FilterMixin(FakeTreeBase);

test("active filter rebuilds projection instead of inserting source rows", () => {
    const table = new FilterTree();

    table.insertVisibleChildren("parent");

    assert.deepEqual(table.calls, [
        ["sync"],
        ["grid", "rowData", [{ id: "filtered", name: "hit" }]]
    ]);
});

test("inactive filter delegates eager insertion to tree layer", () => {
    const table = new FilterTree();
    table._filterState = {};

    table.insertVisibleChildren("parent");

    assert.deepEqual(table.calls, [["insert", "parent"]]);
});

test("lazy children rebuild filtered rows once without eager insertion", () => {
    const table = new FilterTree();
    const children = [{ id: "child" }];

    const result = table.setRowChildren("parent", children);

    assert.equal(result, "updated");
    assert.deepEqual(table.calls, [
        ["setChildren", "parent", children],
        ["sync"],
        ["grid", "rowData", [{ id: "filtered", name: "hit" }]]
    ]);
});
