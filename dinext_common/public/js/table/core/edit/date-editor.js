/**
 * Optional native date editor (ISO YYYY-MM-DD).
 * Not part of `type: "date"` preset — Desk apps should supply their own cellEditor
 * (e.g. Frappe ControlDate). See usage-guides/date-columns.md.
 */

import { formatDateValue, parseDateValue, toIsoDateString } from "./date-utils.js";

export class DateCellEditor {
	init(params) {
		this.params = params;
		const input = document.createElement("input");
		input.type = "date";
		input.className = "dinext-table-date-editor";
		input.value = toIsoDateString(params.value) || "";
		input.setAttribute("aria-label", params.colDef?.headerName || "date");
		this.eInput = input;
	}

	getGui() {
		return this.eInput;
	}

	afterGuiAttached() {
		this.eInput?.focus?.();
		this.eInput?.select?.();
	}

	getValue() {
		return parseDateValue(this.eInput?.value);
	}

	isCancelAfterEnd() {
		return false;
	}

	destroy() {
		this.eInput = null;
		this.params = null;
	}
}

/** valueParser for paste / typed edit → ISO string or null. */
export function dateValueParser(params) {
	return parseDateValue(params.newValue);
}

/** valueFormatter for display (ISO → locale when frappe available). */
export function dateValueFormatter(params) {
	return formatDateValue(params.value);
}
