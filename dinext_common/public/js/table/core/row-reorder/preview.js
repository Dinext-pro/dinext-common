import { getStableRowId } from "./ops.js";
import { ROW_REORDER_POSITIONS } from "./constants.js";

export const ROW_REORDER_TREE_INDENT_PX = 20;
/** Right-shift from drag start → nest under the row above the slot. */
export const NEST_SHIFT_PX = 24;
/** How far into a neighbor row before vertical swap. Same for up and down. */
export const SWAP_EDGE_PX = 2;

const ATTR_TRANSFORM = "data-dinext-rr-tf";
const ATTR_PAD = "data-dinext-rr-pad";
const CLS_SHIFTED = "dinext-table-row--reorder-shifted";
const CLS_PREVIEW_DRAG = "dinext-table-row--reorder-preview-drag";

export function isDraggedPreviewRowId(rowId, draggedIds) {
    const id = String(rowId ?? "");
    for (const draggedId of draggedIds) {
        const prefix = String(draggedId);
        if (id === prefix || id.startsWith(`${prefix}:`)) {
            return true;
        }
    }
    return false;
}

export function hitPreviewRow(hits, clientY) {
    if (!Array.isArray(hits)) {
        return null;
    }
    for (const hit of hits) {
        if (clientY >= hit.top && clientY < hit.bottom) {
            return hit;
        }
    }
    return null;
}

export function buildPreviewHitMap(rows) {
    const hits = [];
    for (const row of rows) {
        const slice = row.slices?.[0];
        if (!slice?.getBoundingClientRect) {
            continue;
        }
        const rect = slice.getBoundingClientRect();
        if (!(rect.height > 0)) {
            continue;
        }
        hits.push({
            rowId: row.rowId,
            top: rect.top,
            bottom: rect.bottom,
            height: rect.height,
            isDragged: !!row.isDragged
        });
    }
    return hits;
}

export function isHomePreviewHit(hit, draggedIds) {
    return !!hit && (hit.isDragged || isDraggedPreviewRowId(hit.rowId, draggedIds));
}

export function previousPreviewHit(hits, hit) {
    if (!Array.isArray(hits) || !hit) {
        return null;
    }
    const index = hits.findIndex((item) => item.rowId === hit.rowId);
    for (let i = index - 1; i >= 0; i--) {
        if (!hits[i].isDragged) {
            return hits[i];
        }
    }
    return null;
}

/**
 * Vertical swap vs original home slot. Enter neighbor by SWAP_EDGE_PX → swap.
 * Down = after that row. Up = before that row. Symmetric.
 */
export function resolveVerticalIntent({ hits, clientY, draggedIds }) {
    const list = hits || [];
    const homeHits = list.filter((hit) => isHomePreviewHit(hit, draggedIds));
    const others = list.filter((hit) => !isHomePreviewHit(hit, draggedIds));

    if (!homeHits.length) {
        return null;
    }

    const homeTop = Math.min(...homeHits.map((hit) => hit.top));
    const homeBottom = Math.max(...homeHits.map((hit) => hit.bottom));

    if (clientY >= homeTop && clientY < homeBottom) {
        return { home: true };
    }

    const hit = hitPreviewRow(others, clientY);
    if (!hit) {
        if (clientY >= homeBottom && clientY < homeBottom + SWAP_EDGE_PX) {
            return { home: true };
        }
        if (clientY < homeTop && clientY > homeTop - SWAP_EDGE_PX) {
            return { home: true };
        }
        return null;
    }

    if (hit.top >= homeBottom - 1) {
        const adjacent = Math.abs(hit.top - homeBottom) <= 1;
        if (adjacent && clientY < hit.top + SWAP_EDGE_PX) {
            return { home: true };
        }
        return { home: false, hoverRowId: hit.rowId, position: ROW_REORDER_POSITIONS.AFTER };
    }

    if (hit.bottom <= homeTop + 1) {
        const adjacent = Math.abs(homeTop - hit.bottom) <= 1;
        if (adjacent && clientY > hit.bottom - SWAP_EDGE_PX) {
            return { home: true };
        }
        return { home: false, hoverRowId: hit.rowId, position: ROW_REORDER_POSITIONS.BEFORE };
    }

    return { home: true };
}

function firstHomePreviewHit(hits, draggedIds) {
    const homeHits = (hits || []).filter((hit) => isHomePreviewHit(hit, draggedIds));
    if (!homeHits.length) {
        return null;
    }
    return homeHits.reduce((first, hit) => (hit.top < first.top ? hit : first));
}

