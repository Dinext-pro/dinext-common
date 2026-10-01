import test from "node:test";
import assert from "node:assert/strict";

import { ROW_CHECK_COL_ID } from "../core/row-check/constants.js";
import { ROW_REORDER_COL_ID } from "../core/row-reorder/constants.js";
import {
    applySavedColumnWidths,
    getColumnWidthStorageKey,
    mergeColumnWidths,
    parseColumnWidthRaw,
    resolveColumnWidthEntityKey,
    serializeColumnWidths
} from "../core/column-width/model.js";

test("entity key is toolbar persistKey before first colon", () => {
    assert.equal(
        resolveColumnWidthEntityKey({ toolbar: { persistKey: "work-efforts:PROJ-001" } }),
        "work-efforts"
    );
    assert.equal(
        resolveColumnWidthEntityKey({ toolbar: { persistKey: "task-tree-gantt:PRJ:TASK-1" } }),
        "task-tree-gantt"
    );
    assert.equal(
        resolveColumnWidthEntityKey({ toolbar: { persistKey: "workload-reports-project" } }),
        "workload-reports-project"
    );
});

test("explicit columnWidth.persistKey wins", () => {
    assert.equal(
        resolveColumnWidthEntityKey({
            toolbar: { persistKey: "work-efforts:PROJ-001" },
            columnWidth: { persistKey: "work-efforts-report" }
        }),
        "work-efforts-report"
    );
});

test("persist off or missing key saves nothing", () => {
    assert.equal(
        resolveColumnWidthEntityKey({
            toolbar: { persistKey: "user-timesheet:TS-1" },
            columnWidth: { persist: false }
        }),
        null
    );
    assert.equal(resolveColumnWidthEntityKey({}), null);
    assert.equal(resolveColumnWidthEntityKey({ toolbar: { persistKey: "  :doc" } }), null);
});

test("storage key is separate from toolbar snapshot", () => {
    assert.equal(getColumnWidthStorageKey("work-efforts"), "dinext-table:columns:work-efforts");
    assert.equal(getColumnWidthStorageKey(""), null);
    assert.equal(getColumnWidthStorageKey(null), null);
});

test("parse drops system cols, junk, and non-positive widths", () => {
    const raw = JSON.stringify({
        task: 240.4,
        [ROW_CHECK_COL_ID]: 36,
        [ROW_REORDER_COL_ID]: 18,
        empty: 0,
        bad: "x"
    });
    assert.deepEqual(parseColumnWidthRaw(raw), { task: 240 });
    assert.deepEqual(parseColumnWidthRaw("{"), {});
    assert.deepEqual(parseColumnWidthRaw("[]"), {});
});

test("merge keeps prior cols and skips system ids", () => {
    const next = mergeColumnWidths(
        { task: 200, subject: 180 },
        { task: 260, [ROW_CHECK_COL_ID]: 40 }
    );
    assert.deepEqual(next, { task: 260, subject: 180 });
    assert.equal(serializeColumnWidths(next), JSON.stringify({ task: 260, subject: 180 }));
});

test("saved width clears flex on matching leaf and nested child", () => {
    const defs = applySavedColumnWidths([
        { field: "subject", flex: 1, minWidth: 80 },
        { field: "status", width: 90 },
        {
            headerName: "Dates",
            children: [{ field: "start", flex: 1 }]
        },
        { colId: ROW_CHECK_COL_ID, width: 36 }
    ], { subject: 320, start: 110 });

    assert.equal(defs[0].width, 320);
    assert.equal("flex" in defs[0], false);
    assert.equal(defs[0].minWidth, 80);
    assert.equal(defs[1].width, 90);
    assert.equal(defs[2].children[0].width, 110);
    assert.equal("flex" in defs[2].children[0], false);
    assert.equal(defs[3].width, 36);
});
