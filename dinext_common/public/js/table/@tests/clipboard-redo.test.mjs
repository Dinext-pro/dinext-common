import test from "node:test";
import assert from "node:assert/strict";

import { createCommandStack, buildCellChangeCommand, tileMatrixToSelection } from "../core/selection/clipboard.js";
import { resolveToolbarItems } from "../core/toolbar/presets.js";
import { CELL_CHANGE_SOURCES } from "../core/edit/changes.js";

test("createCommandStack supports redo after undo", () => {
    const stack = createCommandStack(20);
    let value = 1;

    stack.push({
        execute: () => { value = 2; },
        undo: () => { value = 1; }
    });
    value = 2;

    assert.equal(stack.redo(), false);
    assert.equal(stack.undo(), true);
    assert.equal(value, 1);
    assert.equal(stack.redo(), true);
    assert.equal(value, 2);
});

test("buildCellChangeCommand undo/redo restores values in LIFO order", () => {
    const data = { a: 1, b: 2, c: 3 };
    const node = { data };
    const entries = [{
        node,
        field: "a",
        oldValue: 1,
        newValue: 10,
        rowIndex: 0,
        colId: "a"
    }];

    const commits = [];
    const table = {
        computeRangeFromRawChanges: () => ({ minRowIndex: 0, maxRowIndex: 0 }),
        commitCellChanges(payload) {
            commits.push(payload);
            if (payload.alreadyApplied === false) {
                for (const change of payload.changes) {
                    change.node.data[change.field] = change.newValue;
                }
            }
            return { applied: payload.changes.length, entries: payload.changes };
        }
    };

    const stack = createCommandStack(20);
    const command = buildCellChangeCommand(table, entries, { minRowIndex: 0, maxRowIndex: 0 });
    stack.push(command);
    command.execute();
    assert.equal(data.a, 10);

    stack.push({
        undo: () => { data.b = 1; },
        execute: () => { data.b = 2; }
    });
    data.b = 2;

    assert.equal(stack.undo(), true);
    assert.equal(data.b, 1);

    assert.equal(stack.undo(), true);
    assert.equal(data.a, 1);

    assert.equal(stack.redo(), true);
    assert.equal(data.a, 10);
    assert.equal(commits.at(-1).source, CELL_CHANGE_SOURCES.REDO);
});

test("tileMatrixToSelection repeats a single value across the selection", () => {
    const bounds = { minRowIndex: 0, maxRowIndex: 2, minColIndex: 1, maxColIndex: 3 };
    assert.deepEqual(tileMatrixToSelection([["8"]], bounds), [
        ["8", "8", "8"],
        ["8", "8", "8"],
        ["8", "8", "8"]
    ]);
});

test("tileMatrixToSelection keeps a block pasted onto a single cell", () => {
    const matrix = [["1", "2"], ["3", "4"]];
    const bounds = { minRowIndex: 4, maxRowIndex: 4, minColIndex: 0, maxColIndex: 0 };
    assert.equal(tileMatrixToSelection(matrix, bounds), matrix);
});

test("tileMatrixToSelection repeats a block when the selection is an exact multiple", () => {
    const bounds = { minRowIndex: 0, maxRowIndex: 3, minColIndex: 0, maxColIndex: 1 };
    assert.deepEqual(tileMatrixToSelection([["1", "2"], ["3", "4"]], bounds), [
        ["1", "2"],
        ["3", "4"],
        ["1", "2"],
        ["3", "4"]
    ]);
});

test("tileMatrixToSelection does not stretch a block that does not divide the selection", () => {
    const matrix = [["1", "2"], ["3", "4"]];
    const bounds = { minRowIndex: 0, maxRowIndex: 2, minColIndex: 0, maxColIndex: 2 };
    assert.equal(tileMatrixToSelection(matrix, bounds), matrix);
});

test("default toolbar exposes history, filter (auto), optional tree, and fullscreen", () => {
    const filterItem = {
        id: "filter",
        title: "Filter columns",
        iconSvg: "<svg></svg>",
        onClick: () => {}
    };
    const flatTable = {
        options: { edit: true },
        isUndoRedoEnabled: () => true,
        hasNestedRows: () => false,
        getFilterToolbarItems: () => [filterItem],
        isFullscreenEnabled: () => true,
        isFullscreen: () => false
    };

    const flatItems = resolveToolbarItems(flatTable, { items: [] });
    assert.ok(flatItems.some(item => item.id === "undo"));
    assert.ok(flatItems.some(item => item.id === "redo"));
    assert.ok(flatItems.some(item => item.id === "filter"));
    assert.ok(!flatItems.some(item => item.id === "expand-all"));
    assert.ok(!flatItems.some(item => item.id === "copy"));
    assert.ok(flatItems.some(item => item.id === "fullscreen"));

    const treeTable = {
        ...flatTable,
        hasNestedRows: () => true,
        expandAll: () => {},
        collapseAll: () => {}
    };
    const treeItems = resolveToolbarItems(treeTable, { items: [] });
    assert.ok(treeItems.some(item => item.id === "expand-all"));
    assert.ok(treeItems.some(item => item.id === "collapse-all"));
    assert.ok(treeItems.some(item => item.id === "filter"));
});

test("clipboard preset remains opt-in without undo buttons", () => {
    const table = {
        options: { edit: true },
        isClipboardEnabled: () => true,
        isFullscreenEnabled: () => false
    };

    const items = resolveToolbarItems(table, { presets: ["clipboard"], items: [] });
    assert.ok(items.some(item => item.id === "copy"));
    assert.ok(!items.some(item => item.id === "undo"));
});

test("resolveToolbarItems places fullscreen preset on the end group", () => {
    const table = {
        options: { edit: true },
        isUndoRedoEnabled: () => true,
        hasNestedRows: () => false,
        isFullscreenEnabled: () => true,
        isFullscreen: () => false
    };

    const items = resolveToolbarItems(table, { presets: ["history", "fullscreen"], items: [] });
    const endItems = items.filter(item => item.align === "end");
    const primaryItems = items.filter(item => item.align !== "end");

    assert.ok(primaryItems.some(item => item.id === "undo"));
    assert.ok(endItems.some(item => item.id === "fullscreen"));
    assert.ok(endItems.some(item => item.id === "exit-fullscreen"));
    assert.equal(endItems.every(item => item.align === "end"), true);
});

test("resolveToolbarItems puts domain items in custom zone after filter, before end", () => {
    const filterItem = {
        id: "filter",
        title: "Filter columns",
        iconSvg: "<svg></svg>",
        onClick: () => {}
    };
    const table = {
        options: { edit: true },
        isUndoRedoEnabled: () => true,
        hasNestedRows: () => false,
        getFilterToolbarItems: () => [filterItem],
        isFullscreenEnabled: () => true,
        isFullscreen: () => false
    };

    const items = resolveToolbarItems(table, {
        presets: ["history", "fullscreen"],
        items: [{ id: "domain", label: "Domain" }]
    });

    const undoIndex = items.findIndex(item => item.id === "undo");
    const filterIndex = items.findIndex(item => item.id === "filter");
    const domainIndex = items.findIndex(item => item.id === "domain");
    const fullscreenIndex = items.findIndex(item => item.id === "fullscreen");
    assert.ok(undoIndex >= 0);
    assert.ok(filterIndex > undoIndex);
    assert.ok(domainIndex > filterIndex);
    assert.ok(fullscreenIndex > domainIndex);
    assert.equal(items[domainIndex].zone, "custom");
});
