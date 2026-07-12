import test from "node:test";
import assert from "node:assert/strict";

import {
    buildSelectionStats,
    formatSelectionStatusText,
    resolveNumericCellValue
} from "../core/selection/status.js";

test("resolveNumericCellValue parses raw and formatted numbers", () => {
    assert.equal(resolveNumericCellValue(12.5, ""), 12.5);
    assert.equal(resolveNumericCellValue("1,5", ""), 1.5);
    assert.equal(resolveNumericCellValue("n/a", "2 500,75"), 2500.75);
    assert.equal(resolveNumericCellValue("text", "text"), null);
});

test("buildSelectionStats computes sum average min max", () => {
    assert.deepEqual(buildSelectionStats([10, 20, 30], 4), {
        cellCount: 4,
        numericCount: 3,
        sum: 60,
        average: 20,
        min: 10,
        max: 30
    });
});

test("formatSelectionStatusText matches Excel-like default metrics", () => {
    const stats = buildSelectionStats([10, 20], 3);
    assert.equal(
        formatSelectionStatusText(stats, ["average", "count", "sum"]),
        "Average: 15 | Count: 3 | Sum: 30"
    );
});

test("formatSelectionStatusText shows only count when no numeric cells", () => {
    const stats = buildSelectionStats([], 2);
    assert.equal(
        formatSelectionStatusText(stats, ["average", "count", "sum"]),
        "Count: 2"
    );
});

test("formatSelectionStatusText supports min max metrics", () => {
    const stats = buildSelectionStats([5, 15], 2);
    assert.equal(
        formatSelectionStatusText(stats, ["min", "max", "count"]),
        "Min: 5 | Max: 15 | Count: 2"
    );
});
