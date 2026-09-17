import { DateCellEditor, dateValueFormatter, dateValueParser } from "./date-editor.js";
import { parseDateValue } from "./date-utils.js";
import { NumberCellEditor } from "./number-editor.js";
import { parseLocaleNumber } from "./number-utils.js";
import { SelectCellEditor, selectValueFormatter, selectValueParser } from "./select-editor.js";
import { parseSelectValue } from "./select-utils.js";

export {
    parseDateValue,
    DateCellEditor,
    parseLocaleNumber,
    NumberCellEditor,
    parseSelectValue,
    SelectCellEditor
};

/** Parses boolean from checkbox edit, paste, and fill. Returns null when ambiguous. */
export function parseBooleanValue(raw) {
    if (raw == null || raw === "") {
        return null;
    }
    if (typeof raw === "boolean") {
        return raw;
    }
    if (typeof raw === "number") {
        if (raw === 1) {
            return true;
        }
        if (raw === 0) {
            return false;
        }
        return null;
    }

    const normalized = String(raw).trim().toLowerCase();
    if (["true", "1", "yes", "y", "да", "д"].includes(normalized)) {
        return true;
    }
    if (["false", "0", "no", "n", "нет", "н"].includes(normalized)) {
        return false;
    }
    return null;
}

export function localeNumberValueParser(params) {
    const raw = params.newValue;
    if (raw == null || raw === "") {
        return null;
    }
    const parsed = parseLocaleNumber(raw);
    if (parsed != null) {
        return parsed;
    }
    return params.oldValue === undefined ? null : params.oldValue;
}

function localeIntegerValueParser(params) {
    const raw = params.newValue;
    if (raw == null || raw === "") {
        return null;
    }
    const value = parseLocaleNumber(raw);
    if (value == null) {
        return params.oldValue === undefined ? null : params.oldValue;
    }
    return Math.trunc(value);
}

function booleanValueParser(params) {
    return parseBooleanValue(params.newValue);
}

const CHECKBOX_COLUMN_TYPE = {
    cellDataType: "boolean",
    cellRenderer: "agCheckboxCellRenderer",
    cellEditor: "agCheckboxCellEditor",
    cellClass: "dinext-table-cell--align-center",
    valueParser: booleanValueParser
};

const DEFAULT_COLUMN_TYPES = {
    text: {
        cellDataType: "text"
    },
    number: {
        cellDataType: "number",
        cellClass: "dinext-table-cell--align-right",
        cellEditor: NumberCellEditor,
        valueParser: localeNumberValueParser
    },
    integer: {
        cellDataType: "number",
        cellClass: "dinext-table-cell--align-right",
        cellEditor: NumberCellEditor,
        valueParser: localeIntegerValueParser
    },
    date: {
        // Contract only: ISO YYYY-MM-DD | null. No Desk calendar in core.
        // Interactive editor → column.cellEditor (see usage-guides/date-columns.md).
        // Optional native fallback: DinextTable.DateCellEditor.
        cellDataType: "text",
        valueParser: dateValueParser,
        valueFormatter: dateValueFormatter,
        cellClass: "dinext-table-cell--align-center"
    },
    select: {
        // Contract only: option key string | null. Unknown paste → null.
        // Options: cellEditorParams.values (string[] or (params) => string[]).
        // Interactive editor → column.cellEditor (see usage-guides/select-columns.md).
        // Optional native fallback: DinextTable.SelectCellEditor.
        cellDataType: "text",
        valueParser: selectValueParser,
        valueFormatter: selectValueFormatter
    },
    checkbox: CHECKBOX_COLUMN_TYPE,
    boolean: CHECKBOX_COLUMN_TYPE
};

export const EditorsMixin = (Base) => class extends Base {
    buildEditorsGridOptions() {
        return {
            columnTypes: DEFAULT_COLUMN_TYPES
        };
    }
};
