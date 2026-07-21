/** @layer rowReorder — row drag-and-drop mutation sources. */
export const ROW_REORDER_SOURCES = {
    REORDER: "rowReorder"
};

/** Drop position relative to hover row. */
export const ROW_REORDER_POSITIONS = {
    BEFORE: "before",
    AFTER: "after",
    INSIDE: "inside"
};

/**
 * Tree reorder policy:
 * - `false` — top-level body rows only
 * - `"siblings"` — before/after within same parent
 * - `"reparent"` — before/after across parents + nest inside
 */
export const ROW_REORDER_TREE_MODES = {
    OFF: false,
    SIBLINGS: "siblings",
    REPARENT: "reparent"
};

/** Matches `TREE_INDENT_PX` in tree/mixin.js — drop line indent. */
export const ROW_REORDER_TREE_INDENT_PX = 20;

/** Base left offset so drop line aligns with tree lead (chevron), not row edge. */
export const ROW_REORDER_INDICATOR_BASE_LEFT_PX = 10;
