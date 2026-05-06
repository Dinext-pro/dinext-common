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
            .projects-workload-ag-grid .ag-header-cell-resize {
                display: none !important;
            }
            .projects-workload-ag-grid .ag-header-cell::before,
            .projects-workload-ag-grid .ag-header-group-cell::before,
            .projects-workload-ag-grid .ag-header-cell-resize::after {
                display: none !important;
            }
            .projects-workload-ag-grid .ag-pinned-left-header,
            .projects-workload-ag-grid .ag-pinned-left-cols-container {
                border-right: 1px solid var(--border-color) !important;
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

    function getRowId(row, index) {
        if (!row) return `row-${index}`;
        if (row._agRowId) return row._agRowId;

        const type = row._isUser ? "user" : row._isProject ? "project" : row._isAbsenceRow ? "absence" : row._isLazyPlaceholder ? "placeholder" : "row";
        const key = row._email || row._project || row.project || row.participant || index;
        row._agRowId = `${type}:${key}:${index}`;
        return row._agRowId;
    }

    function getParticipantIndent(row) {
        const indent = Number(row && row.indent);
        return Number.isFinite(indent) ? indent * 18 : 0;
    }

    function isChildOfExpandedUser(row, expandedUsers) {
        if (!row || !row._email) return false;
        if (!row.indent || row.indent <= 0) return true;
        return expandedUsers.has(row._email);
    }

    function toVisibleRows(rows, expandedUsers) {
        return (rows || []).filter(row => {
            if (!row) return false;
            if (!row.indent || row.indent <= 0) return true;
            return isChildOfExpandedUser(row, expandedUsers);
        });
    }

    function toAgColumn(column, index, table) {
        const field = column.id || column.name || `col_${index}`;
        const isParticipant = field === "participant" || index === 0;

        return {
            field,
            colId: field,
            headerName: column.name || "",
            headerComponent: ProjectsWorkloadAgGridHeader,
            headerComponentParams: {
                html: column.name || ""
            },
            width: isParticipant ? 200 : 50,
            minWidth: isParticipant ? 200 : 50,
            maxWidth: isParticipant ? 200 : 50,
            pinned: isParticipant ? "left" : undefined,
            lockPinned: isParticipant,
            suppressMovable: true,
            sortable: !!column.sortable,
            resizable: false,
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
            this.expandedUsers = new Set();
            this.loading = false;

            this.container.classList.add("projects-workload-ag-grid");
            this.applyTheme();
            this.themeObserver = new MutationObserver(() => this.applyTheme());
            this.themeObserver.observe(document.documentElement, {
                attributes: true,
                attributeFilter: ["data-theme", "data-theme-mode"]
            });
            this.rowmanager = {
                collapseAllNodes: () => {
                    this.expandedUsers.clear();
                    this.renderRows();
                },
                openSingleNode: rowIndex => {
                    const row = this.rows[rowIndex];
                    if (row && row._email) {
                        this.expandedUsers.add(row._email);
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
                getRowId: params => params.data && params.data._agRowId ? params.data._agRowId : getRowId(params.data, 0),
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
            this.rows.forEach((row, index) => getRowId(row, index));

            const columnDefs = this.columns.map((column, index) => toAgColumn(column, index, this));
            this.setGridOption("columnDefs", columnDefs);
            this.renderRows();
        }

        renderRows() {
            const visibleRows = toVisibleRows(this.rows, this.expandedUsers);
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
            const indent = getParticipantIndent(row);
            const hasToggle = row._isUser && row._email;
            const expanded = hasToggle && this.expandedUsers.has(row._email);
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
            if (!row || params.column.getColId() !== "participant" || !row._isUser || !row._email) {
                return;
            }

            if (row._detailsLoaded === false && typeof window.loadProjectDetailsForUser === "function" && window.cur_frm) {
                window.loadProjectDetailsForUser(window.cur_frm, row);
                return;
            }

            if (this.expandedUsers.has(row._email)) {
                this.expandedUsers.delete(row._email);
            } else {
                this.expandedUsers.add(row._email);
            }
            this.renderRows();
        }

        handleCellDoubleClick(params) {
            if (typeof window.handleDoubleClick !== "function") return;

            const column = this.columns.find(col => (col.id || col.name) === params.column.getColId()) || {
                id: params.column.getColId()
            };
            window.handleDoubleClick(params.data, column);
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
