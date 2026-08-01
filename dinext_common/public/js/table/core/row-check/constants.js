/** @layer rowCheck — reserved system column id (not a domain field). */
export const ROW_CHECK_COL_ID = "__dinext_row_check";

/** @layer rowCheck — mutation sources for validate/save hooks. */
export const ROW_CHECK_SOURCES = {
    ADD: "rowCheckAdd",
    DELETE: "rowCheckDelete",
    DUPLICATE: "rowCheckDuplicate",
    CHECK: "rowCheckToggle"
};

export const ROW_CHECK_UNITS = {
    ROW: "row",
    MERGE_HEAD: "mergeHead"
};
