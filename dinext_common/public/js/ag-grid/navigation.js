// DinextAgGrid excel-style cell navigation (load after utils.js).
(function() {
    const I = window.DinextAgGridInternals = window.DinextAgGridInternals || {};

    function isEditableCell(params) {
        const colDef = params && params.colDef ? params.colDef : {};
        if (typeof colDef.editable === "function") return !!colDef.editable(params);
        return !!colDef.editable;
    }

    function isPinnedRowAtIndex(api, rowIndex) {
        if (!api || !api.getDisplayedRowAtIndex) return false;
        const rowNode = api.getDisplayedRowAtIndex(rowIndex);
        return !!(rowNode && rowNode.rowPinned);
    }

    function buildCellCheckParams(api, rowIndex, column) {
        const rowNode = api.getDisplayedRowAtIndex ? api.getDisplayedRowAtIndex(rowIndex) : null;
        const colDef = column && column.getColDef ? column.getColDef() : {};
        return {
            data: rowNode ? rowNode.data : null,
            node: rowNode,
            colDef,
            column,
            api,
            rowIndex
        };
    }

    function isRowNavigableForTable(table, api, rowIndex, column) {
        if (typeof table.options.isRowNavigable !== "function") return true;
        const rowNode = api.getDisplayedRowAtIndex ? api.getDisplayedRowAtIndex(rowIndex) : null;
        return !!table.options.isRowNavigable({
            table,
            api,
            rowIndex,
            column,
            rowNode,
            data: rowNode ? rowNode.data : null
        });
    }

    function getNextEditableCell(api, focusedCell, direction, table) {
        if (!api || !focusedCell || !table) return null;

        const columns = api.getAllDisplayedColumns ? api.getAllDisplayedColumns() : [];
        const rowCount = api.getDisplayedRowCount ? api.getDisplayedRowCount() : 0;
        const currentColumnIndex = columns.findIndex(column => column.getColId && column.getColId() === focusedCell.column.getColId());

        if (currentColumnIndex < 0 || rowCount <= 0) return null;

        let rowIndex = focusedCell.rowIndex;
        let columnIndex = currentColumnIndex;
        const maxAttempts = columns.length * rowCount + 1;

        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            columnIndex += direction;

            if (columnIndex >= columns.length) {
                columnIndex = 0;
                rowIndex += 1;
            } else if (columnIndex < 0) {
                columnIndex = columns.length - 1;
                rowIndex -= 1;
            }

            if (rowIndex < 0 || rowIndex >= rowCount) return null;

            const column = columns[columnIndex];

            if (table.options.navigateSkipsPinnedRows !== false && isPinnedRowAtIndex(api, rowIndex)) {
                continue;
            }

            if (!isRowNavigableForTable(table, api, rowIndex, column)) {
                continue;
            }

            if (table.options.navigateSkipsNonEditable !== false) {
                if (!isEditableCell(buildCellCheckParams(api, rowIndex, column))) {
                    continue;
                }
            }

            return {
                rowIndex,
                column
            };
        }

        return null;
    }

    I.isEditableCell = isEditableCell;
    I.isPinnedRowAtIndex = isPinnedRowAtIndex;
    I.buildCellCheckParams = buildCellCheckParams;
    I.isRowNavigableForTable = isRowNavigableForTable;
    I.getNextEditableCell = getNextEditableCell;
})();
