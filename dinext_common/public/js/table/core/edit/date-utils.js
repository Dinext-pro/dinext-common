/**
 * ISO date helpers for column type `date` (YYYY-MM-DD strings).
 * Storage contract: string | null — not JS Date (Frappe / fill / paste friendly).
 */

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** @returns {string | null} */
export function toIsoDateString(value) {
	if (value == null || value === "") {
		return null;
	}
	if (value instanceof Date && !Number.isNaN(value.getTime())) {
		const y = value.getFullYear();
		const m = String(value.getMonth() + 1).padStart(2, "0");
		const d = String(value.getDate()).padStart(2, "0");
		return `${y}-${m}-${d}`;
	}
	const s = String(value).trim();
	if (!s) {
		return null;
	}
	if (s.includes("T")) {
		return s.slice(0, 10);
	}
	// DD.MM.YYYY or DD/MM/YYYY (common paste)
	const dmy = s.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})$/);
	if (dmy) {
		const dd = dmy[1].padStart(2, "0");
		const mm = dmy[2].padStart(2, "0");
		return `${dmy[3]}-${mm}-${dd}`;
	}
	if (ISO_DATE_RE.test(s)) {
		return s;
	}
	return null;
}

/** @returns {string | null} */
export function parseDateValue(raw) {
	if (raw == null || raw === "") {
		return null;
	}
	return toIsoDateString(raw);
}

/** Display label; uses frappe.format when present. */
export function formatDateValue(value) {
	const iso = toIsoDateString(value);
	if (!iso) {
		return "";
	}
	if (typeof frappe !== "undefined" && typeof frappe.format === "function") {
		return frappe.format(iso, { fieldtype: "Date" }) || iso;
	}
	return iso;
}

export function isIsoDateString(value) {
	return typeof value === "string" && ISO_DATE_RE.test(value);
}
