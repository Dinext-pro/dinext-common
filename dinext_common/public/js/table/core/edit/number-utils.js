/** Parses user input with comma or dot decimal separator. Returns null for empty/invalid. */
export function parseLocaleNumber(raw) {
	if (raw == null || raw === "") {
		return null;
	}
	if (typeof raw === "number") {
		return Number.isFinite(raw) ? raw : null;
	}

	const trimmed = String(raw).trim().replace(/\s/g, "");
	if (!trimmed) {
		return null;
	}

	const normalized = trimmed.includes(",") && !trimmed.includes(".")
		? trimmed.replace(",", ".")
		: trimmed.replace(/,/g, "");
	const value = Number(normalized);
	return Number.isFinite(value) ? value : null;
}

/** True if `raw` is a valid in-progress number (optional sign, one decimal sep). */
export function isNumberDraft(raw, integer = false) {
	if (raw == null) {
		return false;
	}
	const text = String(raw).trim().replace(/\s/g, "");
	if (!text) {
		return false;
	}
	if (text === "-" || text === "+") {
		return true;
	}
	if (integer) {
		return /^[+-]?\d+$/.test(text);
	}
	return /^[+-]?(?:\d+[.,]?\d*|[.,]\d+)$/.test(text);
}

export function isAllowedNumberDraft(current, insert, selStart, selEnd, { integer = false } = {}) {
	const next = `${String(current).slice(0, selStart)}${insert}${String(current).slice(selEnd)}`;
	return isNumberDraft(next, integer);
}
