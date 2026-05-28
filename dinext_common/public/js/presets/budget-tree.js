// DinextAgGrid.presets.budgetTree — TreeReport + ForecastDom + budget tree/total row mechanics.
// Requires ag-grid/tree-report.js, forecast-dom.js, presets/budget-tree bootstrap.
(function() {
    const TreeReport = window.DinextAgGrid && window.DinextAgGrid.TreeReport;
    if (!TreeReport) {
        throw new Error(
            "DinextAgGrid.TreeReport must be loaded before presets/budget-tree.js"
        );
    }

    const DEFAULT_TREE_TOGGLE_SELECTORS = [".budget-tree-toggle", ".project-pl-tree-toggle"];
    const DEFAULT_TOTAL_ROW_SELECTOR = [
        ".project-pl-total-row",
        ".budget-total-row",
        ".work-efforts-ag-grid-total-row",
        ".dt-row-total"
    ].join(", ");
    const DEFAULT_PAST_GROUP_SELECTOR = ".budget-group, .we-columns-container";

    function translate(text) {
        return typeof window.__ === "function" ? window.__(text) : text;
    }

    function mergeCallbacks(first, second) {
        if (typeof first !== "function") return second;
        if (typeof second !== "function") return first;
        return function() {
            const result = first.apply(this, arguments);
            const secondResult = second.apply(this, arguments);
            return secondResult !== undefined ? secondResult : result;
        };
    }

    function normalizeTreeToggleSelectors(options) {
        if (!options || options.treeToggleSelector == null) {
            return DEFAULT_TREE_TOGGLE_SELECTORS.slice();
        }
        const value = options.treeToggleSelector;
        return Array.isArray(value) ? value.slice() : [value];
    }

    function matchesSelector(target, selectors) {
        if (!target || !selectors || !selectors.length) return null;
        for (let i = 0; i < selectors.length; i += 1) {
            const toggle = target.closest(selectors[i]);
            if (toggle) return toggle;
        }
        return null;
    }

    function isTotalRowTarget(target, options) {
        if (!target) return false;
        if (typeof options.isTotalRowTarget === "function") {
            return !!options.isTotalRowTarget(target);
        }
        const selector = options.totalRowSelector || DEFAULT_TOTAL_ROW_SELECTOR;
        return !!target.closest(selector);
    }

    function defaultForecastIsEditable(target, options) {
        if (!target) return false;
        if (target.classList.contains("readonly-fact")) return false;

        const group = target.closest(
            options.pastGroupSelector || DEFAULT_PAST_GROUP_SELECTOR
        );
        if (group) {
            const isPast = group.getAttribute("data-is-past");
            if (isPast === "true" || isPast === true) return false;
        }

        return !isTotalRowTarget(target, options);
    }

    function defaultForecastOnActivate(target, params, input) {
        if (typeof window.$ !== "function") return;
        window.$(input).data(
            "original-value",
            String(target.textContent || "").replace(/\s+/g, "")
        );
    }

    function buildForecastDomOptions(options) {
        const userCfg = options.forecastDom;
        if (userCfg === false) return false;

        const userObj = typeof userCfg === "object" && userCfg ? userCfg : {};
        const defaultIsEditable = (target, params) => defaultForecastIsEditable(target, options);

        return {
            selector: userObj.selector || ".editable-forecast",
            getNavKey: userObj.getNavKey,
            isEditable: typeof userObj.isEditable === "function"
                ? (target, params) => userObj.isEditable(target, params)
                    && defaultForecastIsEditable(target, options)
                : defaultIsEditable,
            onActivate: typeof userObj.onActivate === "function"
                ? mergeCallbacks(defaultForecastOnActivate, userObj.onActivate)
                : defaultForecastOnActivate,
            onSave: userObj.onSave
        };
    }

    function resolveTotalRowConfig(options) {
        let totalRow = null;
        if (options.totalRow && typeof options.totalRow === "object") {
            totalRow = Object.assign({ enabled: true, mode: "pinned-empty" }, options.totalRow);
        } else if (options.showTotalRow) {
            totalRow = { enabled: true, mode: "pinned-empty" };
        }

        return totalRow;
    }

    function buildBudgetTreeGridOptions(options, tableRef) {
        const userGridOptions = options.gridOptions || {};

        return Object.assign({}, userGridOptions, {
            onGridReady: mergeCallbacks(userGridOptions.onGridReady, params => {
                const table = tableRef.inst;
                if (!table) return;
                table.api = params.api;
                table.renderRows();
                table.updateBodyScrollable();
            }),
            onCellClicked: mergeCallbacks(userGridOptions.onCellClicked, params => {
                const table = tableRef.inst;
                if (table && typeof table.handleCellClick === "function") {
                    table.handleCellClick(params);
                }
            }),
            onCellDoubleClicked: mergeCallbacks(userGridOptions.onCellDoubleClicked, params => {
                const table = tableRef.inst;
                if (table && typeof table.handleCellDoubleClick === "function") {
                    table.handleCellDoubleClick(params);
                }
            })
        });
    }

    let BudgetTreeTableClass = null;

    function getBudgetTreeTableClass() {
        if (BudgetTreeTableClass) {
            return BudgetTreeTableClass;
        }

        BudgetTreeTableClass = class DinextAgGridBudgetTreeTable extends TreeReport {
            constructor(container, options = {}) {
                if (typeof options.getRowKey !== "function") {
                    throw new Error("DinextAgGrid.BudgetTreeTable: options.getRowKey is required");
                }

                if (options.columns !== undefined) {
                    throw new Error("DinextAgGrid.BudgetTreeTable: options.columns removed; use columnDefs.");
                }
                const columnDefs = options.columnDefs || [];
                if (!Array.isArray(columnDefs)) {
                    throw new Error("DinextAgGrid.BudgetTreeTable: columnDefs must be an array.");
                }
                const fullscreenShell = options.fullscreenShell || container.parentElement;
                const freezeMessage = options.freezeMessage || translate("Идет загрузка данных..");
                const initialRows = options.rows ?? [];
                const tableRef = { inst: null };

                const superOptions = {
                    rows: initialRows,
                    columnDefs,
                    getRowKey: options.getRowKey,
                    getParentKey: options.getParentKey,
                    getRowLevel: options.getRowLevel,
                    isRowExpandable: options.isRowExpandable,
                    expandedRows: options.expandedRows,
                    visibilityMode: options.visibilityMode || "parent",
                    keyboardEditMode: options.keyboardEditMode || "dom",
                    forecastDom: buildForecastDomOptions(options),
                    feature: options.feature,
                    fullscreen: options.fullscreen !== undefined ? options.fullscreen : "prepend",
                    fullscreenTarget: options.fullscreenTarget || "shell",
                    fullscreenShell,
                    toolbarTarget: options.toolbarTarget,
                    classNames: options.classNames,
                    components: options.components,
                    editable: options.editable,
                    readonly: options.readonly,
                    excelNavigation: options.excelNavigation,
                    navigateSkipsNonEditable: options.navigateSkipsNonEditable,
                    isRowNavigable: options.isRowNavigable,
                    defaultColDef: options.defaultColDef,
                    getRowClass: options.getRowClass,
                    getCellStyle: options.getCellStyle,
                    getHeaderClass: options.getHeaderClass,
                    themeClasses: options.themeClasses,
                    gridOptions: buildBudgetTreeGridOptions(options, tableRef)
                };

                super(container, superOptions);
                tableRef.inst = this;

                this.options = Object.assign({}, options, {
                    totalRow: resolveTotalRowConfig(options)
                });
                this.hooksContext = {};
                this.fullscreenShell = fullscreenShell;
                this.freezeMessage = freezeMessage;
                this._treeToggleSelectors = normalizeTreeToggleSelectors(options);

                if (options.feature && window.DinextAgGrid && typeof window.DinextAgGrid.ensureFeatureStyles === "function") {
                    window.DinextAgGrid.ensureFeatureStyles(options.feature);
                }

                if (options.containerClass) {
                    container.classList.add(options.containerClass);
                } else if (options.classNames && typeof options.classNames.root === "string") {
                    container.classList.add(options.classNames.root);
                }
            }

            resetHooksContext() {
                this.hooksContext = {};
            }

            refresh(rows, columnDefs) {
                this.resetHooksContext();
                if (columnDefs) {
                    this.columns = columnDefs;
                    super.refresh(undefined, columnDefs);
                }
                if (rows) {
                    this.setRows(rows);
                    return this;
                }
                if (columnDefs) {
                    this.renderRows();
                }
                return this;
            }

            destroy() {
                super.destroy();
                this.hooksContext = {};
                this.api = null;
            }

            renderRows() {
                const visibleRows = super.renderRows();
                this.applyTotalRow();
                this.updateBodyScrollable();
                return visibleRows;
            }

            applyTotalRow() {
                const totalRow = this.options.totalRow;
                if (!totalRow || totalRow.enabled === false) {
                    return;
                }

                if (totalRow.mode === "pinned-rows") {
                    const pinnedRows = typeof totalRow.getPinnedRows === "function"
                        ? totalRow.getPinnedRows.call(this)
                        : [];
                    this.setGridOption(
                        "pinnedBottomRowData",
                        this.rows.length ? pinnedRows : []
                    );
                    return;
                }

                this.setGridOption(
                    "pinnedBottomRowData",
                    this.rows.length ? (totalRow.pinnedData || [{}]) : []
                );
            }

            updateBodyScrollable() {
                this.bodyScrollable = this.container.querySelector(".ag-body-viewport") || this.container;
            }

            freeze(message) {
                super.freeze(message || this.freezeMessage);
            }

            handleCellClick(params) {
                const target = params.event && params.event.target;
                const toggle = matchesSelector(target, this._treeToggleSelectors);
                if (toggle) {
                    const row = params.data;
                    const rowIndex = typeof params.rowIndex === "number" ? params.rowIndex : undefined;
                    const rowKey = row && this.getRowKey(row, rowIndex);
                    if (rowKey && this.isRowExpandable(row, rowIndex)) {
                        this.toggleRow(rowKey);
                        if (typeof this.options.onTreeToggle === "function") {
                            this.options.onTreeToggle({ row, rowKey, params, toggle }, this);
                        }
                    }
                    return;
                }

                const editable = target && target.closest(".editable-forecast");
                if (editable && this.forecastDom && typeof this.forecastDom.startEdit === "function") {
                    this.forecastDom.startEdit(editable, params);
                }
            }

            handleCellDoubleClick(params) {
                if (typeof this.options.onCellDoubleClicked === "function") {
                    this.options.onCellDoubleClicked(params, this);
                }
            }
        };

        return BudgetTreeTableClass;
    }

    function registerBudgetTreePreset() {
        window.DinextAgGrid = window.DinextAgGrid || {};
        window.DinextAgGrid.presets = window.DinextAgGrid.presets || {};
        if (window.DinextAgGrid.presets.budgetTree) {
            return true;
        }

        window.DinextAgGrid.presets.budgetTree = {
            getTableClass: getBudgetTreeTableClass,
            get Table() {
                return getBudgetTreeTableClass();
            }
        };

        return true;
    }

    registerBudgetTreePreset();
})();
