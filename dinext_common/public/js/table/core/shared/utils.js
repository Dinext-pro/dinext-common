const GRID_CALLBACK_KEYS = new Set([
    "onGridReady",
    "onCellDoubleClicked",
    "onCellClicked",
    "onCellKeyDown",
    "onColumnHeaderClicked",
    "onColumnHeaderMouseOver",
    "onColumnHeaderMouseLeave",
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

const DEFAULT_ROW_ID_FIELD = "id";
const DEFAULT_CHILDREN_FIELD = "children";

export function getRowIdField(options = {}) {
    return options.rowIdField || DEFAULT_ROW_ID_FIELD;
}

export function getChildrenField(options = {}) {
    return options.childrenField || DEFAULT_CHILDREN_FIELD;
}

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

/**
 * Resolve rendered `.ag-cell` for (displayedRowIndex, colId).
 * With pinned left/right columns AG Grid keeps several `.ag-row[row-index=N]`
 * (one per pin container); querying the first row alone misses center/right cells.
 */
export function queryAgCellElement(container, rowIndex, colId) {
    if (!container || rowIndex == null || colId == null) {
        return null;
    }
    return container.querySelector(
        `.ag-row[row-index="${rowIndex}"] .ag-cell[col-id="${cssEscapeAttr(colId)}"]`
    );
}

const TABLE_CHROME_CLASS_NAMES = ["dinext-table-toolbar", "dinext-table-status-bar"];

function isTableChromeElement(element) {
    return TABLE_CHROME_CLASS_NAMES.some(className => element?.classList?.contains(className));
}

function elementContainsAgGridRoot(element) {
    return element?.classList?.contains("ag-root-wrapper")
        || element?.classList?.contains("ag-root")
        || !!element?.querySelector?.(".ag-root-wrapper, .ag-root");
}

/** Direct child of DinextTable container that hosts AG Grid (safe insertBefore target). */
export function findGridMountElement(container) {
    if (!container?.children) {
        return null;
    }
    for (const child of container.children) {
        if (isTableChromeElement(child)) {
            continue;
        }
        if (elementContainsAgGridRoot(child)) {
            return child;
        }
    }
    return null;
}

/** Rendered AG Grid shell inside container; may be nested under mount element. */
export function findAgGridRootElement(container) {
    const mount = findGridMountElement(container);
    if (!mount) {
        return container?.querySelector?.(".ag-root-wrapper, .ag-root") || null;
    }
    if (mount.matches?.(".ag-root-wrapper, .ag-root")) {
        return mount;
    }
    return mount.querySelector?.(".ag-root-wrapper, .ag-root") || mount;
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

// Display-only projection metadata. Symbols keep filter projection details out
// of domain data, callbacks that serialize rows, and sourceData.
const DISPLAY_MERGE_GROUP_META = Symbol("dinextTableDisplayMergeGroupMeta");
const TREE_SOURCE_ROW_ID = Symbol("dinextTableTreeSourceRowId");

/** Return a display clone treated as a plain row by merge-aware layers. */
export function asStandaloneMergeGroupRow(row) {
    if (!row) {
        return row;
    }
    return {
        ...row,
        [DISPLAY_MERGE_GROUP_META]: null
    };
}

/**
 * Return a display clone with projected merge metadata.
 * `treeSourceRowId` points a promoted display head back to the source head.
 */
export function asProjectedMergeGroupRow(row, mergeMeta, treeSourceRowId) {
    if (!row) {
        return row;
    }
    const projected = {
        ...row,
        [DISPLAY_MERGE_GROUP_META]: mergeMeta || null
    };
    if (treeSourceRowId != null && treeSourceRowId !== "") {
        projected[TREE_SOURCE_ROW_ID] = String(treeSourceRowId);
    }
    return projected;
}

/** Source head local id for a row promoted to display merge head. */
export function getTreeSourceRowId(row) {
    return row?.[TREE_SOURCE_ROW_ID] == null
        ? null
        : String(row[TREE_SOURCE_ROW_ID]);
}

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
    if (Object.prototype.hasOwnProperty.call(row, DISPLAY_MERGE_GROUP_META)) {
        return row[DISPLAY_MERGE_GROUP_META];
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
    // treeContentKey — domain-only; wired by TreeMixin, not AG colDef.
    const { edit, render, tree, treeContentKey, children, ...rest } = col;

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

function normalizeRowClassResult(value) {
    if (value == null || value === false || value === "") {
        return [];
    }
    if (Array.isArray(value)) {
        return value.filter(Boolean).map(String);
    }
    return [String(value)];
}

/** Merges AG Grid `getRowClass` handlers into one string[] (or undefined). */
export function chainRowClassHandlers(...handlers) {
    const fns = handlers.filter(fn => typeof fn === "function");
    if (!fns.length) return undefined;
    if (fns.length === 1) return fns[0];

    return function chainedGetRowClass(...args) {
        const classes = [];
        for (const fn of fns) {
            classes.push(...normalizeRowClassResult(fn.apply(this, args)));
        }
        return classes.length ? classes : undefined;
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

            if (key === "getRowClass" && typeof value === "function") {
                result[key] = chainRowClassHandlers(result[key], value);
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
