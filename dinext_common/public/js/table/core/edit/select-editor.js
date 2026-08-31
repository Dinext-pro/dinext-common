/**
 * Optional native `<select>`.
 * Not part of `type: "select"` preset — Desk apps should supply their own
 * cellEditor (e.g. Frappe ControlSelect). See usage-guides/select-columns.md.
 */

import {
	formatSelectValue,
	parseSelectValue,
	resolveSelectSpec
} from "./select-utils.js";

export class SelectCellEditor {
	init(params) {
		this.params = params;
		const spec = resolveSelectSpec(params);
		this._values = spec.values;
		this._labels = spec.labels;

		const select = document.createElement("select");
		select.className = "dinext-table-select-editor";
		select.setAttribute("aria-label", params.colDef?.headerName || "select");

		const blank = document.createElement("option");
		blank.value = "";
		blank.textContent = "";
		select.appendChild(blank);

		const current = params.value == null ? "" : String(params.value);
		for (const opt of this._values) {
			const option = document.createElement("option");
			option.value = opt;
			option.textContent = formatSelectValue(opt, { labels: this._labels });
			if (opt === current) {
				option.selected = true;
			}
			select.appendChild(option);
		}

		this.eSelect = select;
	}

	getGui() {
		return this.eSelect;
	}

	afterGuiAttached() {
		this.eSelect?.focus?.();
		if (typeof this.eSelect?.showPicker === "function") {
			try {
				this.eSelect.showPicker();
			} catch {
				/* gesture lost or unsupported */
			}
		}
	}

	getValue() {
		return parseSelectValue(this.eSelect?.value, this._values, {
			labels: this._labels
		});
	}

	isCancelAfterEnd() {
		return false;
	}

	destroy() {
		this.eSelect = null;
		this.params = null;
		this._values = null;
		this._labels = null;
	}
}

/** valueParser for paste / typed edit → option key or null. */
export function selectValueParser(params) {
	const spec = resolveSelectSpec(params);
	return parseSelectValue(params.newValue, spec.values, { labels: spec.labels });
}

/** valueFormatter for display (optional labels / __). */
export function selectValueFormatter(params) {
	const spec = resolveSelectSpec(params);
	return formatSelectValue(params.value, { labels: spec.labels });
}
