// Pure Work Efforts column helpers (header HTML, cell class, tree wrap options).
// pushWorkEffortsDomainColumn stays in Project WE Client Script — needs frm, renderHtml, ctx lifecycle.
(function() {
    const HEADER_CLASS = "work-efforts-ag-grid-header";
    const TREE_INDENT_MULTIPLIER = 40;

    function workEffortsColumnHeader(columnMeta) {
        const Col = window.DinextAgGrid && window.DinextAgGrid.column;
        if (columnMeta.headerHtml != null) {
            return Col
                ? Col.htmlHeader(columnMeta.headerHtml, { headerClass: HEADER_CLASS })
                : {
                    headerComponent: "dinextHtmlHeader",
                    headerComponentParams: {
                        html: columnMeta.headerHtml,
                        headerClass: HEADER_CLASS
                    }
                };
        }
        return { headerName: columnMeta.headerName || "" };
    }

    function buildWorkEffortsCellClass(columnMeta, metaColIndex) {
        return params => {
            const classes = [`work-efforts-ag-grid-cell-${columnMeta.id || params.column.getColId()}`];
            if (columnMeta.treeView) classes.push("work-efforts-ag-grid-tree-cell");
            if (params.data && params.data._weIsTotalRow) {
                classes.push("work-efforts-ag-grid-total-cell");
            }
            classes.push(`dt-cell__content--col-${metaColIndex}`);
            return classes;
        };
    }

    function buildWorkEffortsTreeCellWrapOptions(table, row) {
        return {
            table,
            indentMultiplier: TREE_INDENT_MULTIPLIER,
            indentField: "indent",
            rowKeyField: "value",
            isExpandable: (t, r) => t.hasChildren(r),
            wrapperClass: "dt-tree-node work-efforts-ag-grid-tree-node",
            wrapperAttrs: ` data-task-id="${row.value || ""}" data-indent="${row.indent || 0}"`,
            toggleClass: "work-efforts-ag-grid-toggle",
            toggleOuterClass: "work-efforts-ag-grid-toggle",
            toggleLabelClass: "work-efforts-ag-grid-toggle-label",
            contentClass: "work-efforts-ag-grid-tree-content",
            useFeatherIcons: true
        };
    }

    function wrapWorkEffortsTreeCellContent(html, table, row) {
        if (!table) return html;
        const treeCell = (window.DinextAgGrid && window.DinextAgGrid.treeCell)
            || (window.DinextAgGridInternals && window.DinextAgGridInternals.treeCell);
        if (!treeCell || typeof treeCell.wrapTreeCellContent !== "function") {
            return html;
        }
        return treeCell.wrapTreeCellContent(html, row, buildWorkEffortsTreeCellWrapOptions(table, row));
    }

    const helpers = {
        HEADER_CLASS,
        TREE_INDENT_MULTIPLIER,
        workEffortsColumnHeader,
        buildWorkEffortsCellClass,
        buildWorkEffortsTreeCellWrapOptions,
        wrapWorkEffortsTreeCellContent
    };

    window.DinextWorkEffortsColumnHelpers = helpers;

    if (window.DinextAgGrid) {
        window.DinextAgGrid.presets = window.DinextAgGrid.presets || {};
        window.DinextAgGrid.presets.workEffortsHelpers = helpers;
    }
})();
