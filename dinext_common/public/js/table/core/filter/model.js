import { getChildrenField, getRowIdField } from "../shared/utils.js";
import { buildSortAtoms } from "../sort/model.js";
import {
    FILTER_KINDS,
    buildFilterKindByField,
    valueMatchesQuery
} from "./query.js";

export {
    FILTER_KINDS,
    FILTER_OPS,
    buildFilterKindByField,
    parseFilterQuery,
    resolveFilterKind,
    valueMatchesQuery
} from "./query.js";

/**
 * Normalize filter state: `{ field: queryString }`, drop empty keys/values.
 * @returns {Record<string, string>}
 */
export function normalizeFilterState(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        return {};
    }
    const out = {};
    for (const [key, value] of Object.entries(raw)) {
        const field = key != null ? String(key) : "";
        if (!field) {
            continue;
        }
        if (value == null) {
            continue;
        }
        const query = String(value).trim();
        if (!query) {
            continue;
        }
        out[field] = query;
    }
    return out;
}

export function isFilterStateEmpty(state) {
    return !state || !Object.keys(state).length;
}

function resolveKindMap(options = {}) {
    return buildFilterKindByField(options.columns || []);
}

/**
 * Row passes when every non-empty field query matches (AND).
 * Operators depend on column `type` / `cellDataType` (see query.js).
 * @param {object} row
 * @param {Record<string, string>} state — already normalized
 * @param {object} [options] — table options (`columns`)
 */
export function rowMatchesFilter(row, state, options = {}) {
    if (isFilterStateEmpty(state)) {
        return true;
    }
    const kinds = resolveKindMap(options);
    for (const [field, query] of Object.entries(state)) {
        const kind = kinds[field] || FILTER_KINDS.TEXT;
        if (!valueMatchesQuery(row?.[field], query, kind)) {
            return false;
        }
    }
    return true;
}

/**
 * Flat filter: keep merge atoms wholly if any row in atom matches.
 * Does not recurse into `children` — use `filterTreeRows` for nested.
 * @returns {object[]} new array (same row refs)
 */
export function filterFlatRows(rows, state, options = {}) {
    const normalized = normalizeFilterState(state);
    if (!Array.isArray(rows) || isFilterStateEmpty(normalized)) {
        return Array.isArray(rows) ? rows : [];
    }

    const atoms = buildSortAtoms(rows, options);
    const out = [];
    for (const atom of atoms) {
        const pass = atom.rows.some((row) => rowMatchesFilter(row, normalized, options));
        if (pass) {
            out.push(...atom.rows);
        }
    }
    return out;
}

/**
 * Tree filter (match + ancestors): prune source tree without mutating rows.
 * Keeps merge atoms wholly; returns expandIds so matches under collapsed parents are visible.
 * @returns {{ rows: object[], expandIds: Set<string> }}
 */
export function filterTreeRows(rows, state, options = {}) {
    const normalized = normalizeFilterState(state);
    if (!Array.isArray(rows) || isFilterStateEmpty(normalized)) {
        return {
            rows: Array.isArray(rows) ? rows : [],
            expandIds: new Set()
        };
    }
    return filterTreeSiblingList(rows, null, normalized, options);
}

function filterTreeSiblingList(list, parentRowId, state, options) {
    const childrenField = getChildrenField(options);
    const rowIdField = getRowIdField(options);
    const atoms = buildSortAtoms(list, options);
    const out = [];
    const expandIds = new Set();

    for (const atom of atoms) {
        const head = atom.head;
        const localId = String(head[rowIdField]);
        const rowId = parentRowId ? `${parentRowId}:${localId}` : localId;
        const tails = atom.rows.slice(1);
        const rawChildren = head[childrenField];

        let filteredChildren = [];
        if (Array.isArray(rawChildren) && rawChildren.length) {
            const childResult = filterTreeSiblingList(rawChildren, rowId, state, options);
            filteredChildren = childResult.rows;
            for (const id of childResult.expandIds) {
                expandIds.add(id);
            }
        }

        const selfMatch = atom.rows.some((row) => rowMatchesFilter(row, state, options));
        if (!selfMatch && !filteredChildren.length) {
            continue;
        }

        if (Array.isArray(rawChildren)) {
            const nextHead = {
                ...head,
                [childrenField]: filteredChildren
            };
            if (!filteredChildren.length) {
                nextHead.hasChildren = false;
            }
            out.push(nextHead, ...tails);
            if (filteredChildren.length) {
                expandIds.add(rowId);
            }
        } else {
            out.push(...atom.rows);
        }
    }

    return { rows: out, expandIds };
}
