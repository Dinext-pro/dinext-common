/** @layer rowReorder — reserved system column id (not a domain field). */
export const ROW_REORDER_COL_ID = "__dinext_row_reorder";

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
