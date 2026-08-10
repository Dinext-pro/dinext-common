import test from "node:test";
import assert from "node:assert/strict";

import {
    columnsAllowEdit,
    isCheckboxColumnDef,
    resolveClickWhenActiveEnabled,
    selectionBlocksClickWhenActive,
    shouldStartEditOnActiveClick,
    snapshotFocusedCell
} from "../core/edit/click-when-active.js";

function mouse({
    detail = 1,
    button = 0,
    shiftKey = false,
    ctrlKey = false,
    metaKey = false,
    altKey = false
} = {}) {
    return { detail, button, shiftKey, ctrlKey, metaKey, altKey };
}

test("columnsAllowEdit walks nested column groups", () => {
    assert.equal(columnsAllowEdit([{ field: "a" }]), false);
    assert.equal(columnsAllowEdit([{ field: "a", edit: true }]), true);
    assert.equal(columnsAllowEdit([{ children: [{ field: "b", edit: () => true }] }]), true);
    assert.equal(columnsAllowEdit([{ field: "a", edit: false }]), false);
});

test("resolveClickWhenActiveEnabled defaults from edit availability", () => {
    assert.equal(resolveClickWhenActiveEnabled({ edit: true }, []), true);
    assert.equal(resolveClickWhenActiveEnabled({ edit: false }, [{ field: "a", edit: true }]), true);
    assert.equal(resolveClickWhenActiveEnabled({}, [{ field: "a" }]), false);
    assert.equal(resolveClickWhenActiveEnabled({ clickWhenActive: false, edit: true }, []), false);
    assert.equal(resolveClickWhenActiveEnabled({ clickWhenActive: true }, []), true);
});

test("isCheckboxColumnDef covers presets and AG editors", () => {
    assert.equal(isCheckboxColumnDef({ type: "checkbox" }), true);
    assert.equal(isCheckboxColumnDef({ type: ["boolean"] }), true);
    assert.equal(isCheckboxColumnDef({ cellEditor: "agCheckboxCellEditor" }), true);
    assert.equal(isCheckboxColumnDef({ cellDataType: "boolean" }), true);
    assert.equal(isCheckboxColumnDef({ field: "hours" }), false);
});

test("selectionBlocksClickWhenActive only multi cell / multi range", () => {
    assert.equal(selectionBlocksClickWhenActive([]), false);
    assert.equal(selectionBlocksClickWhenActive([
        { startRowId: "1", endRowId: "1", startColId: "a", endColId: "a" }
    ]), false);
    assert.equal(selectionBlocksClickWhenActive([
        { startRowId: "1", endRowId: "2", startColId: "a", endColId: "a" }
    ]), true);
    assert.equal(selectionBlocksClickWhenActive([
        { startRowId: "1", endRowId: "1", startColId: "a", endColId: "a" },
        { startRowId: "2", endRowId: "2", startColId: "b", endColId: "b" }
    ]), true);
});

test("shouldStartEditOnActiveClick: second plain click on same focused cell", () => {
    assert.equal(shouldStartEditOnActiveClick({
        focusedBeforePointer: { rowIndex: 2, colId: "hours" },
        rowIndex: 2,
        colId: "hours",
        domEvent: mouse(),
        isEditable: true
    }), true);
});

test("shouldStartEditOnActiveClick: first click (focus was elsewhere) is select only", () => {
    assert.equal(shouldStartEditOnActiveClick({
        focusedBeforePointer: { rowIndex: 0, colId: "a" },
        rowIndex: 2,
        colId: "hours",
        domEvent: mouse(),
        isEditable: true
    }), false);
    assert.equal(shouldStartEditOnActiveClick({
        focusedBeforePointer: null,
        rowIndex: 2,
        colId: "hours",
        domEvent: mouse(),
        isEditable: true
    }), false);
});

test("shouldStartEditOnActiveClick: skips dblclick half, modifiers, checkbox, range", () => {
    const base = {
        focusedBeforePointer: { rowIndex: 1, colId: "x" },
        rowIndex: 1,
        colId: "x",
        isEditable: true
    };
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse({ detail: 2 }) }), false);
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse({ shiftKey: true }) }), false);
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse({ ctrlKey: true }) }), false);
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse(), isEditing: true }), false);
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse(), isEditable: false }), false);
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse(), isCheckboxColumn: true }), false);
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse(), selectionBlocks: true }), false);
    assert.equal(shouldStartEditOnActiveClick({ ...base, domEvent: mouse(), targetIsFillHandle: true }), false);
});

test("snapshotFocusedCell reads AG Grid focused cell shape", () => {
    assert.equal(snapshotFocusedCell(null), null);
    assert.equal(snapshotFocusedCell({ getFocusedCell: () => null }), null);
    assert.deepEqual(snapshotFocusedCell({
        getFocusedCell: () => ({
            rowIndex: 3,
            column: { getColId: () => "role" }
        })
    }), { rowIndex: 3, colId: "role" });
});
