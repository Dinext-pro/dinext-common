import test from "node:test";
import assert from "node:assert/strict";

import {
    clearExpandedDescendantIds,
    collapseTreeRow,
    expandTreeRow,
    resolveTreeChildAddIndex
} from "../core/tree/expand.js";

test("resolveTreeChildAddIndex uses sourceRowIndex not displayed rowIndex", () => {
    assert.equal(
        resolveTreeChildAddIndex({ rowIndex: 2, sourceRowIndex: 47 }, 1),
        48
    );
});

test("resolveTreeChildAddIndex without filter matches displayed+offset", () => {
    assert.equal(
        resolveTreeChildAddIndex({ rowIndex: 5, sourceRowIndex: 5 }, 1),
        6
    );
});

test("resolveTreeChildAddIndex falls back to rowIndex when source missing", () => {
    assert.equal(resolveTreeChildAddIndex({ rowIndex: 3 }, 1), 4);
    assert.equal(resolveTreeChildAddIndex({ rowIndex: 3, sourceRowIndex: -1 }, 1), 4);
    assert.equal(resolveTreeChildAddIndex(null, 1), undefined);
});

test("resolveTreeChildAddIndex merge offset stays on source index", () => {
    assert.equal(
        resolveTreeChildAddIndex({ rowIndex: 1, sourceRowIndex: 10 }, 2),
        12
    );
});

function makeTable({ onExpandRow } = {}) {
    const toggles = [];
    const loadings = [];
    return {
        options: { onExpandRow },
        findSourceRow: (rowId) => ({ id: rowId }),
        setRowLoading: (rowId, loading) => loadings.push({ rowId, loading }),
        refreshTreeToggle: (rowId) => toggles.push(rowId),
        _toggles: toggles,
        _loadings: loadings
    };
}

test("clearExpandedDescendantIds removes nested ids only", () => {
    const ids = new Set(["1", "1:a", "1:a:b", "2", "2:x"]);
    clearExpandedDescendantIds(ids, "1");
    assert.deepEqual([...ids].sort(), ["1", "2", "2:x"]);
});

test("expandTreeRow eager path calls revealChildren({ lazy: false })", async () => {
    const expandedIds = new Set();
    const reveals = [];
    const table = makeTable();

    await expandTreeRow(table, "1", {
        expandedIds,
        getChildren: () => [{ id: "1.1" }],
        revealChildren: (rowId, meta) => reveals.push({ rowId, ...meta })
    });

    assert.equal(expandedIds.has("1"), true);
    assert.deepEqual(reveals, [{ rowId: "1", lazy: false }]);
    assert.deepEqual(table._toggles, ["1"]);
    assert.equal(table._loadings.length, 0);
});

test("expandTreeRow lazy path skips insert reveal and rolls back when empty", async () => {
    const expandedIds = new Set();
    const reveals = [];
    const table = makeTable({
        onExpandRow: async () => {}
    });

    await expandTreeRow(table, "1", {
        expandedIds,
        getChildren: () => [],
        revealChildren: (rowId, meta) => reveals.push({ rowId, ...meta }),
        expandCallbackExtra: { section: "summary" }
    });

    assert.equal(expandedIds.has("1"), false);
    assert.deepEqual(reveals, [{ rowId: "1", lazy: true }]);
    assert.deepEqual(table._loadings, [
        { rowId: "1", loading: true },
        { rowId: "1", loading: false }
    ]);
});

test("expandTreeRow lazy path keeps id when children appear", async () => {
    const expandedIds = new Set();
    let children = [];
    const table = makeTable({
        onExpandRow: async () => {
            children = [{ id: "1.1" }];
        }
    });

    await expandTreeRow(table, "1", {
        expandedIds,
        getChildren: () => children,
        revealChildren: () => {},
        expandCallbackExtra: { section: "summary" }
    });

    assert.equal(expandedIds.has("1"), true);
});

test("expandTreeRow passes expandCallbackExtra to onExpandRow", async () => {
    let payload = null;
    const table = makeTable({
        onExpandRow: async (args) => {
            payload = args;
        }
    });

    await expandTreeRow(table, "sum-1", {
        expandedIds: new Set(),
        getChildren: () => [],
        revealChildren: () => {},
        expandCallbackExtra: { section: "summary" }
    });

    assert.equal(payload.rowId, "sum-1");
    assert.equal(payload.section, "summary");
    assert.equal(payload.table, table);
});

test("collapseTreeRow clears descendants and hides", () => {
    const expandedIds = new Set(["1", "1:a"]);
    const cleared = [];
    const hidden = [];
    const table = makeTable();

    collapseTreeRow(table, "1", {
        expandedIds,
        clearDescendants: (rowId) => {
            cleared.push(rowId);
            clearExpandedDescendantIds(expandedIds, rowId);
        },
        hideDescendants: (rowId) => hidden.push(rowId)
    });

    assert.equal(expandedIds.has("1"), false);
    assert.equal(expandedIds.has("1:a"), false);
    assert.deepEqual(cleared, ["1"]);
    assert.deepEqual(hidden, ["1"]);
    assert.deepEqual(table._toggles, ["1"]);
});
