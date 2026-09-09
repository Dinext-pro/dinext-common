import test from "node:test";
import assert from "node:assert/strict";

import {
    collectDeclaredPinRightLeafs,
    resolveDesiredPinEnd,
    resolvePinEndMode,
    sumDeclaredVisibleLeafWidths,
    sumInjectedColumnWidths
} from "../core/pin-end.js";

const TOTAL_GROUP = {
    headerName: "Итого",
    pinned: "right",
    children: [
        { field: "plan_total", colId: "plan_total", width: 90, pinned: "right" },
        { field: "actual_total", colId: "actual_total", width: 90, pinned: "right" },
        { field: "delta_total", colId: "delta_total", width: 70, hide: true, pinned: "right" }
    ]
};

const FIT_COLUMNS = [
    { field: "name", width: 200 },
    { field: "m1", width: 80 },
    TOTAL_GROUP
];

test("resolvePinEndMode defaults to auto", () => {
    assert.equal(resolvePinEndMode({}), "auto");
    assert.equal(resolvePinEndMode({ pinEnd: {} }), "auto");
    assert.equal(resolvePinEndMode({ pinEnd: { mode: "auto" } }), "auto");
    assert.equal(resolvePinEndMode({ pinEnd: { mode: "always" } }), "always");
});

test("collectDeclaredPinRightLeafs takes the whole group together", () => {
    assert.deepEqual(collectDeclaredPinRightLeafs(FIT_COLUMNS), [
        "plan_total",
        "actual_total",
        "delta_total"
    ]);
});

test("collectDeclaredPinRightLeafs follows group pin when a child omits pinned", () => {
    const columns = [
        { field: "name", width: 120 },
        {
            headerName: "Итого",
            pinned: "right",
            children: [
                { field: "plan_total", width: 80 },
                { field: "actual_total", width: 80 }
            ]
        }
    ];
    assert.deepEqual(collectDeclaredPinRightLeafs(columns), [
        "plan_total",
        "actual_total"
    ]);
});

test("collectDeclaredPinRightLeafs keeps a lone leaf (TSH)", () => {
    const columns = [
        { field: "task", width: 200 },
        { field: "hours", colId: "hours", width: 72, pinned: "right" }
    ];
    assert.deepEqual(collectDeclaredPinRightLeafs(columns), ["hours"]);
});

test("sumDeclaredVisibleLeafWidths skips hidden and uses declared width", () => {
    assert.equal(sumDeclaredVisibleLeafWidths(FIT_COLUMNS), 200 + 80 + 90 + 90);
});

test("sumInjectedColumnWidths adds rowCheck and rowReorder", () => {
    assert.equal(sumInjectedColumnWidths({}), 0);
    assert.equal(sumInjectedColumnWidths({ rowCheck: { enabled: true } }), 36);
    assert.equal(sumInjectedColumnWidths({
        rowCheck: { enabled: true, width: 40 },
        rowReorder: { enabled: true }
    }), 58);
});

test("resolveDesiredPinEnd unpins when declared widths fit", () => {
    const total = sumDeclaredVisibleLeafWidths(FIT_COLUMNS);
    assert.equal(resolveDesiredPinEnd({ totalWidth: total, availableWidth: 500 }), null);
    assert.equal(resolveDesiredPinEnd({ totalWidth: total, availableWidth: 400 }), "right");
});

test("resolveDesiredPinEnd pins on overflow including injected cols", () => {
    const total = sumDeclaredVisibleLeafWidths(FIT_COLUMNS)
        + sumInjectedColumnWidths({ rowCheck: { enabled: true } });
    assert.equal(resolveDesiredPinEnd({ totalWidth: total, availableWidth: 470 }), "right");
    assert.equal(resolveDesiredPinEnd({ totalWidth: total, availableWidth: 500 }), null);
});
