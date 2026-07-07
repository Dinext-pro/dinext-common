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

function localeNumberValueParser(params) {
    return parseLocaleNumber(params.newValue);
}

function localeIntegerValueParser(params) {
    const value = parseLocaleNumber(params.newValue);
    return value == null ? null : Math.trunc(value);
}

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
    }
};

export const EditorsMixin = (Base) => class extends Base {
    buildEditorsGridOptions() {
        return {
            columnTypes: DEFAULT_COLUMN_TYPES
        };
    }
};
