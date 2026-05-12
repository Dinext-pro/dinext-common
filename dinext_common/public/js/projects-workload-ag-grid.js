(function() {
    const AG_GRID_VERSION = "35.2.1";
    const AG_GRID_JS = "/assets/dinext_common/js/ag-grid-community.min.js";
    const AG_GRID_CSS = [
        "/assets/dinext_common/css/ag-grid.css",
        "/assets/dinext_common/css/ag-theme-quartz.css"
    ];

    let agGridPromise = null;

    function loadScriptOnce(url, globalCheck) {
        if (globalCheck && globalCheck()) {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[src="${url}"]`);
            if (existing) {
                existing.addEventListener("load", resolve, { once: true });
                existing.addEventListener("error", reject, { once: true });
                if (globalCheck && globalCheck()) resolve();
                return;
            }

            const script = document.createElement("script");
            script.src = url;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function loadStyleOnce(url) {
        if (document.querySelector(`link[href="${url}"]`)) return;

        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        document.head.appendChild(link);
    }

    function injectProjectsWorkloadAgGridCss() {
        if (document.getElementById("projects-workload-ag-grid-css")) return;

        const style = document.createElement("style");
        style.id = "projects-workload-ag-grid-css";
        style.textContent = `
            .projects-workload-ag-grid {
                width: calc(100% - 4px);
                height: 70vh;
                min-height: 420px;
                margin: 0.5rem 0 4px 4px;
                border-radius: 0;
                font-family: inherit;
                font-size: var(--text-md);
                --ag-font-family: inherit;
                --ag-font-size: var(--text-md);
                --ag-border-radius: 0;
                --ag-wrapper-border-radius: 0;
                --ag-row-border-color: transparent;
                --ag-cell-horizontal-border: none;
                --ag-border-color: var(--border-color);
                --ag-header-column-separator-display: none;
                --ag-header-column-resize-handle-display: none;
                --ag-background-color: var(--bg-color);
                --ag-header-background-color: rgb(243, 243, 243);
                --ag-header-foreground-color: var(--text-color);
                --ag-foreground-color: var(--text-color);
                --projects-workload-ag-header-bg: rgb(243, 243, 243);
                --projects-workload-ag-header-main-color: var(--text-color);
                --projects-workload-ag-header-sub-color: var(--text-color);
            }
            .projects-workload-ag-grid .ag-pinned-left-header {
                --ag-header-column-resize-handle-display: block;
            }
            [data-theme="dark"] .projects-workload-ag-grid,
            .projects-workload-ag-grid.projects-workload-ag-grid-dark {
                --ag-background-color: rgb(23, 23, 23);
                --ag-header-background-color: var(--subtle-fg, #1f2226);
                --ag-foreground-color: var(--text-color);
                --projects-workload-ag-header-bg: var(--subtle-fg, #1f2226);
                --projects-workload-ag-header-main-color: var(--text-color, #f4f4f4);
                --projects-workload-ag-header-sub-color: var(--text-color, #f4f4f4);
            }
            .projects-workload-ag-grid .ag-root-wrapper {
                border: 1px solid var(--border-color) !important;
                border-radius: 0 !important;
                background: var(--ag-background-color) !important;
            }
            .projects-workload-ag-grid .ag-root,
            .projects-workload-ag-grid .ag-body,
            .projects-workload-ag-grid .ag-body-viewport,
            .projects-workload-ag-grid .ag-center-cols-viewport,
            .projects-workload-ag-grid .ag-center-cols-container,
            .projects-workload-ag-grid .ag-pinned-left-cols-container {
                background: var(--ag-background-color) !important;
            }
            .projects-workload-ag-grid .ag-row {
                border: none !important;
                background: transparent !important;
            }
            .projects-workload-ag-grid .ag-cell {
                padding: 0 !important;
                margin: 0 !important;
                line-height: normal;
                border: none !important;
                overflow: hidden !important;
            }
            .projects-workload-ag-grid .ag-cell-wrapper,
            .projects-workload-ag-grid .ag-cell-value {
                width: 100%;
                height: 100%;
                padding: 0 !important;
                margin: 0 !important;
                display: block;
            }
            .projects-workload-ag-grid .ag-header-cell-label {
                justify-content: center;
                text-align: center;
            }
            .projects-workload-ag-grid .ag-header,
            .projects-workload-ag-grid .ag-header-row,
            .projects-workload-ag-grid .ag-header-cell {
                background: var(--projects-workload-ag-header-bg);
            }
            .projects-workload-ag-grid .ag-header {
                border-bottom: none !important;
            }
            .projects-workload-ag-grid .ag-header-cell {
                padding: 0 !important;
                border-right: none !important;
            }
            .projects-workload-ag-grid .ag-header-viewport .ag-header-cell-resize {
                display: none !important;
            }
            .projects-workload-ag-grid .ag-header-cell::before,
            .projects-workload-ag-grid .ag-header-group-cell::before {
                display: none !important;
            }
            .projects-workload-ag-grid .ag-header-viewport .ag-header-cell-resize::after {
                display: none !important;
            }
            .projects-workload-ag-grid .ag-pinned-left-header,
            .projects-workload-ag-grid .ag-pinned-left-cols-container {
                border-right: 1px solid var(--border-color) !important;
            }
            .projects-workload-ag-grid[data-loading-message]::after {
                content: attr(data-loading-message);
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                z-index: 10;
                padding: 8px 12px;
                border: 1px solid var(--border-color);
                border-radius: 4px;
                background: var(--fg-color, var(--bg-color));
                color: var(--text-color);
                box-shadow: var(--shadow-sm, 0 2px 8px rgba(0, 0, 0, 0.12));
                pointer-events: none;
            }
            .projects-workload-ag-grid .projects-workload-ag-grid-header {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 100%;
                line-height: 1.4;
                text-align: center;
                padding: 10px 0 !important;
            }
            .projects-workload-ag-grid .projects-workload-ag-grid-header-main {
                color: var(--projects-workload-ag-header-main-color);
                font-size: 12px;
                font-weight: 600;
            }
            .projects-workload-ag-grid .projects-workload-ag-grid-header-sub {
                margin-top: 2px;
                color: var(--projects-workload-ag-header-sub-color);
                font-size: 11px;
                font-weight: 700;
                opacity: 0.9;
            }
            .projects-workload-ag-grid .projects-workload-ag-grid-header-single {
                color: var(--projects-workload-ag-header-main-color);
                font-size: 12px;
                font-weight: 600;
                white-space: normal;
            }
            .projects-workload-ag-grid-participant {
                display: flex;
                align-items: center;
                height: 100%;
                padding: 0 8px !important;
                cursor: default;
            }
            .projects-workload-ag-grid-toggle {
                width: 16px;
                min-width: 16px;
                color: var(--text-muted, #6c7680);
                cursor: pointer;
                font-size: 18px;
                font-weight: 400;
                line-height: 1;
                text-align: center;
                user-select: none;
            }
            .projects-workload-ag-grid-placeholder {
                color: var(--text-muted, #6c7680);
                font-style: italic;
            }
        `;
        document.head.appendChild(style);
    }

    function ensureAgGrid() {
        if (window.agGrid && typeof window.agGrid.createGrid === "function") {
            return Promise.resolve();
        }

        if (!agGridPromise) {
            AG_GRID_CSS.forEach(loadStyleOnce);
            injectProjectsWorkloadAgGridCss();
            agGridPromise = loadScriptOnce(AG_GRID_JS, () => window.agGrid && typeof window.agGrid.createGrid === "function")
                .then(() => {
                    if (!window.agGrid || typeof window.agGrid.createGrid !== "function") {
                        throw new Error("AG Grid не загрузился");
                    }
                });
        }

        return agGridPromise;
    }

    function getDefaultRowLevel(row) {
        const indent = Number(row && row.indent);
        return Number.isFinite(indent) ? Math.max(0, indent) : 0;
    }

    function getDefaultRowKey(row, index) {
        if (!row) return `row-${index}`;
        if (row._agRowKey) return row._agRowKey;

        if (row.level === "user" || row.isUser || row._isUser) {
            return `user:${row.email || row._email || row.participant || index}`;
        }
        if (row.level === "role" || row.isRole) {
            return `role:${row.email || row._email || "user"}:${row.roleName || row.role || row.participant || index}`;
        }
        if (row.level === "task" || row.isTask) {
            return `task:${row.email || row._email || "user"}:${row.roleName || row.role || "role"}:${row.task_id || row.name || row.participant || index}`;
        }
        if (row._isAbsenceRow) {
            return `absence:${row._email || row.email || index}`;
        }
        if (row._isLazyPlaceholder) {
            return `placeholder:${row._email || row.email || index}`;
        }
        if (row._isProject) {
            return `project:${row._email || row.email || "user"}:${row._project || row.project || row.participant || index}`;
        }

        return `row:${row.participant || row.name || index}:${index}`;
    }

    function getRowId(row, index, table) {
        if (!row) return `row-${index}`;
        if (row._agRowId) return row._agRowId;

        const key = table ? table.getRowKey(row, index) : getDefaultRowKey(row, index);
        row._agRowId = `${key}:${index}`;
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

    function toVisibleRows(rows, table) {
        const expandedByLevel = [];
        const visibleRows = [];

        (rows || []).forEach((row, index) => {
            if (!row) return false;
            const level = table.getRowLevel(row);
            const parentVisible = level <= 0 || expandedByLevel[level - 1] !== false;
            const rowVisible = level <= 0 || parentVisible;

            if (rowVisible) {
                visibleRows.push(row);
            }

            const expandable = table.isRowExpandable(row, index);
            const rowKey = table.getRowKey(row, index);
            expandedByLevel[level] = rowVisible && (!expandable || table.expandedRows.has(rowKey));
            expandedByLevel.length = level + 1;
        });

        return visibleRows;
    }

    function toAgColumn(column, index, table) {
        const field = column.id || column.name || `col_${index}`;
        const isParticipant = field === "participant" || index === 0;
        const width = Number(column.width) || (isParticipant ? table.options.participantWidth || 220 : 50);
        const minWidth = Number(column.minWidth) || (isParticipant ? Math.min(width, 160) : width);
        const maxWidth = Number(column.maxWidth) || (isParticipant ? undefined : width);

        const agColumn = {
            field,
            colId: field,
            headerName: column.name || "",
            headerComponent: ProjectsWorkloadAgGridHeader,
            headerComponentParams: {
                html: column.name || ""
            },
            width,
            minWidth,
            pinned: isParticipant ? "left" : undefined,
            lockPinned: isParticipant,
            suppressMovable: true,
            sortable: !!column.sortable,
            resizable: isParticipant,
            cellClass: params => {
                const classes = [];
                if (isParticipant) classes.push("projects-workload-ag-grid-participant-cell");
                if (params.data && params.data.level) classes.push(`level-${params.data.level}`);
                if (typeof column.cellClass === "function") {
                    const customClass = column.cellClass(params);
                    if (Array.isArray(customClass)) {
                        classes.push(...customClass);
                    } else if (customClass) {
                        classes.push(customClass);
                    }
                } else if (column.cellClass) {
                    classes.push(column.cellClass);
                }
                return classes;
            },
            cellRenderer: params => {
                if (isParticipant) {
                    return table.renderParticipantCell(params.data, column, params);
                }

                if (typeof column.format === "function") {
                    return column.format(params.value, null, column, params.data);
                }

                return params.value == null ? "" : String(params.value);
            }
        };

        if (Number.isFinite(maxWidth)) {
            agColumn.maxWidth = maxWidth;
        }

        return agColumn;
    }

    function isFrappeDarkTheme() {
        const root = document.documentElement;
        const resolvedTheme = root.getAttribute("data-theme");
        const selectedTheme = root.getAttribute("data-theme-mode");

        if (resolvedTheme) return resolvedTheme === "dark";
        return selectedTheme === "dark";
    }

    class ProjectsWorkloadAgGridHeader {
        init(params) {
            const rawHtml = params.html || params.displayName || "";
            const parts = String(rawHtml)
                .split(/<br\s*\/?>/i)
                .map(part => part.replace(/<\/?small>/gi, "").trim())
                .filter(Boolean);

            this.eGui = document.createElement("div");
            this.eGui.className = "projects-workload-ag-grid-header";

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

    class ProjectsWorkloadAgGridTable {
        constructor(container, options = {}) {
            this.container = container;
            this.wrapper = container;
            this.options = options;
            this.columns = options.columns || [];
            this.rows = options.data || [];
            this.expandedRows = new Set();
            this.loading = false;
            this.getRowLevel = typeof options.getRowLevel === "function"
                ? options.getRowLevel
                : getDefaultRowLevel;
            this.getRowKey = typeof options.getRowKey === "function"
                ? options.getRowKey
                : getDefaultRowKey;
            this.isRowExpandable = typeof options.isRowExpandable === "function"
                ? options.isRowExpandable
                : isDefaultExpandableRow;
            this.onCellDoubleClick = typeof options.onCellDoubleClick === "function"
                ? options.onCellDoubleClick
                : null;

            this.container.classList.add("projects-workload-ag-grid");
            if (options.extraClass) {
                String(options.extraClass).split(/\s+/).filter(Boolean).forEach(className => {
                    this.container.classList.add(className);
                });
            }
            this.applyTheme();
            this.themeObserver = new MutationObserver(() => this.applyTheme());
            this.themeObserver.observe(document.documentElement, {
                attributes: true,
                attributeFilter: ["data-theme", "data-theme-mode"]
            });
            this.rowmanager = {
                collapseAllNodes: () => {
                    this.expandedRows.clear();
                    this.renderRows();
                },
                openSingleNode: rowIndex => {
                    const row = this.rows[rowIndex];
                    if (row) {
                        this.expandedRows.add(this.getRowKey(row, rowIndex));
                        this.renderRows();
                    }
                }
            };

            this.gridOptions = {
                theme: "legacy",
                columnDefs: this.columns.map((column, index) => toAgColumn(column, index, this)),
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
                getRowId: params => params.data && params.data._agRowId ? params.data._agRowId : getRowId(params.data, 0, this),
                getRowClass: params => params.data && params.data.level ? `level-${params.data.level}` : "",
                onGridReady: params => {
                    this.api = params.api;
                    this.bodyScrollable = this.container.querySelector(".ag-body-viewport");
                    this.renderRows();
                },
                onCellClicked: params => this.handleCellClick(params),
                onCellDoubleClicked: params => this.handleCellDoubleClick(params)
            };

            this.api = window.agGrid.createGrid(this.container, this.gridOptions);
            this.renderRows();
        }

        applyTheme() {
            const isDark = isFrappeDarkTheme();
            this.container.classList.toggle("ag-theme-quartz", !isDark);
            this.container.classList.toggle("ag-theme-quartz-dark", isDark);
            this.container.classList.toggle("projects-workload-ag-grid-dark", isDark);
        }

        refresh(rows, columns) {
            this.rows = rows || [];
            this.columns = columns || this.columns || [];
            this.rows.forEach((row, index) => getRowId(row, index, this));

            const columnDefs = this.columns.map((column, index) => toAgColumn(column, index, this));
            this.setGridOption("columnDefs", columnDefs);
            this.renderRows();
        }

        renderRows() {
            const visibleRows = toVisibleRows(this.rows, this);
            this.setGridOption("rowData", visibleRows);
            this.bodyScrollable = this.container.querySelector(".ag-body-viewport");
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
            }
        }

        renderParticipantCell(row, column, params) {
            if (!row) return "";

            const value = params.value == null ? row.participant : params.value;
            const indent = getParticipantIndent(row, this);
            const rowKey = this.getRowKey(row, this.rows.indexOf(row));
            const hasToggle = this.isRowExpandable(row);
            const expanded = hasToggle && this.expandedRows.has(rowKey);
            let content = "";

            if (typeof column.format === "function") {
                content = column.format(value, null, column, row);
            } else {
                content = value == null ? "" : String(value);
            }

            if (row._isLazyPlaceholder) {
                content = `<span class="projects-workload-ag-grid-placeholder">${content}</span>`;
            }

            return `
                <div class="projects-workload-ag-grid-participant" style="padding-left: ${indent}px">
                    <span class="projects-workload-ag-grid-toggle">${hasToggle ? (expanded ? "⌄" : "›") : ""}</span>
                    <span class="projects-workload-ag-grid-participant-content">${content}</span>
                </div>
            `;
        }

        handleCellClick(params) {
            const row = params.data;
            if (!row || params.column.getColId() !== "participant" || !this.isRowExpandable(row)) {
                return;
            }

            if (row._detailsLoaded === false && typeof window.loadProjectDetailsForUser === "function" && window.cur_frm) {
                window.loadProjectDetailsForUser(window.cur_frm, row);
                return;
            }

            const rowKey = this.getRowKey(row, this.rows.indexOf(row));
            if (this.expandedRows.has(rowKey)) {
                this.expandedRows.delete(rowKey);
            } else {
                this.expandedRows.add(rowKey);
            }
            this.renderRows();
        }

        handleCellDoubleClick(params) {
            const column = this.columns.find(col => (col.id || col.name) === params.column.getColId()) || {
                id: params.column.getColId()
            };

            if (this.onCellDoubleClick) {
                this.onCellDoubleClick(params.data, column, params);
            } else if (typeof window.handleDoubleClick === "function") {
                window.handleDoubleClick(params.data, column);
            }
        }

        setCellDoubleClickHandler(handler) {
            this.onCellDoubleClick = typeof handler === "function" ? handler : null;
        }

        freeze(message) {
            this.loading = true;
            if (this.api && typeof this.api.setGridOption === "function") {
                this.api.setGridOption("loading", true);
            }
            if (message) {
                this.container.setAttribute("data-loading-message", message);
            }
        }

        unfreeze() {
            this.loading = false;
            if (this.api && typeof this.api.setGridOption === "function") {
                this.api.setGridOption("loading", false);
            }
            this.container.removeAttribute("data-loading-message");
        }

        destroy() {
            if (this.themeObserver) {
                this.themeObserver.disconnect();
                this.themeObserver = null;
            }
            if (this.api && typeof this.api.destroy === "function") {
                this.api.destroy();
            }
            this.container.innerHTML = "";
        }
    }

    window.ProjectsWorkloadAgGrid = {
        ensure: ensureAgGrid,
        Table: ProjectsWorkloadAgGridTable
    };
})();
