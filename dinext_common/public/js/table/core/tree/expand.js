/**
 * Shared expand/collapse for body tree and pinned summary tree.
 * Callers supply ctx so reveal/hide stay section-specific
 * (applyTransaction vs pinnedBottomRowData resync).
 */

export function clearExpandedDescendantIds(expandedIds, rowId) {
    rowId = String(rowId);
    const prefix = `${rowId}:`;
    for (const id of [...expandedIds]) {
        if (id.startsWith(prefix)) {
            expandedIds.delete(id);
        }
    }
}

/**
 * @param {object} table
 * @param {string} rowId
 * @param {{
 *   expandedIds: Set<string>,
 *   getChildren: (rowId: string) => any[],
 *   revealChildren: (rowId: string, meta: { lazy: boolean }) => void,
 *   expandCallbackExtra?: object
 * }} ctx
 */
export async function expandTreeRow(table, rowId, ctx) {
    rowId = String(rowId);
    if (ctx.expandedIds.has(rowId)) {
        return;
    }

    const eagerChildren = ctx.getChildren(rowId);
    const needsLazyLoad = !eagerChildren.length
        && typeof table.options.onExpandRow === "function";

    if (!eagerChildren.length && !needsLazyLoad) {
        return;
    }

    ctx.expandedIds.add(rowId);

    if (needsLazyLoad) {
        table.setRowLoading(rowId, true);
        try {
            await table.options.onExpandRow({
                rowId,
                row: table.findSourceRow(rowId),
                table,
                ...(ctx.expandCallbackExtra || {})
            });
        } finally {
            table.setRowLoading(rowId, false);
        }
        if (!ctx.getChildren(rowId).length) {
            ctx.expandedIds.delete(rowId);
        }
        ctx.revealChildren(rowId, { lazy: true });
        table.refreshTreeToggle(rowId);
        return;
    }

    ctx.revealChildren(rowId, { lazy: false });
    table.refreshTreeToggle(rowId);
}

/**
 * @param {object} table
 * @param {string} rowId
 * @param {{
 *   expandedIds: Set<string>,
 *   clearDescendants: (rowId: string) => void,
 *   hideDescendants: (rowId: string) => void
 * }} ctx
 */
export function collapseTreeRow(table, rowId, ctx) {
    rowId = String(rowId);
    if (!ctx.expandedIds.has(rowId)) {
        return;
    }
    ctx.expandedIds.delete(rowId);
    ctx.clearDescendants(rowId);
    ctx.hideDescendants(rowId);
    table.refreshTreeToggle(rowId);
}
