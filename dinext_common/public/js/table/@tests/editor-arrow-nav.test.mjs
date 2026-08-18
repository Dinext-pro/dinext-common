import test from "node:test";
import assert from "node:assert/strict";

import {
    isArrowKey,
    isCaretEditorTarget,
    isEditorArrowNavTarget,
    isEditorGuardKey,
    isSelectEditorTarget,
    shouldSuppressEditorArrowNav,
    stopEditorArrowNavPropagation
} from "../core/edit/keyboard.js";

function el(tag, extras = {}) {
    return { tagName: tag, isContentEditable: false, type: undefined, ...extras };
}

test("isArrowKey only arrows", () => {
    assert.equal(isArrowKey("ArrowLeft"), true);
    assert.equal(isArrowKey("ArrowRight"), true);
    assert.equal(isArrowKey("ArrowUp"), true);
    assert.equal(isArrowKey("ArrowDown"), true);
    assert.equal(isArrowKey("Tab"), false);
    assert.equal(isArrowKey("Enter"), false);
    assert.equal(isArrowKey("Backspace"), false);
    assert.equal(isArrowKey("Delete"), false);
});

test("isEditorGuardKey: arrows + Backspace/Delete, not Tab/Enter/Esc", () => {
    assert.equal(isEditorGuardKey("ArrowLeft"), true);
    assert.equal(isEditorGuardKey("Backspace"), true);
    assert.equal(isEditorGuardKey("Delete"), true);
    assert.equal(isEditorGuardKey("Tab"), false);
    assert.equal(isEditorGuardKey("Enter"), false);
    assert.equal(isEditorGuardKey("Escape"), false);
});

test("caret editors: text / date / number / textarea / contenteditable", () => {
    assert.equal(isCaretEditorTarget(el("INPUT", { type: "text" })), true);
    assert.equal(isCaretEditorTarget(el("INPUT", { type: "date" })), true);
    assert.equal(isCaretEditorTarget(el("INPUT", { type: "number" })), true);
    assert.equal(isCaretEditorTarget(el("INPUT")), true);
    assert.equal(isCaretEditorTarget(el("TEXTAREA")), true);
    assert.equal(isCaretEditorTarget(el("DIV", { isContentEditable: true })), true);
    assert.equal(isCaretEditorTarget(el("INPUT", { type: "checkbox" })), false);
    assert.equal(isCaretEditorTarget(el("INPUT", { type: "button" })), false);
    assert.equal(isCaretEditorTarget(el("DIV")), false);
});

test("select is editor target, not caret", () => {
    const select = el("SELECT");
    assert.equal(isSelectEditorTarget(select), true);
    assert.equal(isCaretEditorTarget(select), false);
    assert.equal(isEditorArrowNavTarget(select), true);
});

test("shouldSuppressEditorArrowNav: input / select / editing", () => {
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "ArrowLeft", target: el("INPUT", { type: "text" }) }
    }), true);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "ArrowDown", target: el("SELECT") }
    }), true);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "ArrowRight", target: el("DIV") },
        editing: true
    }), true);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "ArrowRight", target: el("DIV") },
        editing: false
    }), false);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Tab", target: el("INPUT", { type: "text" }) }
    }), false);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Enter", target: el("INPUT", { type: "text" }) }
    }), false);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Escape", target: el("INPUT", { type: "text" }) }
    }), false);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "ArrowLeft", target: el("DIV") }
    }), false);
});

test("shouldSuppressEditorArrowNav: Backspace/Delete in editor, not on cell", () => {
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Backspace", target: el("INPUT", { type: "text" }) }
    }), true);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Delete", target: el("TEXTAREA") }
    }), true);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Backspace", target: el("SELECT") }
    }), true);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Backspace", target: el("DIV") },
        editing: true
    }), true);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Backspace", target: el("DIV") },
        editing: false
    }), false);
    assert.equal(shouldSuppressEditorArrowNav({
        event: { key: "Delete", target: el("DIV") }
    }), false);
});

test("stopEditorArrowNavPropagation: input arrows only", () => {
    const stopped = [];
    const inputEvent = {
        key: "ArrowLeft",
        target: el("INPUT", { type: "text" }),
        stopPropagation() { stopped.push("input"); }
    };
    assert.equal(stopEditorArrowNavPropagation(inputEvent), true);
    assert.deepEqual(stopped, ["input"]);

    const cellEvent = {
        key: "ArrowLeft",
        target: el("DIV"),
        stopPropagation() { stopped.push("cell"); }
    };
    assert.equal(stopEditorArrowNavPropagation(cellEvent), false);
    assert.deepEqual(stopped, ["input"]);
});

test("stopEditorArrowNavPropagation: Backspace/Delete in input, not preventDefault", () => {
    const stopped = [];
    let prevented = false;
    const inputEvent = {
        key: "Backspace",
        target: el("INPUT", { type: "text" }),
        stopPropagation() { stopped.push("input"); },
        preventDefault() { prevented = true; }
    };
    assert.equal(stopEditorArrowNavPropagation(inputEvent), true);
    assert.deepEqual(stopped, ["input"]);
    assert.equal(prevented, false);

    const cellEvent = {
        key: "Backspace",
        target: el("DIV"),
        stopPropagation() { stopped.push("cell"); }
    };
    assert.equal(stopEditorArrowNavPropagation(cellEvent), false);
    assert.deepEqual(stopped, ["input"]);

    const tabEvent = {
        key: "Tab",
        target: el("INPUT", { type: "text" }),
        stopPropagation() { stopped.push("tab"); }
    };
    assert.equal(stopEditorArrowNavPropagation(tabEvent), false);
    assert.deepEqual(stopped, ["input"]);
});
