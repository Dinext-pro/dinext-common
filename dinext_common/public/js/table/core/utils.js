const GRID_CALLBACK_KEYS = new Set([
    "onGridReady",
    "onCellDoubleClicked",
    "onCellClicked",
    "onCellKeyDown",
    "tabToNextCell",
    "navigateToNextCell",
    "onCellValueChanged",
    "onCellEditingStopped",
    "onCellEditRequest",
    "onCellMouseDown",
    "onCellMouseOver",
    "onCellFocused",
    "onBodyScroll"
]);

/**
 * Layout-independent shortcut match. On RU layout Ctrl+V yields key "м", code "KeyV".
 * Prefer event.code (physical key); fall back to event.key when code is absent.
 */
export function matchKeyboardShortcut(event, { code, key, mod, shift }) {
    if (!event?.key && !event?.code)                                            return false;
    if (mod && !(event.ctrlKey || event.metaKey))                               return false;
    if (shift === true && !event.shiftKey)                                      return false;
    if (shift === false && event.shiftKey)                                      return false;
    if (code && event.code === code)                                            return true;
    if (key != null && event.key?.toLowerCase() === String(key).toLowerCase())  return true;
    return false;
}

export function cssEscapeAttr(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
        return CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

/** Applies mixins left-to-right: first = innermost, last = outermost (GridMixin). */
export function composeMixins(...mixins) {
    return (Base) => mixins.reduce((Cls, mixin) => mixin(Cls), Base);
}

/** column edit > global edit */
export function resolveEdit({ globalEdit, columnEdit, row, field }) {
    if (typeof columnEdit === "function") return !!columnEdit(row, field);
    if (columnEdit !== undefined) return !!columnEdit;
    return !!globalEdit;
}

const DEFAULT_MERGE_GROUP_FIELD_NAMES = {
    idField: "mergeGroupId",
    indexField: "mergeGroupIndex",
    sizeField: "mergeGroupSize"
};

/** @layer tree — field names for merge-group row metadata */
export function getMergeGroupFieldNames(options = {}) {
    const mergeGroup = options.mergeGroup || {};
    return {
        idField: mergeGroup.idField || DEFAULT_MERGE_GROUP_FIELD_NAMES.idField,
        indexField: mergeGroup.indexField || DEFAULT_MERGE_GROUP_FIELD_NAMES.indexField,
        sizeField: mergeGroup.sizeField || DEFAULT_MERGE_GROUP_FIELD_NAMES.sizeField
    };
}

/** @layer tree — null when row is not part of a multi-row merge group */
export function getMergeGroupMeta(row, options = {}) {
    if (!row) {
        return null;
    }
    const { idField, indexField, sizeField } = getMergeGroupFieldNames(options);
    const id = row[idField];
    if (id == null || id === "") {
        return null;
    }
    const size = Number(row[sizeField]);
    if (!Number.isFinite(size) || size < 2) {
        return null;
    }
    const index = Number(row[indexField]);
    if (!Number.isFinite(index) || index < 0 || index >= size) {
        return null;
    }
    return { id: String(id), index, size };
}

export function isMergeGroupHead(row, options = {}) {
    const meta = getMergeGroupMeta(row, options);
    return meta != null && meta.index === 0;
}

/** Displayed-row offset from parent node to insert position after merge tail (or next row). */
export function getMergeGroupChildInsertOffset(row, options = {}) {
    const meta = getMergeGroupMeta(row, options);
    if (!meta || meta.index !== 0) {
        return 1;
    }
    return meta.size;
}

/** AG Grid spanRows helper: merge adjacent rows in the same merge group. */
export function shouldSpanMergeGroupRows(nodeA, nodeB, options = {}) {
    const a = getMergeGroupMeta(nodeA?.data, options);
    const b = getMergeGroupMeta(nodeB?.data, options);
    return a != null && b != null && a.id === b.id;
}

export function createMergeGroupSpanRows(options = {}) {
    return (params) => shouldSpanMergeGroupRows(params.nodeA, params.nodeB, options);
}

export function normalizeColumn(col, globalEdit) {
    const { edit, render, tree, children, ...rest } = col;

    if (Array.isArray(children) && children.length) {
        return {
            ...rest,
            children: children.map((child) => normalizeColumn(child, globalEdit))
        };
    }

    if (!col.field) {
        return { ...rest };
    }

    const field = col.field;
    return {
        ...rest,
        editable: (params) => resolveEdit({
            globalEdit,
            columnEdit: edit,
            row: params.data,
            field: params.colDef.field || field
        })
    };
}

export function normalizeColumns(columns, globalEdit) {
    return (columns || []).map(col => normalizeColumn(col, globalEdit));
}

export function chainHandlers(...handlers) {
    const fns = handlers.filter(fn => typeof fn === "function");
    if (!fns.length) return undefined;
    if (fns.length === 1) return fns[0];
    
    return function chainedHandler(...args) {
        for (const fn of fns) {
            const result = fn.apply(this, args);
            if (result === false) return false;
        }
    };
}

export function mergeGridOptions(...parts) {
    const result = {};

    for (const part of parts) {
        if (!part || typeof part !== "object") {
            continue;
        }

        for (const [key, value] of Object.entries(part)) {
            if (value === undefined) {
                continue;
            }

            if (GRID_CALLBACK_KEYS.has(key) && typeof value === "function") {
                result[key] = chainHandlers(result[key], value);
                continue;
            }

            if (key === "defaultColDef" && value && typeof value === "object") {
                result[key] = mergeGridOptions(result[key] || {}, value);
                continue;
            }

            if (key === "columnTypes" && value && typeof value === "object") {
                result[key] = Object.assign({}, result[key] || {}, value);
                continue;
            }

            if (key === "context" && value && typeof value === "object") {
                result[key] = Object.assign({}, result[key] || {}, value);
                continue;
            }

            result[key] = value;
        }
    }

    return result;
}
