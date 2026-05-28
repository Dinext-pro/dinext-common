// DinextAgGrid.TreeReport — общий слой expand/collapse для AG Grid tree/report таблиц.
//
// Options:
//   getRowKey(row, index) — required
//   getParentKey(row, index) — required
//   visibilityMode — "parent" (default) | "level"
//   getRowLevel(row, index) — required when visibilityMode === "level"; also used by setTreeDepth()
//   isRowExpandable(row, index) — optional
//   expandedRows — optional Set
//   rows — initial row set (full dataset; visibility filtering in renderRows)
//
// API:
//   toggleRow(rowKey) — rowKey: string, toggles expand state for that node
//   collapseAll() — collapse all expanded nodes
//   showRows(rowIndices) — expand ancestors for given full-dataset indices
//   setTreeDepth(depth) — parent mode: expand all expandable rows with getRowLevel(row) < depth
//   openRow(rowIndex) — expand single node at full-dataset index
//   getRowAt(index) — row from full dataset
//   getCheckedRowIndices() — selected row indices in full dataset (AG Grid selection)
//   visibleRowIndices — getter, indices into full row set for currently visible rows (parent mode)
//   rows — getter/setter alias for full dataset (_allRows), not the filtered grid rowData
(function() {
    const Table = window.DinextAgGrid && window.DinextAgGrid.Table;
    if (!Table) {
        throw new Error("DinextAgGrid.Table must be loaded before ag-grid/tree-report.js");
    }

    function defaultIsRowExpandable(row, index, allRows, getRowKey, getParentKey) {
        if (!row) return false;
        const key = getRowKey(row, index);
        return allRows.some((candidate, candidateIndex) => {
            if (candidate === row) return false;
            return getParentKey(candidate, candidateIndex) === key;
        });
    }

    class DinextAgGridTreeReport extends Table {
        constructor(container, options = {}) {
            if (typeof options.getRowKey !== "function") {
                throw new Error("DinextAgGrid.TreeReport: options.getRowKey is required");
            }

            const visibilityMode = options.visibilityMode === "level" ? "level" : "parent";
            if (visibilityMode === "parent" && typeof options.getParentKey !== "function") {
                throw new Error("DinextAgGrid.TreeReport: options.getParentKey is required when visibilityMode is \"parent\"");
            }
            if (visibilityMode === "level" && typeof options.getRowLevel !== "function") {
                throw new Error("DinextAgGrid.TreeReport: options.getRowLevel is required when visibilityMode is \"level\"");
            }

            const initialRows = options.rows ?? [];
            const tableOptions = Object.assign({}, options, {
                rows: [],
                rowKey: options.getRowKey
            });

            super(container, tableOptions);

            this._allRows = Array.isArray(initialRows) ? initialRows.slice() : [];
            this.visibilityMode = visibilityMode;
            this.getRowKeyFn = options.getRowKey;
            this.getParentKeyFn = typeof options.getParentKey === "function"
                ? options.getParentKey
                : () => "";
            this.getRowLevelFn = typeof options.getRowLevel === "function" ? options.getRowLevel : null;
            this.isRowExpandableFn = typeof options.isRowExpandable === "function"
                ? options.isRowExpandable
                : (row, index) => defaultIsRowExpandable(
                    row,
                    index,
                    this._allRows,
                    (candidate, candidateIndex) => this.getRowKey(candidate, candidateIndex),
                    (candidate, candidateIndex) => this.getParentKey(candidate, candidateIndex)
                );
            this.expandedRows = options.expandedRows instanceof Set ? options.expandedRows : new Set();
            this._visibleRows = [];
            this._visibleRowIndices = [];

            Object.defineProperty(this, "rows", {
                configurable: true,
                enumerable: true,
                get: () => this._allRows,
                set: value => {
                    this._allRows = Array.isArray(value) ? value.slice() : [];
                }
            });

            Object.defineProperty(this, "visibleRowIndices", {
                configurable: true,
                enumerable: true,
                get: () => this._visibleRowIndices.slice()
            });

            if (this._allRows.length) {
                this.renderRows();
            }
        }

        getRowKey(row, index) {
            return this.getRowKeyFn(row, index);
        }

        getParentKey(row, index) {
            return this.getParentKeyFn(row, index);
        }

        getRowLevel(row, index) {
            if (typeof this.getRowLevelFn !== "function") {
                throw new Error("DinextAgGrid.TreeReport: options.getRowLevel is required for getRowLevel()");
            }
            const resolvedIndex = typeof index === "number" ? index : this._allRows.indexOf(row);
            return this.getRowLevelFn(row, resolvedIndex);
        }

        isRowExpandable(row, index) {
            const resolvedIndex = typeof index === "number" ? index : this._allRows.indexOf(row);
            return this.isRowExpandableFn(row, resolvedIndex);
        }

        getRowAt(index) {
            return this._allRows[index];
        }

        getCheckedRowIndices() {
            if (!this.api || typeof this.api.getSelectedRows !== "function") {
                return [];
            }

            return (this.api.getSelectedRows() || [])
                .map(row => this._allRows.indexOf(row))
                .filter(rowIndex => rowIndex >= 0);
        }

        setRows(rows) {
            this._allRows = Array.isArray(rows) ? rows.slice() : [];
            this.renderRows();
            return this;
        }

        getRows() {
            return this._allRows.slice();
        }

        toVisibleRowsByParent() {
            const visible = [];
            const visibleIndices = [];
            const visibleByKey = new Map();

            this._allRows.forEach((row, index) => {
                const parentKey = this.getParentKey(row, index);
                const parentVisible = !parentKey || visibleByKey.get(parentKey) === true;
                const rowVisible = parentVisible && (!parentKey || this.expandedRows.has(parentKey));
                const rootVisible = !parentKey;
                const shouldShow = rootVisible || rowVisible;
                const key = this.getRowKey(row, index);

                if (shouldShow) {
                    visible.push(row);
                    visibleIndices.push(index);
                }

                visibleByKey.set(key, shouldShow);
            });

            this._visibleRows = visible;
            this._visibleRowIndices = visibleIndices;
            return visible;
        }

        toVisibleRowsByLevel() {
            const expandedByLevel = [];
            const visible = [];

            this._allRows.forEach((row, index) => {
                if (!row) return;

                const level = this.getRowLevel(row, index);
                const parentVisible = level <= 0 || expandedByLevel[level - 1] !== false;
                const rowVisible = level <= 0 || parentVisible;

                if (rowVisible) {
                    visible.push(row);
                }

                const expandable = this.isRowExpandable(row, index);
                const rowKey = this.getRowKey(row, index);
                expandedByLevel[level] = rowVisible && (!expandable || this.expandedRows.has(rowKey));
                expandedByLevel.length = level + 1;
            });

            this._visibleRows = visible;
            this._visibleRowIndices = [];
            return visible;
        }

        toVisibleRows() {
            if (this.visibilityMode === "level") {
                return this.toVisibleRowsByLevel();
            }
            return this.toVisibleRowsByParent();
        }

        renderRows() {
            const visibleRows = this.toVisibleRows();
            this.setGridOption("rowData", visibleRows);
            return visibleRows;
        }

        /** @param {string} rowKey */
        toggleRow(rowKey) {
            if (this.expandedRows.has(rowKey)) {
                this.expandedRows.delete(rowKey);
            } else {
                this.expandedRows.add(rowKey);
            }
            this.renderRows();
            return this.expandedRows.has(rowKey);
        }

        expandRow(rowKey) {
            this.expandedRows.add(rowKey);
            this.renderRows();
            return this;
        }

        collapseAll() {
            this.expandedRows.clear();
            this.renderRows();
            return this;
        }

        setTreeDepth(depth) {
            if (this.visibilityMode !== "parent") {
                throw new Error("DinextAgGrid.TreeReport: setTreeDepth() is only supported when visibilityMode is \"parent\"");
            }
            if (typeof this.getRowLevelFn !== "function") {
                throw new Error("DinextAgGrid.TreeReport: options.getRowLevel is required for setTreeDepth()");
            }

            this.expandedRows.clear();
            this._allRows.forEach((row, index) => {
                if (this.isRowExpandable(row, index) && this.getRowLevel(row, index) < depth) {
                    this.expandedRows.add(this.getRowKey(row, index));
                }
            });
            this.renderRows();
            return this;
        }

        openRow(rowIndex) {
            const row = this._allRows[rowIndex];
            if (!row) return this;

            this.expandedRows.add(this.getRowKey(row, rowIndex));
            this.renderRows();
            return this;
        }

        showRows(rowIndices) {
            const rowsByKey = new Map();
            this._allRows.forEach((row, index) => {
                rowsByKey.set(this.getRowKey(row, index), row);
            });

            (rowIndices || []).forEach(rowIndex => {
                const row = this._allRows[rowIndex];
                if (!row) return;

                let parentKey = this.getParentKey(row, rowIndex);
                while (parentKey != null && parentKey !== "") {
                    const parent = rowsByKey.get(parentKey);
                    if (!parent) break;

                    if (this.isRowExpandable(parent, this._allRows.indexOf(parent))) {
                        this.expandedRows.add(parentKey);
                    }

                    const parentIndex = this._allRows.indexOf(parent);
                    parentKey = this.getParentKey(parent, parentIndex >= 0 ? parentIndex : undefined);
                }
            });

            this.renderRows();
            return this;
        }

        refresh(rows, columns) {
            if (columns) {
                this.columns = columns;
                super.refresh(undefined, columns);
            }
            if (rows) {
                this.setRows(rows);
                return;
            }
            if (columns) {
                this.renderRows();
            }
        }
    }

    window.DinextAgGrid = window.DinextAgGrid || {};
    window.DinextAgGrid.TreeReport = DinextAgGridTreeReport;
    window.DinextAgGrid.adapters = window.DinextAgGrid.adapters || {};
    window.DinextAgGrid.adapters.TreeReport = DinextAgGridTreeReport;
})();
