/** Parses user input with comma or dot decimal separator. Returns null for empty/invalid. */
export function parseLocaleNumber(raw) {
    if (raw == null || raw === "") {
        return null;
    }
    if (typeof raw === "number") {
        return Number.isFinite(raw) ? raw : null;
    }

    const trimmed = String(raw).trim().replace(/\s/g, "");
    if (!trimmed) {
        return null;
    }

    const normalized = trimmed.includes(",") && !trimmed.includes(".")
        ? trimmed.replace(",", ".")
        : trimmed.replace(/,/g, "");
    const value = Number(normalized);
    return Number.isFinite(value) ? value : null;
}

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

function localeNumberValueParser(params) {
    return parseLocaleNumber(params.newValue);
}

function localeIntegerValueParser(params) {
    const value = parseLocaleNumber(params.newValue);
    return value == null ? null : Math.trunc(value);
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
        valueParser: localeNumberValueParser
    },
    integer: {
        cellDataType: "number",
        cellClass: "dinext-table-cell--align-right",
        valueParser: localeIntegerValueParser
    },
    date: {
        cellDataType: "date"
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
