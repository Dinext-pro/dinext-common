// Shared tree cell HTML helpers (load after utils.js).
(function() {
    const I = window.DinextAgGridInternals = window.DinextAgGridInternals || {};

    function escapeHtml(value) {
        if (window.frappe && typeof window.frappe.utils.escape_html === "function") {
            return window.frappe.utils.escape_html(value == null ? "" : String(value));
        }
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function resolveRowKey(table, row, options) {
        const opts = options || {};
        if (opts.rowKeyField && row && row[opts.rowKeyField] != null) {
            return row[opts.rowKeyField];
        }
        if (table && typeof table.getRowKey === "function") {
            return table.getRowKey(row, opts.rowIndex);
        }
        if (row && row.value != null) return row.value;
        if (row && row.name != null) return row.name;
        return "";
    }

    function resolveIndent(table, row, options) {
        const opts = options || {};
        const multiplier = opts.indentMultiplier != null ? Number(opts.indentMultiplier) : 18;

        if (opts.indentField && row) {
            const raw = Number(row[opts.indentField]) || 0;
            return Math.max(0, raw) * multiplier;
        }
        if (table && typeof table.getRowLevel === "function") {
            return table.getRowLevel(row, opts.rowIndex) * multiplier;
        }
        return 0;
    }

    function resolveExpandable(table, row, options) {
        const opts = options || {};
        if (typeof opts.isExpandable === "function") {
            return !!opts.isExpandable(table, row);
        }
        if (table && typeof table.hasChildren === "function") {
            return !!table.hasChildren(row);
        }
        if (table && typeof table.isRowExpandable === "function") {
            return !!table.isRowExpandable(row, opts.rowIndex);
        }
        return false;
    }

    function resolveExpanded(table, rowKey, options) {
        const opts = options || {};
        if (typeof opts.isExpanded === "function") {
            return !!opts.isExpanded(table, rowKey, opts.row);
        }
        return !!(table && table.expandedRows && table.expandedRows.has(rowKey));
    }

    function buildTreeToggleHtml(table, row, options) {
        const opts = options || {};
        const rowKey = resolveRowKey(table, row, opts);
        const expandable = resolveExpandable(table, row, opts);
        const expanded = resolveExpanded(table, rowKey, Object.assign({}, opts, { row }));
        const toggleClass = opts.toggleClass || "dinext-ag-grid-tree-toggle";
        const toggleTag = opts.toggleTag || "span";
        const icon = expanded ? "⌄" : "›";

        if (opts.useFeatherIcons) {
            if (!expandable) {
                return `<span class="${toggleClass}"></span>`;
            }

            const toggleSvgClass = expanded ? "feather-chevron-down" : "feather-chevron-right";
            const outerClass = [opts.toggleOuterClass, toggleClass].filter(Boolean).join(" ");
            const labelClass = opts.toggleLabelClass || "dinext-ag-grid-toggle-label";
            return `<span class="dt-tree-node__toggle ${outerClass}">
                <svg class="${toggleSvgClass}" aria-hidden="true"><use href="#icon-${toggleSvgClass}"></use></svg>
                <span class="${labelClass}">${icon}</span>
            </span>`;
        }

        const typeAttr = toggleTag === "button" ? ' type="button"' : "";
        const dataRowKey = opts.toggleDataRowKey !== false && toggleTag === "button"
            ? ` data-row-key="${escapeHtml(rowKey)}"`
            : "";

        return `<${toggleTag} class="${toggleClass}"${typeAttr}${dataRowKey}>${expandable ? icon : ""}</${toggleTag}>`;
    }

    function wrapTreeCellContent(innerHtml, row, options) {
        const opts = options || {};
        const table = opts.table;
        const indent = resolveIndent(table, row, opts);
        const wrapperClass = opts.wrapperClass || "dinext-ag-grid-tree-cell";
        const contentClass = opts.contentClass || "dinext-ag-grid-tree-content";
        const wrapperAttrs = opts.wrapperAttrs || "";
        const extraStyle = opts.wrapperStyle || "";
        const style = extraStyle
            ? `padding-left: ${indent}px; ${extraStyle}`
            : `padding-left: ${indent}px`;
        const toggleHtml = typeof opts.toggleHtml === "string"
            ? opts.toggleHtml
            : buildTreeToggleHtml(table, row, opts);

        return `<div class="${wrapperClass}"${wrapperAttrs} style="${style}">
            ${toggleHtml}
            <span class="${contentClass}">${innerHtml == null ? "" : innerHtml}</span>
        </div>`;
    }

    const treeCell = {
        buildTreeToggleHtml,
        wrapTreeCellContent,
        resolveRowKey,
        resolveIndent,
        resolveExpandable
    };

    I.buildTreeToggleHtml = buildTreeToggleHtml;
    I.wrapTreeCellContent = wrapTreeCellContent;
    I.treeCell = treeCell;

    if (window.DinextAgGrid) {
        window.DinextAgGrid.treeCell = treeCell;
    }
})();
