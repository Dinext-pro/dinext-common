import {
    asProjectedMergeGroupRow,
    asStandaloneMergeGroupRow,
    getChildrenField,
    getMergeGroupMeta,
    getRowIdField
} from "../shared/utils.js";
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

/** True when both maps have the same fields and query strings. */
export function sameFilterState(a, b) {
    const left = normalizeFilterState(a);
    const right = normalizeFilterState(b);
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    if (leftKeys.length !== rightKeys.length) {
        return false;
    }
    for (const key of leftKeys) {
        if (left[key] !== right[key]) {
            return false;
        }
    }
    return true;
}

function resolveKindMap(options = {}) {
    return buildFilterKindByField(options.columns || []);
}

function resolveMergeInheritedFields(options = {}) {
    const fields = options.filter?.mergeInheritedFields;
    return new Set(Array.isArray(fields) ? fields.map(String) : []);
}

function rowMatchesFilterValues(row, fallbackRow, state, options) {
    const kinds = resolveKindMap(options);
    const inheritedFields = resolveMergeInheritedFields(options);
    for (const [field, query] of Object.entries(state)) {
        const kind = kinds[field] || FILTER_KINDS.TEXT;
        const value = inheritedFields.has(field) ? fallbackRow?.[field] : row?.[field];
        if (!valueMatchesQuery(value, query, kind)) {
            return false;
        }
    }
    return true;
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
    return rowMatchesFilterValues(row, row, state, options);
}

function rowMatchesMergeFilter(row, head, state, options) {
    return rowMatchesFilterValues(row, head, state, options);
}

/**
 * Build a display-only valid merge block from matching source rows.
 * First survivor becomes the display head; source rows and raw metadata stay intact.
 */
function projectMatchingMergeRows(atom, matchingRows, options, {
    childrenField,
    filteredChildren
} = {}) {
    const sourceHead = atom.head;
    const sourceMeta = getMergeGroupMeta(sourceHead, options);
    const rowIdField = getRowIdField(options);
    const inheritedFields = resolveMergeInheritedFields(options);
    const projectedSize = matchingRows.length;

    return matchingRows.map((sourceRow, index) => {
        let projected = { ...sourceRow };
        for (const field of inheritedFields) {
            projected[field] = sourceHead?.[field];
        }
        if (index === 0 && childrenField && Array.isArray(sourceHead?.[childrenField])) {
            projected[childrenField] = filteredChildren || [];
            if (!projected[childrenField].length) {
                projected.hasChildren = false;
            }
        }

        const mergeMeta = projectedSize > 1
            ? { id: sourceMeta.id, index, size: projectedSize }
            : null;
        const treeSourceRowId = index === 0 && sourceRow !== sourceHead
            ? sourceHead[rowIdField]
            : null;
        return asProjectedMergeGroupRow(projected, mergeMeta, treeSourceRowId);
    });
}

/**
 * Flat filter: merge atoms stay whole by default. With
 * `filter.mergeMatchMode: "rows"`, keep only matching source rows and rebuild
 * valid display merge metadata without mutating source data.
 * Does not recurse into `children` — use `filterTreeRows` for nested.
 * @returns {object[]} new array
 */
export function filterFlatRows(rows, state, options = {}) {
    const normalized = normalizeFilterState(state);
    if (!Array.isArray(rows) || isFilterStateEmpty(normalized)) {
        return Array.isArray(rows) ? rows : [];
    }

    const atoms = buildSortAtoms(rows, options);
    const out = [];
    for (const atom of atoms) {
        const matchingRows = atom.rows.filter(
            (row) => rowMatchesMergeFilter(row, atom.head, normalized, options)
        );
        if (!matchingRows.length) {
            continue;
        }
        const projectRows =
            options.filter?.mergeMatchMode === "rows"
            && atom.rows.length > 1
            && matchingRows.length < atom.rows.length;
        if (projectRows) {
            out.push(...projectMatchingMergeRows(atom, matchingRows, options));
        } else {
            out.push(...atom.rows);
        }
    }
    return out;
}

/**
 * Tree filter (match + ancestors): prune source tree without mutating rows.
 * Self-matching merge atoms stay whole by default. `mergeMatchMode: "rows"`
 * keeps only matching roles/rows. `mergeAncestorMode: "head"` renders a
 * descendant-only merge ancestor as one context head.
 * Returns expandIds so matches under collapsed parents are visible.
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
        const matchingRows = atom.rows.filter(
            (row) => rowMatchesMergeFilter(row, head, state, options)
        );
        const selfMatch = matchingRows.length > 0;
        const projectRows =
            selfMatch
            && options.filter?.mergeMatchMode === "rows"
            && atom.rows.length > 1
            && matchingRows.length < atom.rows.length;
        const displayHead = projectRows ? matchingRows[0] : head;
        const localId = String(displayHead[rowIdField]);
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

        if (!selfMatch && !filteredChildren.length) {
            continue;
        }

        if (projectRows) {
            out.push(...projectMatchingMergeRows(atom, matchingRows, options, {
                childrenField,
                filteredChildren
            }));
        } else if (Array.isArray(rawChildren)) {
            let nextHead = {
                ...head,
                [childrenField]: filteredChildren
            };
            if (!filteredChildren.length) {
                nextHead.hasChildren = false;
            }
            const compactMergeAncestor =
                !selfMatch
                && filteredChildren.length > 0
                && tails.length > 0
                && options.filter?.mergeAncestorMode === "head";
            if (compactMergeAncestor) {
                nextHead = asStandaloneMergeGroupRow(nextHead);
                out.push(nextHead);
            } else {
                out.push(nextHead, ...tails);
            }
        } else {
            out.push(...atom.rows);
        }
        if (filteredChildren.length) {
            expandIds.add(rowId);
        }
    }

    return { rows: out, expandIds };
}
