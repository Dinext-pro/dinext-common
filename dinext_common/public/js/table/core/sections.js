/** @layer section — logical table sections (body / summary). */

export const TABLE_SECTIONS = {
    BODY: "body",
    SUMMARY: "summary"
};

/** Body is default when `_section` is absent on source rows. */
export function getRowSection(row) {
    if (row?._section === TABLE_SECTIONS.SUMMARY) {
        return TABLE_SECTIONS.SUMMARY;
    }
    return TABLE_SECTIONS.BODY;
}

export function isSummarySectionRow(row) {
    return getRowSection(row) === TABLE_SECTIONS.SUMMARY;
}

/** Stamp visible summary rows only — body rows stay without `_section`. */
export function stampSummaryRows(rows) {
    return (rows || []).map((row) => (
        row._section === TABLE_SECTIONS.SUMMARY
            ? row
            : { ...row, _section: TABLE_SECTIONS.SUMMARY }
    ));
}
