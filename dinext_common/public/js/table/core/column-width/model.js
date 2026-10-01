import { ROW_CHECK_COL_ID } from "../row-check/constants.js";
import { ROW_REORDER_COL_ID } from "../row-reorder/constants.js";

/** User drag / header autosize. API and flex passes must not overwrite the snapshot. */
export const COLUMN_WIDTH_USER_SOURCE = "uiColumnResized";

const SKIP_COL_IDS = new Set([ROW_CHECK_COL_ID, ROW_REORDER_COL_ID]);

function cleanKey(value) {
    if (typeof value !== "string") {
        return "";
    }
    return value.trim();
}

/** Default on. `columnWidth.persist: false` — domain owns widths (timesheet). */
export function isColumnWidthPersistEnabled(options) {
    return options?.columnWidth?.persist !== false;
}

/**
 * Entity id, not document.
 * Explicit `columnWidth.persistKey`, else `toolbar.persistKey` before the first `:`.
 * `work-efforts:PROJ-001` → `work-efforts`. No colon → key as-is.
 * @returns {string|null}
 */
export function resolveColumnWidthEntityKey(options) {
    if (!isColumnWidthPersistEnabled(options)) {
        return null;
    }
    const explicit = cleanKey(options?.columnWidth?.persistKey);
    if (explicit) {
        return explicit;
    }
    const toolbarKey = cleanKey(options?.toolbar?.persistKey);
    if (!toolbarKey) {
        return null;
    }
    const colon = toolbarKey.indexOf(":");
    const entity = colon === -1 ? toolbarKey : toolbarKey.slice(0, colon);
    return entity || null;
}

/** @returns {string|null} */
export function getColumnWidthStorageKey(entityKey) {
    const entity = cleanKey(entityKey);
    return entity ? `dinext-table:columns:${entity}` : null;
}

export function isSkippedColumnWidthId(colId) {
    return SKIP_COL_IDS.has(colId);
}

/**
 * @param {string|null|undefined} raw
 * @returns {Record<string, number>}
 */
export function parseColumnWidthRaw(raw) {
    if (raw == null || raw === "") {
        return {};
    }
    let obj;
    try {
        obj = JSON.parse(raw);
    } catch (_err) {
        return {};
    }
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
        return {};
    }
    /** @type {Record<string, number>} */
    const widths = {};
    for (const [colId, width] of Object.entries(obj)) {
        const px = normalizeColumnWidthPx(colId, width);
        if (px == null) {
            continue;
        }
        widths[colId] = px;
    }
    return widths;
}

export function serializeColumnWidths(widths) {
    /** @type {Record<string, number>} */
    const clean = {};
    for (const [colId, width] of Object.entries(widths || {})) {
        const px = normalizeColumnWidthPx(colId, width);
        if (px == null) {
            continue;
        }
        clean[colId] = px;
    }
    return JSON.stringify(clean);
}

/**
 * @param {Record<string, number>} saved
 * @param {Record<string, number>} updates
 */
export function mergeColumnWidths(saved, updates) {
    return parseColumnWidthRaw(serializeColumnWidths({ ...saved, ...updates }));
}

function normalizeColumnWidthPx(colId, width) {
    if (!colId || isSkippedColumnWidthId(colId)) {
        return null;
    }
    const n = Number(width);
    if (!Number.isFinite(n) || n <= 0) {
        return null;
    }
    return Math.round(n);
}

function columnDefId(col) {
    if (col?.colId != null && col.colId !== "") {
        return String(col.colId);
    }
    if (col?.field != null && col.field !== "") {
        return String(col.field);
    }
    return null;
}

function patchColumnDef(col, widths) {
    if (Array.isArray(col?.children) && col.children.length) {
        return {
            ...col,
            children: col.children.map((child) => patchColumnDef(child, widths))
        };
    }
    const id = columnDefId(col);
    if (!id || widths[id] == null) {
        return col;
    }
    const next = { ...col, width: widths[id] };
    delete next.flex;
    return next;
}

/** Saved px replace `flex`, otherwise AG Grid ignores the width. */
export function applySavedColumnWidths(defs, widths) {
    if (!Array.isArray(defs) || !widths || !Object.keys(widths).length) {
        return defs;
    }
    return defs.map((col) => patchColumnDef(col, widths));
}

/** @param {Array<{ getColId?: () => string, getActualWidth?: () => number }>|null|undefined} columns */
export function widthsFromColumns(columns) {
    /** @type {Record<string, number>} */
    const updates = {};
    for (const col of columns || []) {
        const id = col?.getColId?.();
        if (!id) {
            continue;
        }
        updates[id] = col?.getActualWidth?.();
    }
    return updates;
}

/** @returns {string|null} */
export function readColumnWidthRaw(entityKey) {
    const key = getColumnWidthStorageKey(entityKey);
    if (!key || typeof window === "undefined" || !window.localStorage) {
        return null;
    }
    try {
        return window.localStorage.getItem(key);
    } catch (_err) {
        return null;
    }
}

/** @param {Record<string, number>} widths */
export function writeColumnWidths(entityKey, widths) {
    const key = getColumnWidthStorageKey(entityKey);
    if (!key || typeof window === "undefined" || !window.localStorage) {
        return;
    }
    try {
        window.localStorage.setItem(key, serializeColumnWidths(widths));
    } catch (_err) {
        // quota / privacy mode
    }
}
