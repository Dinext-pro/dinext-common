(function() {
    let ensurePromise = null;
    let ProjectsWorkloadAgGridTable = null;

    function getStableFallbackRowId(row) {
        if (window.DinextAgGrid && typeof window.DinextAgGrid.getStableFallbackRowId === "function") {
            return window.DinextAgGrid.getStableFallbackRowId(row);
        }
        return `row-value:${typeof row}:${String(row)}`;
    }

    function initWorkloadTableClass() {
        if (!ProjectsWorkloadAgGridTable && window.DinextAgGrid && window.DinextAgGrid.TreeReport) {
            ProjectsWorkloadAgGridTable = createProjectsWorkloadAgGridTableClass();
        }
        return ProjectsWorkloadAgGridTable;
    }

    function ensureWorkloadTableReady() {
        const TableClass = initWorkloadTableClass();
        if (TableClass) {
            return Promise.resolve(TableClass);
        }

        if (!window.DinextAgGrid || typeof window.DinextAgGrid.ensureModules !== "function") {
            return Promise.reject(new Error(
                "DinextAgGrid не загружен (ожидается ag-grid/bootstrap.js + facade)"
            ));
        }

        if (!ensurePromise) {
            ensurePromise = window.DinextAgGrid.ensureModules(["tree-report"]).then(initWorkloadTableClass);
        }

        return ensurePromise.then(TableClass => {
            if (!TableClass) {
                throw new Error("DinextAgGrid.presets.workload: TreeReport не загружен");
            }
            return TableClass;
        });
    }

    function getDefaultRowLevel(row) {
        const indent = Number(row && row.indent);
        return Number.isFinite(indent) ? Math.max(0, indent) : 0;
    }

    function getDefaultRowKey(row, index) {
        if (!row) return getStableFallbackRowId(row);
        if (row._agRowKey) return row._agRowKey;

        if (row.level === "user" || row.isUser || row._isUser) {
            return `user:${row.email || row._email || row.participant || getStableFallbackRowId(row)}`;
        }
        if (row.level === "role" || row.isRole) {
            return `role:${row.email || row._email || "user"}:${row.roleName || row.role || row.participant || getStableFallbackRowId(row)}`;
        }
        if (row.level === "task" || row.isTask) {
            return `task:${row.email || row._email || "user"}:${row.roleName || row.role || "role"}:${row.task_id || row.name || row.participant || getStableFallbackRowId(row)}`;
        }
        if (row._isAbsenceRow) {
            return `absence:${row._email || row.email || getStableFallbackRowId(row)}`;
        }
        if (row._isLazyPlaceholder) {
            return `placeholder:${row._email || row.email || getStableFallbackRowId(row)}`;
        }
        if (row._isProject) {
            return `project:${row._email || row.email || "user"}:${row._project || row.project || row.participant || getStableFallbackRowId(row)}`;
        }

        return `row:${row.participant || row.name || getStableFallbackRowId(row)}:${getStableFallbackRowId(row)}`;
    }

    function getRowId(row, index, table) {
        if (!row) return getStableFallbackRowId(row);
        if (row._agRowId) return row._agRowId;

        const key = table ? table.getRowKey(row, index) : getDefaultRowKey(row, index);
        row._agRowId = `${key}:${getStableFallbackRowId(row)}`;
        return row._agRowId;
    }

    function getParticipantIndent(row, table) {
        const indentSize = table && Number.isFinite(Number(table.options.indentSize))
            ? Number(table.options.indentSize)
            : 18;
        return (table ? table.getRowLevel(row) : getDefaultRowLevel(row)) * indentSize;
    }

    function isDefaultExpandableRow(row) {
        if (!row) return false;
        if (row.expandable === true) return true;
        return !!(row._isUser && row._email);
    }

    function getColumnColId(column) {
        return column && (column.colId || column.field);
    }

    function cellRendererResultToHtml(result) {
        if (result == null) return "";
        if (typeof result === "string") return result;
        if (typeof Element !== "undefined" && result instanceof Element) {
            return result.outerHTML;
        }
        return String(result);
    }

    function wrapWorkloadColumnDefs(columnDefs, tableRef) {
        if (!Array.isArray(columnDefs)) return [];
        const defs = columnDefs.map(col => ({ ...col }));
        const idx = defs.findIndex(col => getColumnColId(col) === "participant");
        if (idx < 0) return defs;

        const participantDef = defs[idx];
        const innerRenderer = participantDef.cellRenderer;
        participantDef.cellRenderer = params => {
            const table = tableRef && tableRef.inst;
            if (!table || typeof table.renderParticipantCell !== "function") {
                if (typeof innerRenderer === "function") {
                    return innerRenderer(params);
                }
                return params.value == null ? "" : String(params.value);
            }
            return table.renderParticipantCell(params.data, participantDef, params, innerRenderer);
        };
        defs[idx] = participantDef;
        return defs;
    }

    function createProjectsWorkloadAgGridTableClass() {
        const TreeReport = window.DinextAgGrid && window.DinextAgGrid.TreeReport;
        if (!TreeReport) {
            throw new Error("DinextAgGrid.TreeReport must be loaded (ag-grid/tree-report.js)");
        }

        return class ProjectsWorkloadAgGridTable extends TreeReport {
            constructor(container, options = {}) {
                if (!Array.isArray(options.columnDefs)) {
                    throw new Error("ProjectsWorkloadAgGrid: options.columnDefs is required (array).");
                }

                const tableRef = { inst: null };
                const initialRows = options.rows ?? [];
                const columnDefs = wrapWorkloadColumnDefs(options.columnDefs, tableRef);
                const getRowLevel = typeof options.getRowLevel === "function"
                    ? options.getRowLevel
                    : getDefaultRowLevel;
                const getRowKey = typeof options.getRowKey === "function"
                    ? options.getRowKey
                    : getDefaultRowKey;
                const isRowExpandableFn = typeof options.isRowExpandable === "function"
                    ? options.isRowExpandable
                    : isDefaultExpandableRow;

                super(container, {
                    visibilityMode: "level",
                    getRowKey,
                    getParentKey: () => "",
                    getRowLevel,
                    isRowExpandable: isRowExpandableFn,
                    rows: initialRows,
                    columnDefs,
                    gridOptions: {
                        theme: "legacy",
                        rowData: [],
                        rowHeight: options.rowHeight || 40,
                        headerHeight: options.headerHeight || 70,
                        suppressColumnVirtualisation: false,
                        suppressRowVirtualisation: false,
                        animateRows: false,
                        ensureDomOrder: false,
                        loadingOverlayComponentParams: {
                            loadingMessage: options.freezeMessage || __("Идет загрузка данных...")
                        },
                        getRowId: params => params.data && params.data._agRowId
                            ? params.data._agRowId
                            : getRowId(params.data, params.rowIndex, tableRef.inst),
                        getRowClass: params => params.data && params.data.level ? `level-${params.data.level}` : "",
                        onGridReady: params => {
                            tableRef.inst.api = params.api;
                            tableRef.inst.bodyScrollable = container.querySelector(".ag-body-viewport");
                            tableRef.inst.renderRows();
                        },
                        onCellClicked: params => tableRef.inst && tableRef.inst.handleCellClick(params),
                        onCellDoubleClicked: params => tableRef.inst && tableRef.inst.handleCellDoubleClick(params)
                    },
                    themeClasses: {
                        light: "ag-theme-quartz",
                        dark: "ag-theme-quartz-dark",
                        darkExtra: "projects-workload-ag-grid-dark"
                    },
                    classNames: options.classNames,
                    fullscreen: options.fullscreen || false,
                    toolbarTarget: options.toolbarTarget,
                    components: Object.assign({
                        dinextHtmlHeader: window.DinextAgGridInternals
                            && window.DinextAgGridInternals.DinextAgGridHtmlHeader
                    }, options.components),
                    defaultColDef: options.defaultColDef,
                    excelNavigation: true,
                    keyboardEditMode: "dom",
                    navigateSkipsNonEditable: false
                });

                tableRef.inst = this;
                this._tableRef = tableRef;
                this.wrapper = container;
                this.options = options;
                this.columnDefs = columnDefs;
                this.loading = false;
                this.table = this;
                container.classList.add("projects-workload-ag-grid");
                if (options.extraClass) {
                    String(options.extraClass).split(/\s+/).filter(Boolean).forEach(className => {
                        container.classList.add(className);
                    });
                }

                initialRows.forEach((row, index) => getRowId(row, index, this));
            }

            getRowAt(index) {
                return this.rows[index];
            }

            refresh(rows, columnDefs) {
                if (Array.isArray(columnDefs)) {
                    const wrapped = wrapWorkloadColumnDefs(columnDefs, this._tableRef);
                    this.columnDefs = wrapped;
                    this.columns = wrapped;
                    this.setGridOption("columnDefs", wrapped);
                }
                if (rows) {
                    rows.forEach((row, index) => getRowId(row, index, this));
                    this.setRows(rows);
                }
                if (Array.isArray(columnDefs) && !rows) {
                    this.renderRows();
                }
            }

            renderRows() {
                const result = super.renderRows();
                this.bodyScrollable = this.container.querySelector(".ag-body-viewport");
                return result;
            }

            renderParticipantCell(row, columnDef, params, innerRenderer) {
                if (!row) return "";

                let content;

                if (typeof innerRenderer === "function") {
                    content = cellRendererResultToHtml(innerRenderer(params));
                } else {
                    const value = params.value == null ? row.participant : params.value;
                    content = value == null ? "" : String(value);
                }

                if (row._isLazyPlaceholder) {
                    content = `<span class="projects-workload-ag-grid-placeholder">${content}</span>`;
                }

                const treeCell = (window.DinextAgGrid && window.DinextAgGrid.treeCell)
                    || (window.DinextAgGridInternals && window.DinextAgGridInternals.treeCell);
                if (!treeCell || typeof treeCell.wrapTreeCellContent !== "function") {
                    const indent = getParticipantIndent(row, this);
                    return `
                <div class="projects-workload-ag-grid-participant" style="padding-left: ${indent}px">
                    <span class="projects-workload-ag-grid-toggle"></span>
                    <span class="projects-workload-ag-grid-participant-content">${content}</span>
                </div>
            `;
                }

                const indentSize = Number.isFinite(Number(this.options.indentSize))
                    ? Number(this.options.indentSize)
                    : 18;

                return treeCell.wrapTreeCellContent(content, row, {
                    table: this,
                    rowIndex: this.rows.indexOf(row),
                    indentMultiplier: indentSize,
                    wrapperClass: "projects-workload-ag-grid-participant",
                    toggleClass: "projects-workload-ag-grid-toggle",
                    contentClass: "projects-workload-ag-grid-participant-content"
                });
            }

            handleCellClick(params) {
                const row = params.data;
                if (!row || params.column.getColId() !== "participant" || !this.isRowExpandable(row)) {
                    return;
                }

                if (row._detailsLoaded === false && typeof window.loadProjectDetailsForUser === "function" && window.cur_frm) {
                    Promise.resolve(window.loadProjectDetailsForUser(window.cur_frm, row)).catch(error => {
                        const message = __("Не удалось загрузить детали проекта");
                        if (window.frappe && typeof window.frappe.show_alert === "function") {
                            window.frappe.show_alert({ message, indicator: "red" });
                        } else if (typeof window.show_alert === "function") {
                            window.show_alert(message);
                        }
                        if (window.console && typeof window.console.error === "function") {
                            window.console.error(message, error);
                        }
                    });
                    return;
                }

                this.toggleRow(this.getRowKey(row, this.rows.indexOf(row)));
            }

            handleCellDoubleClick(params) {
                const colId = params.column && params.column.getColId();
                const columnDef = Array.isArray(this.columnDefs)
                    ? this.columnDefs.find(col => getColumnColId(col) === colId)
                    : null;
                const column = columnDef || { colId, id: colId, field: colId };

                const handler = typeof this.options.onCellDoubleClicked === "function"
                    ? this.options.onCellDoubleClicked
                    : null;
                if (handler) {
                    handler(params.data, column, params);
                } else if (typeof window.handleDoubleClick === "function") {
                    window.handleDoubleClick(params.data, column);
                }
            }

            setCellDoubleClickHandler(handler) {
                this.options.onCellDoubleClicked = typeof handler === "function" ? handler : null;
            }

            freeze(message) {
                this.loading = true;
                super.freeze(message);
                if (message) {
                    this.container.setAttribute("data-loading-message", message);
                }
            }

            unfreeze() {
                this.loading = false;
                super.unfreeze();
                this.container.removeAttribute("data-loading-message");
            }

            destroy() {
                super.destroy();
                this.container.innerHTML = "";
            }
        };
    }

    initWorkloadTableClass();

    if (window.DinextAgGrid) {
        window.DinextAgGrid.presets = window.DinextAgGrid.presets || {};
        window.DinextAgGrid.presets.workload = {
            ensureReady: ensureWorkloadTableReady,
            get Table() {
                return initWorkloadTableClass();
            }
        };
    }
})();

