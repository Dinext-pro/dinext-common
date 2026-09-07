/**
 * ISO date helpers for column type `date` (YYYY-MM-DD strings).
 * Storage contract: string | null — not JS Date (Frappe / fill / paste friendly).
 *
 * Clipboard copies `valueFormatter` output (`frappe.format` Date → user date_format).
 * Default/common Frappe format is `dd-mm-yyyy` — must parse back to ISO.
 */

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, optional time after T or space. */
const YMD_RE = /^(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?:[T\s].*)?$/;

/** DD.MM.YYYY / DD/MM/YYYY / DD-MM-YYYY (Frappe user formats). */
const DMY_RE = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/;

function fromFrappeUserDate(s) {
	const userToStr = globalThis.frappe?.datetime?.user_to_str;
	if (typeof userToStr !== "function") {
		return null;
	}
	try {
		const converted = userToStr(s);
		if (!converted || converted === "Invalid date") {
			return null;
		}
		const iso = String(converted).trim().slice(0, 10);
		return ISO_DATE_RE.test(iso) ? iso : null;
	} catch (_e) {
		return null;
	}
}

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
	const ymd = s.match(YMD_RE);
	if (ymd) {
		return `${ymd[1]}-${ymd[2].padStart(2, "0")}-${ymd[3].padStart(2, "0")}`;
	}
	const dmy = s.match(DMY_RE);
	if (dmy) {
		return `${dmy[3]}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}`;
	}
	return fromFrappeUserDate(s);
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
