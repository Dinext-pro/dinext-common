import {
    getChildrenField,
    getMergeGroupMeta,
    isMergeGroupHead
} from "../shared/utils.js";

export const SORT_DIRS = Object.freeze({
    ASC: "asc",
    DESC: "desc"
});

export const SORT_NULLS = Object.freeze({
    LAST: "last",
    FIRST: "first"
});

/** @returns {{ field: string, dir: "asc"|"desc" }[]} */
export function normalizeSortState(raw) {
    if (!Array.isArray(raw) || !raw.length) {
        return [];
    }
    const out = [];
    const seen = new Set();
    for (const item of raw) {
        const field = item?.field != null ? String(item.field) : "";
        if (!field || seen.has(field)) {
            continue;
        }
        const dir = item.dir === SORT_DIRS.DESC ? SORT_DIRS.DESC : SORT_DIRS.ASC;
        seen.add(field);
        out.push({ field, dir });
    }
    return out;
}

export function isEmptySortValue(value) {
    return value == null || value === "";
}

/**
 * Default compare for scalar cell values.
 * @returns {number} negative / 0 / positive (before nulls policy)
 */
export function compareSortValues(a, b) {
    if (typeof a === "number" && typeof b === "number") {
        if (Number.isNaN(a) && Number.isNaN(b)) return 0;
        if (Number.isNaN(a)) return 1;
        if (Number.isNaN(b)) return -1;
        return a - b;
    }
    if (typeof a === "boolean" && typeof b === "boolean") {
        return Number(a) - Number(b);
    }
    if (a instanceof Date && b instanceof Date) {
        return a.getTime() - b.getTime();
    }
    const sa = String(a);
    const sb = String(b);
    return sa.localeCompare(sb, undefined, { numeric: true, sensitivity: "base" });
}

function resolveComparator(field, options = {}) {
    const custom = options.sort?.comparators?.[field];
    return typeof custom === "function" ? custom : null;
}

/**
 * Compare two atom heads by sort specs.
 * @param {object} rowA
 * @param {object} rowB
 * @param {{ field: string, dir: string }[]} specs
 * @param {object} options
 */
export function compareRowsBySortSpecs(rowA, rowB, specs, options = {}) {
    const nulls = options.sort?.nulls === SORT_NULLS.FIRST
        ? SORT_NULLS.FIRST
        : SORT_NULLS.LAST;

    for (const spec of specs) {
        const field = spec.field;
        const dir = spec.dir === SORT_DIRS.DESC ? -1 : 1;
        const a = rowA?.[field];
        const b = rowB?.[field];
        const aEmpty = isEmptySortValue(a);
        const bEmpty = isEmptySortValue(b);

        if (aEmpty && bEmpty) {
            continue;
        }
        if (aEmpty || bEmpty) {
            if (nulls === SORT_NULLS.FIRST) {
                return aEmpty ? -1 : 1;
            }
            return aEmpty ? 1 : -1;
        }

        const custom = resolveComparator(field, options);
        const cmp = custom
            ? custom(a, b, { field, dir: spec.dir, rowA, rowB, options })
            : compareSortValues(a, b);
        if (cmp !== 0 && cmp != null && !Number.isNaN(cmp)) {
            return cmp * dir;
        }
    }
    return 0;
}

/**
 * Split sibling list into atoms: single rows or full merge blocks.
 * Invalid / broken merge tails fall through as singles.
 * @returns {{ rows: object[], head: object }[]}
 */
export function buildSortAtoms(list, options = {}) {
    if (!Array.isArray(list) || !list.length) {
        return [];
    }

    const atoms = [];
    let i = 0;
    while (i < list.length) {
        const row = list[i];
        const meta = getMergeGroupMeta(row, options);

        if (meta && isMergeGroupHead(row, options)) {
            const end = Math.min(i + meta.size, list.length);
            let ok = end - i === meta.size;
            if (ok) {
                for (let j = i; j < end; j++) {
                    const m = getMergeGroupMeta(list[j], options);
                    if (!m || m.id !== meta.id || m.index !== j - i) {
                        ok = false;
                        break;
                    }
                }
            }
            if (ok) {
                const rows = list.slice(i, end);
                atoms.push({ rows, head: rows[0] });
                i = end;
                continue;
            }
        }

        atoms.push({ rows: [row], head: row });
        i += 1;
    }
    return atoms;
}

/**
 * Sort one sibling list in place (atoms + recursive children).
 * @returns {object[]} same array reference
 */
export function sortSiblingListInPlace(list, specs, options = {}) {
    if (!Array.isArray(list) || list.length < 2 || !specs?.length) {
        if (Array.isArray(list) && specs?.length) {
            sortChildrenRecursive(list, specs, options);
        }
        return list || [];
    }

    const atoms = buildSortAtoms(list, options);
    atoms.sort((a, b) => compareRowsBySortSpecs(a.head, b.head, specs, options));

    list.length = 0;
    for (const atom of atoms) {
        for (const row of atom.rows) {
            list.push(row);
        }
    }

    sortChildrenRecursive(list, specs, options);
    return list;
}

function sortChildrenRecursive(list, specs, options) {
    const childrenField = getChildrenField(options);
    for (const row of list) {
        const meta = getMergeGroupMeta(row, options);
        if (meta && meta.index !== 0) {
            continue;
        }
        const children = row?.[childrenField];
        if (Array.isArray(children) && children.length) {
            sortSiblingListInPlace(children, specs, options);
        }
    }
}

/** Sort entire top-level source tree in place. */
export function sortTreeInPlace(rows, specs, options = {}) {
    return sortSiblingListInPlace(rows, normalizeSortState(specs), options);
}

/** Non-mutating: shallow-copies sibling arrays along the sorted path. */
export function sortTreeCopy(rows, specs, options = {}) {
    const normalized = normalizeSortState(specs);
    if (!Array.isArray(rows)) {
        return [];
    }
    const copy = rows.map((row) => cloneRowShallowForSort(row, options));
    sortSiblingListInPlace(copy, normalized, options);
    return copy;
}

function cloneRowShallowForSort(row, options) {
    const childrenField = getChildrenField(options);
    const next = { ...row };
    const children = row?.[childrenField];
    if (Array.isArray(children)) {
        next[childrenField] = children.map((child) => cloneRowShallowForSort(child, options));
    }
    return next;
}

/** Cycle for header click: none → asc → desc → none (single-column). */
export function cycleSortState(current, field, { multi = false } = {}) {
    const specs = normalizeSortState(current);
    const key = String(field);
    const existing = specs.find((s) => s.field === key);

    if (!multi) {
        if (!existing) {
            return [{ field: key, dir: SORT_DIRS.ASC }];
        }
        if (existing.dir === SORT_DIRS.ASC) {
            return [{ field: key, dir: SORT_DIRS.DESC }];
        }
        return [];
    }

    // reserved: multi path (append / cycle one field)
    if (!existing) {
        return [...specs, { field: key, dir: SORT_DIRS.ASC }];
    }
    if (existing.dir === SORT_DIRS.ASC) {
        return specs.map((s) => (s.field === key ? { field: key, dir: SORT_DIRS.DESC } : s));
    }
    return specs.filter((s) => s.field !== key);
}