/** Parent for nest: the row that sits above the insert slot. */
export function resolveNestParentHit(hits, vertical, draggedIds) {
    if (!vertical) {
        return null;
    }
    if (vertical.home) {
        return previousPreviewHit(hits, firstHomePreviewHit(hits, draggedIds));
    }
    const hover = (hits || []).find((hit) => hit.rowId === vertical.hoverRowId);
    if (vertical.position === ROW_REORDER_POSITIONS.AFTER) {
        return hover && !isHomePreviewHit(hover, draggedIds) ? hover : null;
    }
    return previousPreviewHit(hits, hover);
}

/**
 * Vertical = before/after after SWAP_EDGE_PX into the neighbor.
 * Right shift ≥ NEST_SHIFT_PX = nest into the row above the slot
 * (not the swapped neighbor). Home + right = nest under the row above.
 */
export function resolveReorderIntent({
    hits,
    clientY,
    clientX,
    startClientX,
    allowNest,
    draggedIds
}) {
    const vertical = resolveVerticalIntent({ hits, clientY, draggedIds });
    if (!vertical) {
        return null;
    }

    const nest = !!allowNest && (clientX - startClientX) >= NEST_SHIFT_PX;
    if (nest) {
        const parent = resolveNestParentHit(hits, vertical, draggedIds);
        if (parent) {
            return {
                hoverRowId: parent.rowId,
                position: ROW_REORDER_POSITIONS.INSIDE
            };
        }
    }

    if (vertical.home) {
        return vertical;
    }

    return { hoverRowId: vertical.hoverRowId, position: vertical.position };
}

export function previewTargetKey(dropTarget) {
    if (!dropTarget) {
        return "";
    }
    return `${dropTarget.position}:${dropTarget.targetRowId}:${dropTarget.toParentRowId ?? ""}`;
}

/**
 * Pure layout: original Y of displayed rows → preview Y + indent delta.
 * `rows` must be sorted by original `y`.
 * @returns {Array<{ rowId: string, y: number, indentDelta: number, isDragged: boolean }> | null}
 */
export function planRowReorderPreview(rows, dropTarget) {
    if (!Array.isArray(rows) || !rows.length || !dropTarget) {
        return null;
    }

    const dragged = rows.filter((row) => row.isDragged);
    if (!dragged.length) {
        return null;
    }

    const slotY = resolvePreviewSlotY(rows, dropTarget);
    if (slotY == null) {
        return null;
    }

    const blockTop = dragged[0].y;
    const blockHeight = dragged.reduce((sum, row) => sum + row.height, 0);
    const blockBottom = blockTop + blockHeight;
    const fromLevel = Number(dragged[0].level) || 0;
    const toLevel = Number(dropTarget.indentLevel);
    const indentDelta = Number.isFinite(toLevel)
        ? (toLevel - fromLevel) * ROW_REORDER_TREE_INDENT_PX
        : 0;

    let destY = slotY;
    if (slotY >= blockBottom) {
        destY = slotY - blockHeight;
    }
    if (destY === blockTop && indentDelta === 0) {
        return null;
    }

    const planned = [];
    for (const row of rows) {
        if (row.isDragged) {
            continue;
        }
        let y = row.y;
        if (slotY <= blockTop && row.y >= slotY && row.y < blockTop) {
            y += blockHeight;
        } else if (slotY >= blockBottom && row.y >= blockBottom && row.y < slotY) {
            y -= blockHeight;
        }
        planned.push({
            rowId: row.rowId,
            y,
            indentDelta: 0,
            isDragged: false
        });
    }

    let cursor = destY;
    for (const row of dragged) {
        planned.push({
            rowId: row.rowId,
            y: cursor,
            indentDelta,
            isDragged: true
        });
        cursor += row.height;
    }

    return planned;
}

export function resolvePreviewSlotY(rows, dropTarget) {
    const hoverId = String(dropTarget.targetRowId ?? "");
    const hover = rows.find((row) => row.rowId === hoverId && !row.isDragged);
    if (!hover) {
        return null;
    }

    if (dropTarget.position === ROW_REORDER_POSITIONS.BEFORE) {
        return hover.y;
    }

    const last = lastVisibleInSubtree(rows, hoverId) || hover;
    return last.y + last.height;
}

