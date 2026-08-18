/** Arrow keys that AG Grid / DinextTable use to change the focused cell. */
const ARROW_KEYS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]);

/**
 * AG Grid CellKeyboardListener.onBackspaceOrDeleteKeyDown:
 * Windows Backspace → startEditing (wipes custom Frappe input);
 * Mac Backspace / any Delete → setDataValue(..., "cellClear").
 */
const EDITOR_CLEAR_KEYS = new Set(["Backspace", "Delete"]);

/** Keys the grid must not steal while a native editor is focused. */
const EDITOR_GUARD_KEYS = new Set([...ARROW_KEYS, ...EDITOR_CLEAR_KEYS]);

/** Native inputs where arrows are not caret movement. */
const NON_CARET_INPUT_TYPES = new Set([
    "button",
    "checkbox",
    "radio",
    "hidden",
    "file",
    "submit",
    "reset",
    "image",
    "range",
    "color"
]);

export function isArrowKey(key) {
    return ARROW_KEYS.has(key);
}

export function isEditorGuardKey(key) {
    return EDITOR_GUARD_KEYS.has(key);
}

export function isSelectEditorTarget(el) {
    return !!el && el.tagName === "SELECT";
}

/** text / date / number / textarea / contenteditable — arrows move caret (or native stepper). */
export function isCaretEditorTarget(el) {
    if (!el) {
        return false;
    }
    if (el.isContentEditable) {
        return true;
    }
    const tag = el.tagName;
    if (tag === "TEXTAREA") {
        return true;
    }
    if (tag !== "INPUT") {
        return false;
    }
    const type = String(el.type || "text").toLowerCase();
    return !NON_CARET_INPUT_TYPES.has(type);
}

export function isEditorArrowNavTarget(el) {
    return isCaretEditorTarget(el) || isSelectEditorTarget(el);
}

/**
 * AG Grid `suppressKeyboardEvent` (ColDef / defaultColDef, not grid root).
 * Covers official AG editors (`params.editing`) and custom in-cell inputs
 * (Frappe Control) that never set `getEditingCells()`.
 * Arrows stay in caret / native &lt;select&gt;. Backspace/Delete stay native
 * (one char / selection) — do not preventDefault.
 * Tab / Enter / Esc are not suppressed.
 */
export function shouldSuppressEditorArrowNav(params = {}) {
    const event = params.event;
    if (!event || !isEditorGuardKey(event.key)) {
        return false;
    }
    if (isEditorArrowNavTarget(event.target)) {
        return true;
    }
    return !!params.editing;
}

/**
 * Capture-phase on the focused editor: stop bubbling to AG Grid / selection.
 * Do not call from an ancestor capture — that would starve the input of the key.
 * Do not preventDefault — native Backspace/Delete must still edit the value.
 */
export function stopEditorArrowNavPropagation(event) {
    if (!event || !isEditorGuardKey(event.key) || !isEditorArrowNavTarget(event.target)) {
        return false;
    }
    event.stopPropagation();
    return true;
}
