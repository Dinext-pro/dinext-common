// DinextAgGrid.Table — requires loader, utils, editors, navigation, fullscreen (bootstrap order).
(function() {
    const loader = window.DinextAgGridLoader;
    const I = window.DinextAgGridInternals;

    if (!loader) {
        throw new Error("DinextAgGridLoader must be loaded before ag-grid/table.js");
    }
    if (!I || typeof I.normalizeColumn !== "function") {
        throw new Error("DinextAgGridInternals (utils) must load before ag-grid/table.js");
    }

    const {
        isFrappeDarkTheme,
        translate,
        toClassList,
        mergeCallbacks,
        getRowKey,
        rollbackCellValue,
        normalizeColumn,
        syncFullscreenBodyClass,
        fullscreenTables,
        isEditableCell,
        isPinnedRowAtIndex,
        buildCellCheckParams,
        isRowNavigableForTable,
        getNextEditableCell,
        DinextAgGridTextEditor,
        DinextAgGridNumericEditor
    } = I;

    /**
     * Table options (excerpt):
     * - keyboardEditMode: "grid" | "dom" | "auto" (default "auto")
     * - forecastDom: true | { isEditable, onActivate, onSave }
     * - onReady, onCellFocused, onEditStart, onBeforeSave, validateCellValue, onSaveCell, onCellDoubleClicked
     */
    class DinextAgGridTable {
        constructor(container, options = {}) {
            if (!container) {
                throw new Error("DinextAgGrid.Table: container is required");
            }

            this.container = container;
            this.wrapper = container;
            this.options = options;
            if (options.columns !== undefined) {
                throw new Error("DinextAgGrid.Table: options.columns removed; use columnDefs.");
            }
            this.columns = options.columnDefs
                || (options.gridOptions && options.gridOptions.columnDefs)
                || [];
            if (!Array.isArray(this.columns)) {
                throw new Error("DinextAgGrid.Table: columnDefs must be an array.");
            }
            this.rows = options.rows ?? [];
            this.fullscreenTarget = options.fullscreenTarget === "shell" ? "shell" : "container";
            this.fullscreenShell = options.fullscreenShell || null;
            this.fullscreenActive = false;
            this.lastEditKey = null;
            this.lastEditDirection = 1;
            this.handleFullscreenKeydown = event => {
                if (event.key === "Escape" && this.fullscreenActive) {
                    event.preventDefault();
                    this.toggleFullscreen(false);
                }
            };

            this.applyContainerClasses();
            this.applyTheme();
            this.themeObserver = new MutationObserver(() => this.applyTheme());
            this.themeObserver.observe(document.documentElement, {
                attributes: true,
                attributeFilter: ["data-theme", "data-theme-mode"]
            });

            this.toolbar = this.createToolbar();
            this.gridOptions = this.buildGridOptions();
            this.api = window.agGrid.createGrid(this.container, this.gridOptions);
            this.bindForecastDomIfNeeded();
        }

        bindForecastDomIfNeeded() {
            const cfg = this.options.forecastDom;
            if (!cfg || cfg === true) return;
            if (typeof cfg !== "object") return;

            const ForecastDomCell = window.DinextAgGrid && window.DinextAgGrid.ForecastDomCell;
            if (!ForecastDomCell) {
                console.warn("DinextAgGrid: forecastDom options require ForecastDomCell module");
                return;
            }

            this.forecastDom = new ForecastDomCell();
            this.forecastDom.bindTable(this, {
                isEditable: cfg.isEditable,
                onActivate: cfg.onActivate,
                onSave: cfg.onSave
            });
        }

        applyContainerClasses() {
            this.container.classList.add("dinext-ag-grid-table");
            if (typeof this.options.classNames === "string" || Array.isArray(this.options.classNames)) {
                toClassList(this.options.classNames, { table: this }).forEach(className => this.container.classList.add(className));
            }
            toClassList(this.options.classNames && this.options.classNames.root, { table: this }).forEach(className => this.container.classList.add(className));
        }

        applyTheme() {
            const isDark = isFrappeDarkTheme();
            const themeClasses = this.options.themeClasses || {};

            this.container.classList.toggle(themeClasses.light || "ag-theme-quartz", !isDark);
            this.container.classList.toggle(themeClasses.dark || "ag-theme-quartz-dark", isDark);
            this.container.classList.toggle("dinext-ag-grid-table-dark", isDark);

            if (themeClasses.darkExtra) {
                this.container.classList.toggle(themeClasses.darkExtra, isDark);
            }
        }

        createToolbar() {
            const fullscreen = this.options.fullscreen;
            if (!fullscreen) return null;

            const toolbarTarget = this.options.toolbarTarget || this.container.parentElement;
            if (!toolbarTarget) return null;

            const toolbar = document.createElement("div");
            toolbar.className = "dinext-ag-grid-table-toolbar";
            toClassList(this.options.classNames && this.options.classNames.toolbar, { table: this }).forEach(className => toolbar.classList.add(className));

            const button = document.createElement("button");
            button.type = "button";
            button.className = "dinext-ag-grid-table-fullscreen-button";
            button.title = translate("Полноэкранный режим");
            button.textContent = "◱";
            button.addEventListener("click", () => this.toggleFullscreen());
            toolbar.appendChild(button);

            if (fullscreen === "prepend") {
                toolbarTarget.insertBefore(toolbar, toolbarTarget.firstChild);
            } else {
                toolbarTarget.appendChild(toolbar);
            }

            this.fullscreenButton = button;
            return toolbar;
        }

        buildGridOptions() {
            const HtmlHeader = I.DinextAgGridHtmlHeader;
            const components = Object.assign({
                dinextTextEditor: DinextAgGridTextEditor,
                dinextNumericEditor: DinextAgGridNumericEditor,
                dinextHtmlHeader: HtmlHeader
            }, this.options.components || {});
            const userGridOptions = this.options.gridOptions || {};
            const userDefaultColDef = this.options.defaultColDef || {};

            const gridOptions = Object.assign({}, userGridOptions, {
                theme: userGridOptions.theme || "legacy",
                context: Object.assign({}, userGridOptions.context || {}, { dinextTable: this }),
                rowData: this.rows,
                columnDefs: this.columns.map((column, index) => normalizeColumn(column, index, this)),
                components,
                defaultColDef: Object.assign({
                    resizable: true,
                    sortable: false,
                    editable: !!this.options.editable && !this.options.readonly,
                    singleClickEdit: false,
                    cellEditor: "dinextTextEditor"
                }, userGridOptions.defaultColDef || {}, userDefaultColDef)
            });

            gridOptions.getRowId = userGridOptions.getRowId || (params => {
                return String(getRowKey(params.data, params.rowIndex, this.options.rowKey));
            });
            gridOptions.getRowClass = params => [
                ...toClassList(this.options.getRowClass, params),
                ...toClassList(userGridOptions.getRowClass, params)
            ];
            gridOptions.getRowStyle = this.options.getRowStyle || userGridOptions.getRowStyle;

            gridOptions.onGridReady = mergeCallbacks(userGridOptions.onGridReady, params => {
                this.api = params.api;
                if (typeof this.options.onReady === "function") this.options.onReady(params, this);
            });
            gridOptions.onCellFocused = mergeCallbacks(userGridOptions.onCellFocused, params => {
                if (typeof this.options.onCellFocused === "function") this.options.onCellFocused(params, this);
            });
            gridOptions.onCellEditingStarted = mergeCallbacks(userGridOptions.onCellEditingStarted, params => {
                if (typeof this.options.onEditStart === "function") this.options.onEditStart(params, this);
            });
            gridOptions.onCellValueChanged = mergeCallbacks(userGridOptions.onCellValueChanged, params => this.handleCellValueChanged(params));
            gridOptions.onCellDoubleClicked = mergeCallbacks(userGridOptions.onCellDoubleClicked, params => {
                if (typeof this.options.onCellDoubleClicked === "function") this.options.onCellDoubleClicked(params, this);
            });
            gridOptions.onCellKeyDown = mergeCallbacks(userGridOptions.onCellKeyDown, params => this.handleCellKeyDown(params));
            gridOptions.onCellEditingStopped = mergeCallbacks(userGridOptions.onCellEditingStopped, params => this.handleCellEditingStopped(params));

            return gridOptions;
        }

        isExcelNavigationEnabled() {
            if (this.options.readonly) return false;
            if (this.options.excelNavigation === false) return false;
            if (this.options.excelNavigation === true) return true;
            return !!this.options.editable;
        }

        getKeyboardEditMode() {
            const configured = this.options.keyboardEditMode;
            if (configured === "grid" || configured === "dom") {
                return configured;
            }

            if (this.options.editable) {
                return "grid";
            }

            if (this.options.forecastDom) {
                return "dom";
            }

            return "dom";
        }

        moveToNextEditableColumn(direction) {
            if (!this.api || !this.isExcelNavigationEnabled()) return;

            const focusedCell = this.api.getFocusedCell ? this.api.getFocusedCell() : null;
            const nextDirection = typeof direction === "number" ? direction : this.lastEditDirection || 1;
            const nextCell = getNextEditableCell(this.api, focusedCell, nextDirection, this);

            if (nextCell) {
                this.api.setFocusedCell(nextCell.rowIndex, nextCell.column);
            }
        }

        moveToNextEditableRow() {
            if (!this.api || !this.isExcelNavigationEnabled()) return;

            const focusedCell = this.api.getFocusedCell ? this.api.getFocusedCell() : null;
            if (!focusedCell) return;

            const rowCount = this.api.getDisplayedRowCount ? this.api.getDisplayedRowCount() : 0;
            const column = focusedCell.column;
            let rowIndex = focusedCell.rowIndex + 1;

            while (rowIndex < rowCount) {
                if (this.options.navigateSkipsPinnedRows !== false && isPinnedRowAtIndex(this.api, rowIndex)) {
                    rowIndex += 1;
                    continue;
                }

                if (!isRowNavigableForTable(this, this.api, rowIndex, column)) {
                    rowIndex += 1;
                    continue;
                }

                if (this.options.navigateSkipsNonEditable !== false) {
                    if (!isEditableCell(buildCellCheckParams(this.api, rowIndex, column))) {
                        rowIndex += 1;
                        continue;
                    }
                }

                this.api.setFocusedCell(rowIndex, column);
                return;
            }
        }

        handleCellEditingStopped(params) {
            if (!this.isExcelNavigationEnabled()) return;

            const lastEditKey = this.lastEditKey;
            this.lastEditKey = null;
            this.lastEditDirection = 1;

            if (!lastEditKey) return;

            if (lastEditKey === "Tab") {
                this.moveToNextEditableColumn();
                return;
            }

            if (lastEditKey === "Enter") {
                this.moveToNextEditableRow();
            }
        }

        handleCellKeyDown(params) {
            const event = params.event;
            if (!event || !this.api || this.options.readonly) return;

            const mode = this.getKeyboardEditMode();
            const isEditing = this.api.getEditingCells && this.api.getEditingCells().length;

            if (mode === "grid" && !isEditing && isEditableCell(params)) {
                const printable = event.key && event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
                if (printable || event.key === "Enter") {
                    return;
                }
            }

            if (event.key === "Tab" && this.api.getFocusedCell) {
                if (isEditing) return;

                if (this.isExcelNavigationEnabled()) {
                    const nextCell = getNextEditableCell(
                        this.api,
                        this.api.getFocusedCell(),
                        event.shiftKey ? -1 : 1,
                        this
                    );
                    if (nextCell) {
                        event.preventDefault();
                        this.api.setFocusedCell(nextCell.rowIndex, nextCell.column);
                    }
                }
            }
        }

        handleCellValueChanged(params) {
            const validate = this.options.validateCellValue;
            const beforeSave = this.options.onBeforeSave;
            const onSaveCell = this.options.onSaveCell;

            if (typeof validate === "function") {
                const validation = validate(params, this);
                if (validation === false) {
                    rollbackCellValue(params);
                    this.refreshCells({ rowNodes: [params.node], columns: [params.column], force: true });
                    return;
                }
            }

            if (typeof beforeSave === "function" && beforeSave(params, this) === false) {
                rollbackCellValue(params);
                this.refreshCells({ rowNodes: [params.node], columns: [params.column], force: true });
                return;
            }

            if (typeof onSaveCell === "function") {
                onSaveCell(params, this);
            }
        }

        refresh(rows, columnDefs) {
            if (columnDefs) {
                this.columns = columnDefs;
                this.setGridOption("columnDefs", this.columns.map((column, index) => normalizeColumn(column, index, this)));
            }

            if (rows) {
                this.rows = rows;
                this.setGridOption("rowData", rows);
            }
        }

        setGridOption(key, value) {
            if (!this.api) return;
            if (typeof this.api.setGridOption === "function") {
                this.api.setGridOption(key, value);
                return;
            }

            if (key === "rowData" && typeof this.api.setRowData === "function") {
                this.api.setRowData(value);
            } else if (key === "columnDefs" && typeof this.api.setColumnDefs === "function") {
                this.api.setColumnDefs(value);
            } else {
                this.gridOptions[key] = value;
            }
        }

        refreshCells(params) {
            if (this.api && typeof this.api.refreshCells === "function") {
                this.api.refreshCells(params);
            }
        }

        freeze(message) {
            if (this.api && typeof this.api.setGridOption === "function") {
                this.api.setGridOption("loading", true);
            }
            if (message) {
                this.container.setAttribute("data-loading-message", message);
            }
        }

        unfreeze() {
            if (this.api && typeof this.api.setGridOption === "function") {
                this.api.setGridOption("loading", false);
            }
            this.container.removeAttribute("data-loading-message");
        }

        getFullscreenElement() {
            if (this.fullscreenTarget === "shell" && this.fullscreenShell) {
                return this.fullscreenShell;
            }
            return this.container;
        }

        toggleFullscreen(force) {
            const nextState = typeof force === "boolean" ? force : !this.fullscreenActive;
            const fullscreenElement = this.getFullscreenElement();
            this.fullscreenActive = nextState;
            fullscreenElement.classList.toggle("dinext-ag-grid-table-fullscreen", nextState);
            if (this.fullscreenTarget === "shell" && this.fullscreenShell && this.container !== this.fullscreenShell) {
                this.container.classList.toggle("dinext-ag-grid-table-fullscreen-host", nextState);
            }
            if (nextState) {
                fullscreenTables.add(this);
                document.addEventListener("keydown", this.handleFullscreenKeydown);
            } else {
                fullscreenTables.delete(this);
                document.removeEventListener("keydown", this.handleFullscreenKeydown);
            }
            syncFullscreenBodyClass();

            if (this.fullscreenButton) {
                this.fullscreenButton.textContent = nextState ? "×" : "◱";
                this.fullscreenButton.title = nextState ? translate("Закрыть полноэкранный режим") : translate("Полноэкранный режим");
                this.fullscreenButton.classList.toggle("dinext-ag-grid-table-fullscreen-button-active", nextState);
            }

            setTimeout(() => {
                if (this.api && typeof this.api.sizeColumnsToFit === "function" && this.options.sizeColumnsOnFullscreen !== false) {
                    this.api.sizeColumnsToFit();
                }
            }, 0);
        }

        destroy() {
            if (this.fullscreenActive) {
                this.toggleFullscreen(false);
            }
            if (this.forecastDom && typeof this.forecastDom.unbindTable === "function") {
                this.forecastDom.unbindTable();
                this.forecastDom = null;
            }
            document.removeEventListener("keydown", this.handleFullscreenKeydown);
            if (this.themeObserver) {
                this.themeObserver.disconnect();
                this.themeObserver = null;
            }
            if (this.toolbar && this.toolbar.parentElement) {
                this.toolbar.parentElement.removeChild(this.toolbar);
            }
            if (this.api && typeof this.api.destroy === "function") {
                this.api.destroy();
            }
            this.container.innerHTML = "";
        }
    }

    I.DinextAgGridTable = DinextAgGridTable;
})();
