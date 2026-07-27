import { parseDateValue } from "../edit/date-utils.js";
import { walkLeafColumns } from "../tree/model.js";

/** @typedef {"text"|"number"|"date"} DinextFilterKind */

export const FILTER_KINDS = Object.freeze({
    TEXT: "text",
    NUMBER: "number",
    DATE: "date"
});

/** Compare / text ops after parse. */
export const FILTER_OPS = Object.freeze({
    CONTAINS: "contains",
    NOT_CONTAINS: "not_contains",
    EQ: "eq",
    NE: "ne",
    GT: "gt",
    GTE: "gte",
    LT: "lt",
    LTE: "lte"
});

const COMPARE_PREFIXES = [
    [">=", FILTER_OPS.GTE],
    ["<=", FILTER_OPS.LTE],
    ["<>", FILTER_OPS.NE],
    ["!=", FILTER_OPS.NE],
    [">", FILTER_OPS.GT],
    ["<", FILTER_OPS.LT],
    ["=", FILTER_OPS.EQ]
];

/**
 * Resolve filter kind from column def (`type` / `cellDataType` / `filterKind`).
 * @returns {DinextFilterKind}
 */
export function resolveFilterKind(col) {
    const raw = col?.filterKind ?? col?.type ?? col?.cellDataType;
    const t = raw != null ? String(raw).toLowerCase() : "";
    if (t === "number" || t === "integer") {
        return FILTER_KINDS.NUMBER;
    }
    if (t === "date") {
        return FILTER_KINDS.DATE;
    }
    return FILTER_KINDS.TEXT;
}

/** @returns {Record<string, DinextFilterKind>} */
export function buildFilterKindByField(columns) {
    const map = Object.create(null);
    walkLeafColumns(columns, (col) => {
        if (col?.field == null || col.field === "") {
            return;
        }
        map[String(col.field)] = resolveFilterKind(col);
    });
    return map;
}

/**
 * @returns {{ op: string, operand: string, literal?: boolean }}
 */
export function parseFilterQuery(query, kind = FILTER_KINDS.TEXT) {
    const raw = query == null ? "" : String(query).trim();
    if (!raw) {
        return { op: FILTER_OPS.CONTAINS, operand: "" };
    }

    // "..." → always literal contains (escape operators).
    if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
        return {
            op: FILTER_OPS.CONTAINS,
            operand: raw.slice(1, -1),
            literal: true
        };
    }

    if (kind === FILTER_KINDS.NUMBER || kind === FILTER_KINDS.DATE) {
        for (const [prefix, op] of COMPARE_PREFIXES) {
            if (raw.startsWith(prefix)) {
                return { op, operand: raw.slice(prefix.length).trim() };
            }
        }
        return { op: FILTER_OPS.CONTAINS, operand: raw };
    }

    // text: = exact, ! / - not contains; bare → contains. `>1` stays contains.
    if (raw.startsWith("=")) {
        return { op: FILTER_OPS.EQ, operand: raw.slice(1).trim() };
    }
    if (raw.startsWith("!")) {
        return { op: FILTER_OPS.NOT_CONTAINS, operand: raw.slice(1).trim() };
    }
    if (raw.startsWith("-") && raw.length > 1) {
        return { op: FILTER_OPS.NOT_CONTAINS, operand: raw.slice(1).trim() };
    }
    return { op: FILTER_OPS.CONTAINS, operand: raw };
}

function coerceNumber(value) {
    if (value == null || value === "") {
        return null;
    }
    if (typeof value === "number") {
        return Number.isFinite(value) ? value : null;
    }
    if (typeof value === "boolean") {
        return Number(value);
    }
    const s = String(value).trim().replace(",", ".");
    if (!s) {
        return null;
    }
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
}

function coerceDate(value) {
    if (value == null || value === "") {
        return null;
    }
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
        return value.getTime();
    }
    const iso = parseDateValue(value);
    if (!iso) {
        return null;
    }
    const t = Date.parse(`${iso}T00:00:00`);
    return Number.isNaN(t) ? null : t;
}

function coerceForKind(value, kind) {
    if (kind === FILTER_KINDS.NUMBER) {
        return coerceNumber(value);
    }
    if (kind === FILTER_KINDS.DATE) {
        return coerceDate(value);
    }
    return value == null ? null : String(value);
}

function textContains(value, needle) {
    if (needle == null || needle === "") {
        return true;
    }
    if (value == null) {
        return false;
    }
    return String(value).toLowerCase().includes(String(needle).toLowerCase());
}

function textEquals(value, needle) {
    if (value == null) {
        return needle == null || needle === "";
    }
    return String(value).toLowerCase() === String(needle ?? "").toLowerCase();
}

function compareOps(left, right, op) {
    switch (op) {
        case FILTER_OPS.EQ:
            return left === right;
        case FILTER_OPS.NE:
            return left !== right;
        case FILTER_OPS.GT:
            return left > right;
        case FILTER_OPS.GTE:
            return left >= right;
        case FILTER_OPS.LT:
            return left < right;
        case FILTER_OPS.LTE:
            return left <= right;
        default:
            return false;
    }
}

/**
 * Match cell value against filter query for a column kind.
 * @param {unknown} value
 * @param {string} query
 * @param {DinextFilterKind} [kind]
 */
export function valueMatchesQuery(value, query, kind = FILTER_KINDS.TEXT) {
    if (query == null || query === "") {
        return true;
    }
    const trimmed = String(query).trim();
    if (!trimmed) {
        return true;
    }

    const resolvedKind = kind || FILTER_KINDS.TEXT;
    const parsed = parseFilterQuery(trimmed, resolvedKind);

    if (resolvedKind === FILTER_KINDS.NUMBER || resolvedKind === FILTER_KINDS.DATE) {
        if (
            parsed.op === FILTER_OPS.GT
            || parsed.op === FILTER_OPS.GTE
            || parsed.op === FILTER_OPS.LT
            || parsed.op === FILTER_OPS.LTE
            || parsed.op === FILTER_OPS.EQ
            || parsed.op === FILTER_OPS.NE
        ) {
            const left = coerceForKind(value, resolvedKind);
            const right = coerceForKind(parsed.operand, resolvedKind);
            if (left == null || right == null) {
                return false;
            }
            return compareOps(left, right, parsed.op);
        }
        return textContains(value, parsed.operand);
    }

    if (parsed.op === FILTER_OPS.EQ) {
        return textEquals(value, parsed.operand);
    }
    if (parsed.op === FILTER_OPS.NOT_CONTAINS) {
        if (parsed.operand === "") {
            return true;
        }
        return !textContains(value, parsed.operand);
    }
    return textContains(value, parsed.operand);
}
