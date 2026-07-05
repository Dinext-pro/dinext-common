const GRID_CALLBACK_KEYS = new Set([
    "onGridReady",
    "onCellDoubleClicked",
    "onCellClicked",
    "onCellKeyDown",
    "tabToNextCell",
    "navigateToNextCell"
]);

/** Applies mixins left-to-right: first = innermost, last = outermost (GridMixin). */
export function composeMixins(...mixins) {
    return (Base) => mixins.reduce((Cls, mixin) => mixin(Cls), Base);
}

/** column edit > global edit */
export function resolveEdit({ globalEdit, columnEdit, row, field }) {
    if (typeof columnEdit === "function") {
        return !!columnEdit(row, field);
    }
    if (columnEdit !== undefined) {
        return !!columnEdit;
    }
    return !!globalEdit;
}

export function normalizeColumn(col, globalEdit) {
    const { edit, render, tree, ...rest } = col;
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
    if (!fns.length) {
        return undefined;
    }
    if (fns.length === 1) {
        return fns[0];
    }
    return function chainedHandler(...args) {
        for (const fn of fns) {
            const result = fn.apply(this, args);
            if (result === false) {
                return false;
            }
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

            if (key === "context" && value && typeof value === "object") {
                result[key] = Object.assign({}, result[key] || {}, value);
                continue;
            }

            result[key] = value;
        }
    }

    return result;
}
