// DinextAgGrid shared helpers (load after loader.js).
(function() {
    const I = window.DinextAgGridInternals = window.DinextAgGridInternals || {};

    if (typeof I.fallbackRowIdCounter !== "number") {
        I.fallbackRowIdCounter = 0;
    }
    if (!I.fallbackRowIds && typeof WeakMap === "function") {
        I.fallbackRowIds = new WeakMap();
    }

    function isFrappeDarkTheme() {
        const root = document.documentElement;
        const resolvedTheme = root.getAttribute("data-theme");
        const selectedTheme = root.getAttribute("data-theme-mode");

        if (resolvedTheme) return resolvedTheme === "dark";
        return selectedTheme === "dark";
    }

    function translate(text) {
        return typeof window.__ === "function" ? window.__(text) : text;
    }

    function toClassList(value, params) {
        if (!value) return [];
        if (typeof value === "function") return toClassList(value(params), params);
        if (Array.isArray(value)) return value.flatMap(item => toClassList(item, params));
        if (typeof value === "object") {
            return Object.keys(value).filter(className => !!value[className]);
        }
        return String(value).split(/\s+/).filter(Boolean);
    }

    function mergeStyles(first, second, params) {
        const firstValue = typeof first === "function" ? first(params) : first;
        const secondValue = typeof second === "function" ? second(params) : second;

        return Object.assign({}, firstValue || {}, secondValue || {});
    }

    function mergeCallbacks(first, second) {
        if (typeof first !== "function") return second;
        if (typeof second !== "function") return first;

        return function(params) {
            first(params);
            return second(params);
        };
    }

    function getStableFallbackRowId(row) {
        if (row && (typeof row === "object" || typeof row === "function") && I.fallbackRowIds) {
            let id = I.fallbackRowIds.get(row);
            if (!id) {
                I.fallbackRowIdCounter += 1;
                id = `row-fallback-${I.fallbackRowIdCounter}`;
                I.fallbackRowIds.set(row, id);
            }
            return id;
        }

        return `row-value:${typeof row}:${String(row)}`;
    }

    function getRowKey(row, index, rowKey) {
        if (typeof rowKey === "function") {
            const customKey = rowKey(row, index);
            if (customKey != null) return customKey;
        }
        if (rowKey && row && row[rowKey] != null) return row[rowKey];
        if (row && row.name != null) return row.name;
        return getStableFallbackRowId(row);
    }

    function rollbackCellValue(params) {
        if (!params || !params.data) return;

        const field = params.colDef && params.colDef.field;
        const colId = params.column && typeof params.column.getColId === "function"
            ? params.column.getColId()
            : null;
        const key = field || colId;

        if (key) {
            params.data[key] = params.oldValue;
        }
    }

    function resolveWidth(column) {
        if (!column) return undefined;

        const ownDescriptor = Object.getOwnPropertyDescriptor(column, "width");
        if (ownDescriptor && typeof ownDescriptor.get === "function") {
            return ownDescriptor.get.call(column);
        }

        const proto = Object.getPrototypeOf(column);
        const protoDescriptor = proto ? Object.getOwnPropertyDescriptor(proto, "width") : null;
        if (protoDescriptor && typeof protoDescriptor.get === "function") {
            return protoDescriptor.get.call(column);
        }

        if (typeof column.width === "function") {
            return column.width();
        }

        return column.width;
    }

    function warnColumnDeprecationOnce(key, message) {
        if (!I._columnDeprecationWarned) I._columnDeprecationWarned = {};
        if (I._columnDeprecationWarned[key]) return;
        I._columnDeprecationWarned[key] = true;
        console.warn(message);
    }

    /** AG Grid header with HTML (supports &lt;br&gt; for two-line headers). */
    class DinextAgGridHtmlHeader {
        init(params) {
            const rawHtml = params.html || params.displayName || "";
            const parts = String(rawHtml)
                .split(/<br\s*\/?>/i)
                .map(part => part.replace(/<\/?small>/gi, "").trim())
                .filter(Boolean);

            this.eGui = document.createElement("div");
            const extraClass = params.headerClass ? String(params.headerClass) : "";
            this.eGui.className = ["dinext-ag-grid-html-header", "projects-workload-ag-grid-header", extraClass]
                .filter(Boolean)
                .join(" ");

            if (parts.length > 1) {
                this.eGui.innerHTML = `
                    <div class="projects-workload-ag-grid-header-main">${parts[0]}</div>
                    <div class="projects-workload-ag-grid-header-sub">${parts.slice(1).join(" ")}</div>
                `;
            } else {
                this.eGui.innerHTML = `<div class="projects-workload-ag-grid-header-single">${parts[0] || rawHtml}</div>`;
            }
        }

        getGui() {
            return this.eGui;
        }
    }

    function htmlHeaderParams(headerHtml, options) {
        const opts = options || {};
        return {
            headerComponent: "dinextHtmlHeader",
            headerComponentParams: {
                html: headerHtml || "",
                headerClass: opts.headerClass || opts.className
            }
        };
    }

    function ensureFieldIds(def, fallbackField) {
        const field = def.field || def.colId || def.id || fallbackField;
        return Object.assign({}, def, {
            field,
            colId: def.colId || field
        });
    }

    function participantColumnDef(overrides) {
        return ensureFieldIds(Object.assign({
            field: "participant",
            colId: "participant",
            pinned: "left",
            lockPinned: true,
            suppressMovable: true,
            sortable: true,
            resizable: true
        }, overrides), "participant");
    }

    function wrapHtmlCellRenderer(renderer) {
        if (typeof renderer !== "function") {
            return renderer;
        }
        return params => {
            const html = renderer(params);
            if (html == null || html === "") {
                return "";
            }
            if (typeof html !== "string") {
                return html;
            }
            const el = document.createElement("div");
            el.innerHTML = html;
            return el;
        };
    }

    function normalizeColumn(column, index, table) {
        const source = column || {};
        const field = source.field || source.colId || `col_${index}`;
        if (!source.field && !source.colId) {
            throw new Error(
                `DinextAgGrid: columnDefs[${index}] requires field or colId (legacy id/name/format removed).`
            );
        }
        const cellClass = source.cellClass;
        const cellStyle = source.cellStyle;
        const headerClass = source.headerClass;
        const cellRenderer = wrapHtmlCellRenderer(source.cellRenderer);

        const resolvedWidth = resolveWidth(source);
        const normalized = Object.assign({}, source, {
            field,
            colId: source.colId || field,
            headerName: source.headerName || source.label || "",
            cellClass: params => [
                ...toClassList(table.options.getCellClass, params),
                ...toClassList(cellClass, params)
            ],
            cellStyle: params => mergeStyles(table.options.getCellStyle, cellStyle, params),
            cellRenderer,
            headerClass: params => [
                ...toClassList(table.options.getHeaderClass, params),
                ...toClassList(headerClass, params)
            ]
        });

        if (resolvedWidth != null) {
            normalized.width = Number(resolvedWidth) || resolvedWidth;
        }

        return normalized;
    }

    I.isFrappeDarkTheme = isFrappeDarkTheme;
    I.translate = translate;
    I.toClassList = toClassList;
    I.mergeStyles = mergeStyles;
    I.mergeCallbacks = mergeCallbacks;
    I.getStableFallbackRowId = getStableFallbackRowId;
    I.getRowKey = getRowKey;
    I.rollbackCellValue = rollbackCellValue;
    I.resolveWidth = resolveWidth;
    I.warnColumnDeprecationOnce = warnColumnDeprecationOnce;
    I.normalizeColumn = normalizeColumn;
    I.DinextAgGridHtmlHeader = DinextAgGridHtmlHeader;
    I.htmlHeaderParams = htmlHeaderParams;
    I.ensureFieldIds = ensureFieldIds;
    I.participantColumnDef = participantColumnDef;
})();
