import {
    applySavedColumnWidths,
    COLUMN_WIDTH_USER_SOURCE,
    mergeColumnWidths,
    parseColumnWidthRaw,
    readColumnWidthRaw,
    resolveColumnWidthEntityKey,
    widthsFromColumns,
    writeColumnWidths
} from "./model.js";

export const ColumnWidthMixin = (Base) => class extends Base {
    buildColumnDefs() {
        const defs = super.buildColumnDefs();
        return applySavedColumnWidths(defs, this.readSavedColumnWidths());
    }

    buildColumnWidthGridOptions() {
        return {
            onColumnResized: (event) => this.rememberColumnWidths(event)
        };
    }

    readSavedColumnWidths() {
        const entityKey = resolveColumnWidthEntityKey(this.options);
        if (!entityKey) {
            return {};
        }
        return parseColumnWidthRaw(readColumnWidthRaw(entityKey));
    }

    rememberColumnWidths(event) {
        if (!event?.finished || event.source !== COLUMN_WIDTH_USER_SOURCE) {
            return;
        }
        const entityKey = resolveColumnWidthEntityKey(this.options);
        if (!entityKey) {
            return;
        }
        const cols = event.columns?.length
            ? event.columns
            : (event.column ? [event.column] : []);
        const updates = widthsFromColumns(cols);
        if (!Object.keys(updates).length) {
            return;
        }
        writeColumnWidths(entityKey, mergeColumnWidths(this.readSavedColumnWidths(), updates));
    }
};
