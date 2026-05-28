// Project Work Efforts — DinextAgGrid.presets.workEfforts (budgetTree + selection / height / total).
(function() {
    let ensurePromise = null;
    let WorkEffortsAgGridTable = null;

    function prepareWorkEffortsRows(rows) {
        return (rows || []).map((row, index) => {
            row._weSourceIndex = index;
            row._weRowId = row.value || `row-${index}`;
            return row;
        });
    }

    function getSelectionColumnDef(stickyColumnsCount) {
        const pinned = stickyColumnsCount > 0 ? "left" : undefined;
        return {
            colId: "_we_checkbox",
            width: 46,
            minWidth: 46,
            maxWidth: 46,
            pinned,
            lockPinned: stickyColumnsCount > 0,
            suppressSizeToFit: true,
            sortable: false,
            resizable: false,
            cellClass: params => params.data && params.data._weIsTotalRow ? "work-efforts-ag-grid-total-cell" : ""
        };
    }

    function getBudgetTreeTableClass() {
        const preset = window.DinextAgGrid && window.DinextAgGrid.presets && window.DinextAgGrid.presets.budgetTree;
        if (!preset || !preset.Table) {
            throw new Error("presets/budget-tree.js must load before presets/projects-work-efforts-table.js");
        }
        return preset.Table;
    }

    function createWorkEffortsAgGridTableClass() {
        const BudgetTreeTable = getBudgetTreeTableClass();

        return class WorkEffortsAgGridTable extends BudgetTreeTable {
            constructor(container, options) {
                const adapterRef = { inst: null };
                const tableOptions = options || {};
                const columnDefs = tableOptions.columnDefs || [];
                const preparedRows = prepareWorkEffortsRows(tableOptions.rows || []);
                const showTotalRow = !!tableOptions.showTotalRow;
                const stickyColumnsCount = tableOptions.stickyColumnsCount || 0;
                const forecastDom = tableOptions.forecastDom;

                super(container, {
                    feature: "work-efforts",
                    getRowKey: row => row.value || row._weRowId,
                    getParentKey: row => row.parent_task || "",
                    getRowLevel: row => Number(row.indent) || 0,
                    isRowExpandable: row => adapterRef.inst && adapterRef.inst.hasChildren(row),
                    rows: preparedRows,
                    columnDefs,
                    treeToggleSelector: ".work-efforts-ag-grid-toggle",
                    showTotalRow,
                    totalRow: showTotalRow
                        ? Object.assign(
                            {
                                enabled: true,
                                mode: "pinned-rows",
                                getPinnedRows() {
                                    return adapterRef.inst ? adapterRef.inst.getPinnedBottomRows() : [];
                                }
                            },
                            typeof tableOptions.totalRow === "object" && tableOptions.totalRow
                                ? tableOptions.totalRow
                                : {}
                        )
                        : (typeof tableOptions.totalRow === "object" ? tableOptions.totalRow : null),
                    containerClass: "work-efforts-ag-grid",
                    fullscreen: true,
                    toolbarTarget: tableOptions.toolbarTarget,
                    freezeMessage: tableOptions.freezeMessage,
                    forecastDom: forecastDom === false
                        ? false
                        : (typeof forecastDom === "object" && forecastDom ? forecastDom : null),
                    navigateSkipsNonEditable: true,
                    isRowNavigable: ({ data }) => !(data && data._weIsTotalRow),
                    components: tableOptions.components,
                    defaultColDef: Object.assign({
                        sortable: false,
                        resizable: true,
                        suppressMovable: true,
                        editable: false,
                        autoHeight: true,
                        wrapText: false
                    }, tableOptions.defaultColDef),
                    gridOptions: Object.assign({
                        theme: "legacy",
                        rowSelection: {
                            mode: "multiRow",
                            checkboxes: params => !(params.data && params.data._weIsTotalRow),
                            headerCheckbox: true,
                            enableClickSelection: false,
                            hideDisabledCheckboxes: false,
                            isRowSelectable: node => !(node.data && node.data._weIsTotalRow)
                        },
                        selectionColumnDef: getSelectionColumnDef(stickyColumnsCount),
                        animateRows: false,
                        headerHeight: 56,
                        getRowHeight: params => adapterRef.inst && adapterRef.inst.getRowHeight(params.data),
                        onGridReady: () => {
                            if (!adapterRef.inst) return;
                            adapterRef.inst.syncSelectionColumn();
                            adapterRef.inst.restoreSelection();
                        },
                        onSelectionChanged: () => adapterRef.inst && adapterRef.inst.captureSelection(),
                        getRowClass: params => [
                            "dt-row",
                            params.data && params.data._weIsTotalRow ? "dt-row-total work-efforts-ag-grid-total-row" : ""
                        ].filter(Boolean)
                    }, tableOptions.gridOptions)
                });

                adapterRef.inst = this;
                this.options = tableOptions;
                this.stickyColumnsCount = stickyColumnsCount;
                this.selectedRowKeys = new Set();
                this.suppressSelectionCapture = false;
                this.rowsById = new Map();
                this.childrenByParent = new Map();
                this._totalRowData = null;
                this.rebuildTreeIndex();
                this.renderRows();
            }

            rebuildTreeIndex() {
                this.rowsById = new Map();
                this.childrenByParent = new Map();
                this.rows.forEach(row => {
                    if (!row) return;
                    this.rowsById.set(row.value, row);
                    const parent = row.parent_task || "";
                    if (!this.childrenByParent.has(parent)) {
                        this.childrenByParent.set(parent, []);
                    }
                    this.childrenByParent.get(parent).push(row);
                });
            }

            hasChildren(row) {
                return !!(row && this.childrenByParent.get(row.value)?.length);
            }

            syncSelectionColumn() {
                if (!this.api || typeof this.api.setGridOption !== "function") return;
                this.api.setGridOption("selectionColumnDef", getSelectionColumnDef(this.stickyColumnsCount));
            }

            renderRows() {
                super.renderRows();
                this.syncSelectionColumn();
            }

            getPinnedBottomRows() {
                return this.options.showTotalRow ? [this.getTotalRow()] : [];
            }

            getRowHeight(row) {
                if (row && row._weIsTotalRow) return 32;
                if (typeof this.options.getDynamicRowHeight === "function") {
                    return this.options.getDynamicRowHeight(this, row?._weSourceIndex || 0);
                }
                return undefined;
            }

            getRowAt(index) {
                return this.rows[index] || this._visibleRows[index];
            }

            getCheckedRowIndices() {
                if (!this.api || typeof this.api.getSelectedNodes !== "function") return [];
                this.captureSelection();
                return Array.from(this.selectedRowKeys)
                    .map(rowKey => this.rows.find(row => row && row._weRowId === rowKey)?._weSourceIndex)
                    .filter(index => index !== undefined);
            }

            captureSelection() {
                if (this.suppressSelectionCapture || !this.api || typeof this.api.getSelectedNodes !== "function") {
                    return;
                }
                const visibleKeys = new Set();
                if (typeof this.api.forEachNode === "function") {
                    this.api.forEachNode(node => {
                        if (node.data && !node.data._weIsTotalRow) {
                            visibleKeys.add(node.data._weRowId);
                        }
                    });
                }
                const selectedVisibleKeys = new Set(this.api.getSelectedNodes()
                    .filter(node => node.data && !node.data._weIsTotalRow)
                    .map(node => node.data?._weSourceIndex)
                    .filter(index => index !== undefined)
                    .map(index => this.rows[index]?._weRowId)
                    .filter(Boolean));
                const nextSelectedKeys = new Set(
                    Array.from(this.selectedRowKeys).filter(rowKey => !visibleKeys.has(rowKey))
                );
                selectedVisibleKeys.forEach(rowKey => nextSelectedKeys.add(rowKey));
                this.selectedRowKeys = nextSelectedKeys;
            }

            restoreSelection() {
                if (!this.api || typeof this.api.forEachNode !== "function") return;
                this.suppressSelectionCapture = true;
                try {
                    this.api.forEachNode(node => {
                        if (node.data && !node.data._weIsTotalRow) {
                            node.setSelected(this.selectedRowKeys.has(node.data._weRowId));
                        }
                    });
                } finally {
                    this.suppressSelectionCapture = false;
                }
            }

            showRows(rowIndices) {
                if (Array.isArray(rowIndices)) {
                    rowIndices.forEach(index => this.expandParentsFor(this.rows[index]));
                }
                this.refresh();
            }

            expandParentsFor(row) {
                let current = row;
                while (current && current.parent_task) {
                    this.expandedRows.add(current.parent_task);
                    current = this.rowsById.get(current.parent_task);
                }
            }

            setStickyColumnsCount(count) {
                this.stickyColumnsCount = count || 0;
                this.syncSelectionColumn();
            }

            refresh(rows, columnDefs) {
                this.captureSelection();
                if (columnDefs) {
                    this.options.columnDefs = columnDefs;
                    super.refresh(undefined, columnDefs);
                }
                if (rows) {
                    this.setRows(prepareWorkEffortsRows(rows));
                    this.rebuildTreeIndex();
                } else if (columnDefs) {
                    this.renderRows();
                }
                this.syncSelectionColumn();
                setTimeout(() => this.restoreSelection(), 0);
            }

            getTotalRow() {
                if (!this._totalRowData) {
                    this._totalRowData = {
                        _weIsTotalRow: true,
                        _weSourceIndex: -1,
                        _weRowId: "__work_efforts_total__"
                    };
                }
                return this._totalRowData;
            }
        };
    }

    function ensureWorkEffortsAgGridTable() {
        if (WorkEffortsAgGridTable) {
            return Promise.resolve(WorkEffortsAgGridTable);
        }

        if (!window.DinextAgGridCoreBootstrap || typeof window.DinextAgGridCoreBootstrap.ensureTreeDom !== "function") {
            return Promise.reject(new Error("DinextAgGridCoreBootstrap.ensureTreeDom required for work-efforts preset"));
        }

        if (!ensurePromise) {
            ensurePromise = window.DinextAgGridCoreBootstrap.ensureTreeDom().then(() => {
                WorkEffortsAgGridTable = createWorkEffortsAgGridTableClass();
                return WorkEffortsAgGridTable;
            });
        }

        return ensurePromise;
    }

    if (window.DinextAgGrid) {
        window.DinextAgGrid.presets = window.DinextAgGrid.presets || {};
        window.DinextAgGrid.presets.workEfforts = {
            ensureReady: ensureWorkEffortsAgGridTable,
            get Table() {
                return WorkEffortsAgGridTable;
            }
        };
    }
})();

