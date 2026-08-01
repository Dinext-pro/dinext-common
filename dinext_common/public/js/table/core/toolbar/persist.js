import { normalizeFilterState } from "../filter/model.js";

/**
 * Table UI persistence (toolbar pin + filter).
 * Storage key: `dinext-table:toolbar:${persistKey}` (legacy name; payload is UI snapshot).
 *
 * Formats:
 * - legacy: `"1"` | `"0"` → pinned only
 * - v2 JSON: `{ pinned, filter: { active, state } }`
 */

/** @returns {string|null} */
export function getPersistStorageKey(persistKey) {
    return persistKey ? `dinext-table:toolbar:${persistKey}` : null;
}

/**
 * @param {string|null|undefined} raw
 * @returns {{ pinned: boolean|null, filter: { active?: boolean, state?: Record<string, string> }|null }}
 */
export function parseUiPersistRaw(raw) {
    if (raw == null || raw === "") {
        return { pinned: null, filter: null };
    }
    if (raw === "1") {
        return { pinned: true, filter: null };
    }
    if (raw === "0") {
        return { pinned: false, filter: null };
    }

    try {
        const obj = JSON.parse(raw);
        if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
            return { pinned: null, filter: null };
        }

        const pinned = typeof obj.pinned === "boolean" ? obj.pinned : null;
        let filter = null;
        if (obj.filter && typeof obj.filter === "object" && !Array.isArray(obj.filter)) {
            filter = {};
            if (typeof obj.filter.active === "boolean") {
                filter.active = obj.filter.active;
            }
            if (obj.filter.state != null && typeof obj.filter.state === "object") {
                filter.state = normalizeFilterState(obj.filter.state);
            }
        }

        return { pinned, filter };
    } catch (_err) {
        return { pinned: null, filter: null };
    }
}

/**
 * @param {{ pinned?: boolean, filter?: { active?: boolean, state?: Record<string, string> } }} snapshot
 * @returns {string}
 */
export function serializeUiPersist(snapshot = {}) {
    const state = normalizeFilterState(snapshot.filter?.state || {});
    return JSON.stringify({
        pinned: !!snapshot.pinned,
        filter: {
            active: !!snapshot.filter?.active,
            state
        }
    });
}

/**
 * Read localStorage raw value; null if unavailable / missing.
 * @returns {string|null}
 */
export function readUiPersistRaw(persistKey) {
    const key = getPersistStorageKey(persistKey);
    if (!key || typeof window === "undefined" || !window.localStorage) {
        return null;
    }
    try {
        return window.localStorage.getItem(key);
    } catch (_err) {
        return null;
    }
}

/**
 * @param {string|null|undefined} persistKey
 * @param {{ pinned?: boolean, filter?: { active?: boolean, state?: Record<string, string> } }} snapshot
 */
export function writeUiPersist(persistKey, snapshot) {
    const key = getPersistStorageKey(persistKey);
    if (!key || typeof window === "undefined" || !window.localStorage) {
        return;
    }
    try {
        window.localStorage.setItem(key, serializeUiPersist(snapshot));
    } catch (_err) {
        // quota / privacy mode
    }
}