function lastVisibleInSubtree(rows, ancestorId) {
    const prefix = `${ancestorId}:`;
    let last = null;
    for (const row of rows) {
        if (row.isDragged) {
            continue;
        }
        if (row.rowId === ancestorId || String(row.rowId).startsWith(prefix)) {
            last = row;
        }
    }
    return last;
}

export function readRowTranslateY(el) {
    if (!el) {
        return 0;
    }
    const transform = el.style.transform || "";
    const match = transform.match(/translateY\(\s*(-?[\d.]+)px\s*\)/);
    if (match) {
        return Number(match[1]);
    }
    const top = Number.parseFloat(el.style.top);
    if (Number.isFinite(top)) {
        return top;
    }
    return el.offsetTop || 0;
}

export function collectPreviewRows(table, section, draggedIds) {
    const rows = [];
    if (!table?.api || !table.container) {
        return rows;
    }

    table.api.forEachNode((node) => {
        if (!node?.data || node.rowIndex == null) {
            return;
        }
        if (typeof table.resolveRowReorderSection === "function"
            && table.resolveRowReorderSection(node.data) !== section) {
            return;
        }

        const rowIndex = node.rowIndex;
        const slices = queryRowSlices(table.container, rowIndex);
        if (!slices.length) {
            return;
        }

        const rowId = getStableRowId(node.data, table.options);
        rows.push({
            rowIndex,
            rowId,
            node,
            slices,
            y: readRowTranslateY(slices[0]),
            height: slices[0].offsetHeight || 28,
            level: Number(node.data?._level) || 0,
            isDragged: isDraggedPreviewRowId(rowId, draggedIds)
        });
    });

    rows.sort((a, b) => a.y - b.y || a.rowIndex - b.rowIndex);
    return rows;
}

export function applyRowReorderPreviewPlan(rows, plan) {
    if (!plan?.length) {
        return false;
    }

    const byId = new Map(rows.map((row) => [row.rowId, row]));
    for (const item of plan) {
        const row = byId.get(item.rowId);
        if (!row) {
            continue;
        }
        for (const slice of row.slices) {
            rememberRowTransform(slice);
            slice.style.transform = `translateY(${item.y}px)`;
            slice.classList.add(CLS_SHIFTED);
            slice.classList.toggle(CLS_PREVIEW_DRAG, item.isDragged);
            applyTreeIndentDelta(slice, item.indentDelta);
        }
    }
    return true;
}

export function clearRowReorderPreview(container) {
    if (!container) {
        return;
    }
    container.querySelectorAll(`.ag-row.${CLS_SHIFTED}, .ag-row.${CLS_PREVIEW_DRAG}`).forEach((el) => {
        restoreRowTransform(el);
        restoreTreeIndent(el);
        el.classList.remove(CLS_SHIFTED, CLS_PREVIEW_DRAG);
    });
}

function queryRowSlices(container, rowIndex) {
    const safeIndex = typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(String(rowIndex))
        : String(rowIndex);
    return [...container.querySelectorAll(`.ag-row[row-index="${safeIndex}"]`)];
}

function rememberRowTransform(el) {
    if (!el.hasAttribute(ATTR_TRANSFORM)) {
        el.setAttribute(ATTR_TRANSFORM, el.style.transform || "");
    }
}

function restoreRowTransform(el) {
    if (!el.hasAttribute(ATTR_TRANSFORM)) {
        return;
    }
    el.style.transform = el.getAttribute(ATTR_TRANSFORM) || "";
    el.removeAttribute(ATTR_TRANSFORM);
}

function applyTreeIndentDelta(rowEl, indentDelta) {
    rowEl.querySelectorAll(".dinext-table-tree-cell").forEach((cell) => {
        if (!cell.hasAttribute(ATTR_PAD)) {
            cell.setAttribute(ATTR_PAD, cell.style.paddingLeft || "");
        }
        const base = Number.parseFloat(cell.getAttribute(ATTR_PAD)) || 0;
        cell.style.paddingLeft = `${Math.max(0, base + indentDelta)}px`;
    });
}

function restoreTreeIndent(rowEl) {
    rowEl.querySelectorAll(".dinext-table-tree-cell").forEach((cell) => {
        if (!cell.hasAttribute(ATTR_PAD)) {
            return;
        }
        cell.style.paddingLeft = cell.getAttribute(ATTR_PAD) || "";
        cell.removeAttribute(ATTR_PAD);
    });
}
