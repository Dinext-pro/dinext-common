import test from "node:test";
import assert from "node:assert/strict";

import {
    CELL_CHANGE_SOURCES,
    computeRangeFromChanges,
    toPublicCellChange,
    toPublicCellChanges
} from "../core/edit-changes.js";

test("computeRangeFromChanges returns null for empty input", () => {
    assert.equal(computeRangeFromChanges([]), null);
    assert.equal(computeRangeFromChanges(null), null);
});

test("computeRangeFromChanges builds row/col bounding box", () => {
    const range = computeRangeFromChanges([
        { rowId: "1", rowIndex: 0, colId: "a", colIndex: 0, field: "a" },
        { rowId: "2", rowIndex: 1, colId: "b", colIndex: 1, field: "b" }
    ]);

    assert.deepEqual(range, {
        startRowId: "1",
        endRowId: "2",
        startColId: "a",
        endColId: "b",
        minRowIndex: 0,
        maxRowIndex: 1,
        minColIndex: 0,
        maxColIndex: 1
    });
});

test("toPublicCellChange strips internal node handles", () => {
    const publicChange = toPublicCellChange({
        node: { rowIndex: 5 },
        rowId: "10",
        rowIndex: 5,
        colId: "c",
        field: "c",
        oldValue: 1,
        newValue: 2,
        row: { id: "10", c: 2 }
    });

    assert.deepEqual(publicChange, {
        rowId: "10",
        rowIndex: 5,
        colId: "c",
        field: "c",
        oldValue: 1,
        newValue: 2,
        row: { id: "10", c: 2 },
        section: "body"
    });
    assert.equal("node" in publicChange, false);
});

test("toPublicCellChanges maps arrays", () => {
    assert.equal(toPublicCellChanges([{ rowId: "1", field: "a" }]).length, 1);
});

test("toPublicCellChange includes summary section", () => {
    const change = toPublicCellChange({
        rowId: "total",
        field: "amount",
        row: { id: "total", _section: "summary", amount: 10 }
    });
    assert.equal(change.section, "summary");
});

test("CELL_CHANGE_SOURCES includes edit and paste", () => {
    assert.equal(CELL_CHANGE_SOURCES.EDIT, "edit");
    assert.equal(CELL_CHANGE_SOURCES.PASTE, "paste");
    assert.equal(CELL_CHANGE_SOURCES.UNDO, "undo");
});
