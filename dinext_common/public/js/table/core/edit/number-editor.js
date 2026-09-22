/**
 * Default editor for `type: "number"` / `"integer"`.
 * Text input + locale decimal; letters never stay in the field.
 */

import { isNumberDraft, isAllowedNumberDraft, parseLocaleNumber } from "./number-utils.js";

const CONTROL_INPUT_TYPES = new Set([
	"insertLineBreak",
	"deleteContentBackward",
	"deleteContentForward",
	"deleteByCut",
	"deleteByDrag",
	"historyUndo",
	"historyRedo",
]);

export { isAllowedNumberDraft, isNumberDraft, parseLocaleNumber } from "./number-utils.js";

function formatEditorValue(value) {
	if (value == null || value === "") {
		return "";
	}
	if (typeof value === "number" && Number.isFinite(value)) {
		return String(value);
	}
	const parsed = parseLocaleNumber(value);
	return parsed == null ? "" : String(parsed);
}

export class NumberCellEditor {
	init(params) {
		this.params = params;
		this.integer = params?.colDef?.type === "integer"
			|| params?.column?.getColDef?.()?.type === "integer";
		const input = document.createElement("input");
		input.type = "text";
		input.inputMode = "decimal";
		input.autocomplete = "off";
		input.spellcheck = false;
		input.className = "dinext-table-number-editor";
		input.setAttribute("aria-label", params.colDef?.headerName || "number");

		const typed = params.eventKey && params.eventKey.length === 1
			? params.eventKey
			: params.charPress;
		if (typed && isNumberDraft(typed, this.integer)) {
			input.value = typed;
		} else {
			input.value = formatEditorValue(params.value);
		}

		input.addEventListener("beforeinput", (event) => {
			if (CONTROL_INPUT_TYPES.has(event.inputType) || event.inputType?.startsWith("delete")) {
				return;
			}
			if (event.inputType !== "insertText" && event.inputType !== "insertFromPaste"
				&& event.inputType !== "insertFromDrop" && event.inputType !== "insertReplacementText") {
				if (!event.data) {
					return;
				}
			}
			const data = event.data ?? "";
			const start = input.selectionStart ?? input.value.length;
			const end = input.selectionEnd ?? input.value.length;
			if (!isAllowedNumberDraft(input.value, data, start, end, { integer: this.integer })) {
				event.preventDefault();
			}
		});

		this.eInput = input;
	}

	isCancelBeforeStart() {
		const typed = this.params?.eventKey && this.params.eventKey.length === 1
			? this.params.eventKey
			: this.params?.charPress;
		if (!typed) {
			return false;
		}
		return !isNumberDraft(typed, this.integer);
	}

	getGui() {
		return this.eInput;
	}

	afterGuiAttached() {
		this.eInput?.focus?.();
		this.eInput?.select?.();
	}

	getValue() {
		const parsed = parseLocaleNumber(this.eInput?.value);
		if (parsed == null) {
			return null;
		}
		return this.integer ? Math.trunc(parsed) : parsed;
	}

	isCancelAfterEnd() {
		return false;
	}

	destroy() {
		this.eInput = null;
		this.params = null;
	}
}
