import test from "node:test";
import assert from "node:assert/strict";

import { FilterMixin } from "../core/filter/mixin.js";

class FakeTreeBase {
    constructor() {
        this.options = { filter: { enabled: true } };
        this._filterState = { name: "hit" };
        this.rowData = [];
        this.sourceData = [];
        this.calls = [];
        this.api = {
            onFilterChanged: () => {
                this.calls.push(["filterChanged"]);
            }
        };
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

test("active filter inserts children then notifies AG external filter", () => {
    const table = new FilterTree();

    table.insertVisibleChildren("parent");

    assert.deepEqual(table.calls, [
        ["insert", "parent"],
        ["filterChanged"]
    ]);
});

test("inactive filter delegates eager insertion to tree layer", () => {
    const table = new FilterTree();
    table._filterState = {};

    table.insertVisibleChildren("parent");

    assert.deepEqual(table.calls, [["insert", "parent"]]);
});

test("lazy children notify AG filter once without replacing rowData", () => {
    const table = new FilterTree();
    const children = [{ id: "child" }];

    const result = table.setRowChildren("parent", children);

    assert.equal(result, "updated");
    assert.deepEqual(table.calls, [
        ["setChildren", "parent", children],
        ["insert", "parent"],
        ["filterChanged"]
    ]);
});

test("applyFilterToGrid uses onFilterChanged instead of replacing rowData", () => {
    const table = new FilterTree();
    table.rowData = [
        { id: "a", name: "hit" },
        { id: "b", name: "miss" }
    ];
    table.sourceData = table.rowData;

    table.applyFilterToGrid();

    assert.deepEqual(table.calls, [["filterChanged"]]);
    assert.ok(table._filterPassIds.has("a"));
    assert.equal(table._filterPassIds.has("b"), false);
});
