/**
 * Select helpers for column type `select`.
 * Storage contract: option key string | null. Unknown paste → null (never keep raw).
 */

/**
 * @param {unknown} spec
 * @returns {string[]}
 */
export function normalizeSelectValues(spec) {
	if (!Array.isArray(spec)) {
		return [];
	}
	return spec.map((v) => String(v).trim()).filter(Boolean);
}

/**
 * @param {object} [params] AG valueParser / editor params
 * @returns {{ values: string[], labels: Record<string, string> }}
 */
export function resolveSelectSpec(params) {
	const cep =
		params?.colDef?.cellEditorParams ??
		params?.column?.getColDef?.()?.cellEditorParams;
	const spec = typeof cep === "function" ? cep(params) : cep;
	let values = spec?.values;
	if (typeof values === "function") {
		values = values(params);
	}
	const labels =
		spec?.labels && typeof spec.labels === "object" && !Array.isArray(spec.labels)
			? spec.labels
			: {};
	return {
		values: normalizeSelectValues(values),
		labels
	};
}

function getTranslate() {
	const fn = typeof globalThis !== "undefined" ? globalThis.__ : undefined;
	return typeof fn === "function" ? fn : null;
}

function labelFor(option, labels) {
	if (labels && labels[option] != null && labels[option] !== "") {
		return String(labels[option]);
	}
	const translate = getTranslate();
	if (translate) {
		return String(translate(option));
	}
	return String(option);
}

/**
 * @param {unknown} raw
 * @param {string[]} options
 * @param {{ labels?: Record<string, string> }} [meta]
 * @returns {string | null}
 */
export function parseSelectValue(raw, options = [], meta = {}) {
	if (raw == null) {
		return null;
	}
	const s = String(raw).trim();
	if (!s) {
		return null;
	}

	const list = normalizeSelectValues(options);
	if (!list.length) {
		return null;
	}
	if (list.includes(s)) {
		return s;
	}

	const lower = s.toLowerCase();
	const byKey = list.find((opt) => opt.toLowerCase() === lower);
	if (byKey) {
		return byKey;
	}

	const labels = meta.labels || {};
	const byLabel = list.find((opt) => {
		const label = labelFor(opt, labels);
		return label === s || label.toLowerCase() === lower;
	});
	return byLabel || null;
}

/**
 * @param {unknown} value
 * @param {{ labels?: Record<string, string> }} [meta]
 * @returns {string}
 */
export function formatSelectValue(value, meta = {}) {
	if (value == null || value === "") {
		return "";
	}
	return labelFor(String(value), meta.labels || {});
}

/** @returns {boolean} */
export function isAllowedSelectValue(value, options = []) {
	if (value == null || value === "") {
		return false;
	}
	return normalizeSelectValues(options).includes(String(value));
}
