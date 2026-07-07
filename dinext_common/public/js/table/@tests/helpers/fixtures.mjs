/** Shared row builders for DinextTable core tests. Extend here for new scenarios. */

export const DEFAULT_OPTIONS = {};

export function makeRow(id, extras = {}) {
    return { id: String(id), a: String(id), ...extras };
}

export function makeChild(id, parentId) {
    return makeRow(id, { a: `${parentId}.${id.split(".").pop()}` });
}

export function makeMergeHead(id, size, extras = {}) {
    return makeRow(id, {
        mergeGroupId: `g-${id}`,
        mergeGroupIndex: 0,
        mergeGroupSize: size,
        ...extras
    });
}

export function makeMergeTail(id, headId, size, extras = {}) {
    return makeRow(id, {
        mergeGroupId: `g-${headId}`,
        mergeGroupIndex: size - 1,
        mergeGroupSize: size,
        ...extras
    });
}

/** Two-row merge group: head + one tail. */
export function makeMergePair(headId, tailId, headExtras = {}, tailExtras = {}) {
    return [
        makeMergeHead(headId, 2, headExtras),
        makeMergeTail(tailId, headId, 2, tailExtras)
    ];
}

export function visibleRowIds(rows) {
    return rows.map((row) => row._rowId);
}

export function expandedSet(...ids) {
    return new Set(ids.map(String));
}
