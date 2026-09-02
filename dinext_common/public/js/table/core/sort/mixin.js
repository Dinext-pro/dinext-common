import { walkLeafColumns } from "../tree/model.js";
import {
    cycleSortState,
    normalizeSortState,
    sortTreeInPlace,
    SORT_DIRS
} from "./model.js";

const SORT_DEFAULTS = {
    enabled: false,
    multi: false,
    nulls: "last",
    state: []
};

const SORT_CLICK_SEL = ".dinext-table-header-sort-text, .dinext-table-header-sort-icon";
const RESIZE_SKIP_SEL = ".ag-header-cell-resize, .ag-header-cell-menu-button";

/** Two-box header: title + sort icon. Sort binds only on those two boxes. */
class DinextSortHeader {
    init(params) {
        this.params = params;
        this.eGui = document.createElement("div");
        this.eGui.className = "dinext-table-header-sort";
        this.eText = document.createElement("div");
        this.eText.className = "dinext-table-header-sort-text";
        this.eIcon = document.createElement("div");
        this.eIcon.className = "dinext-table-header-sort-icon";
        this.eIcon.setAttribute("aria-hidden", "true");
        this.eGui.append(this.eText, this.eIcon);
        this.eText.textContent = params.displayName || "";
        this._onSortClick = (event) => this.handleSortClick(event);
        this.eText.addEventListener("click", this._onSortClick);
        this.eIcon.addEventListener("click", this._onSortClick);
    }

    getGui() {
        return this.eGui;
    }

    refresh(params) {
        this.params = params;
        this.eText.textContent = params.displayName || "";
        return true;
    }

    handleSortClick(event) {
        if (event.target?.closest?.(RESIZE_SKIP_SEL)) {
            return;
        }
        if (!event.target?.closest?.(SORT_CLICK_SEL)) {
            return;
        }
        event.stopPropagation();
        const field = this.params?.column?.getColDef?.()?.field;
        if (typeof this.params?.onDinextSortClick === "function") {
            this.params.onDinextSortClick(field);
        }
    }

    destroy() {
        this.eText?.removeEventListener("click", this._onSortClick);
        this.eIcon?.removeEventListener("click", this._onSortClick);
    }
}

function findRawColumn(columns, field) {
    let match = null;
    walkLeafColumns(columns, (col) => {
        if (col?.field === field) {
            match = col;
            return true;
        }
    });
    return match;
}

/**
 * Client sort layer: recursive sibling sort on source tree (merge atoms).
 * Does not use AG Grid Client-Side sorting (would break tree / rowSpan).
 */
export const SortMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this.initSortState();
    }

    afterGridCreated() {
        super.afterGridCreated();
        this.syncSortHeaderClasses();
    }

    initSortState() {
        const opts = this.getSortOptions();
        this._sortState = normalizeSortState(opts.state);
        if (this.isSortEnabled() && this._sortState.length && Array.isArray(this.sourceData)) {
            sortTreeInPlace(this.sourceData, this._sortState, this.options);
            if (typeof this.syncVisibleRows === "function") {
                this.syncVisibleRows();
            }
        }
    }

    getSortOptions() {
        return { ...SORT_DEFAULTS, ...(this.options.sort || {}) };
    }

    isSortEnabled() {
        return !!this.getSortOptions().enabled;
    }

    isSortActive() {
        return this.isSortEnabled() && this._sortState.length > 0;
    }

    getSort() {
        return this._sortState.map((s) => ({ ...s }));
    }

    isColumnSortable(field) {
        if (!this.isSortEnabled() || field == null || field === "") {
            return false;
        }
        const col = findRawColumn(this.columns, String(field));
        if (!col) {
            return false;
        }
        if (col.sortable === false) {
            return false;
        }
        return true;
    }

    setSort(state, { silent = false } = {}) {
        if (!this.isSortEnabled()) {
            return this.getSort();
        }
        this._sortState = normalizeSortState(state);
        this.applySortToSource();
        this.syncSortHeaderClasses();
        if (!silent) {
            this.emitSortChange();
        }
        return this.getSort();
    }

    clearSort(opts = {}) {
        return this.setSort([], opts);
    }

    applySortToSource() {
        if (!Array.isArray(this.sourceData)) {
            return;
        }
        if (this._sortState.length) {
            sortTreeInPlace(this.sourceData, this._sortState, this.options);
        }
        if (typeof this.syncVisibleRows === "function") {
            this.syncVisibleRows();
        }
        this.setGridOption("rowData", [...(this.rowData || [])]);
        if (typeof this.clearCellSelection === "function") {
            this.clearCellSelection();
        }
    }

    emitSortChange() {
        if (typeof this.options.onSortChange === "function") {
            this.options.onSortChange({
                sort: this.getSort(),
                table: this
            });
        }
    }

    cycleColumnSort(field) {
        if (!this.isColumnSortable(field)) {
            return this.getSort();
        }
        const next = cycleSortState(this._sortState, field, {
            multi: !!this.getSortOptions().multi
        });
        return this.setSort(next);
    }

    refresh(data) {
        if (data !== undefined) {
            this.sourceData = data;
            this.options.data = data;
        }
        if (this.isSortActive() && Array.isArray(this.sourceData)) {
            sortTreeInPlace(this.sourceData, this._sortState, this.options);
        }
        super.refresh();
        this.syncSortHeaderClasses();
    }

    setRowChildren(rowId, children) {
        let next = children;
        if (this.isSortActive() && Array.isArray(children)) {
            next = children.slice();
            sortTreeInPlace(next, this._sortState, this.options);
        }
        super.setRowChildren(rowId, next);
    }

    refreshAfterRowReorder(section) {
        if (section !== "summary" && this._sortState?.length) {
            if (Array.isArray(this.sourceData)) {
                sortTreeInPlace(this.sourceData, this._sortState, this.options);
            }
        }
        super.refreshAfterRowReorder?.(section);
        this.syncSortHeaderClasses();
    }

    buildColumnDefs() {
        const defs = super.buildColumnDefs();
        if (!this.isSortEnabled()) {
            return defs;
        }
        return this.applySortMetaToColumnDefs(defs);
    }

    applySortMetaToColumnDefs(columnDefs) {
        return (columnDefs || []).map((col) => {
            if (Array.isArray(col.children) && col.children.length) {
                return {
                    ...col,
                    children: this.applySortMetaToColumnDefs(col.children)
                };
            }
            if (!col.field) {
                return col;
            }
            const sortable = this.isColumnSortable(col.field);
            const headerClass = this.buildSortHeaderClass(col.field, col.headerClass);
            const useDinextHeader = sortable && !col.headerComponent;
            const existingParams = col.headerComponentParams;
            return {
                ...col,
                sortable: false,
                headerClass,
                ...(sortable
                    ? {
                        headerTooltip: col.headerTooltip,
                        headerComponent: col.headerComponent || DinextSortHeader
                    }
                    : {}),
                ...(useDinextHeader
                    ? {
                        headerComponentParams: {
                            ...(existingParams && typeof existingParams === "object"
                                ? existingParams
                                : {}),
                            onDinextSortClick: (field) => this.cycleColumnSort(field)
                        }
                    }
                    : {})
            };
        });
    }

    buildSortHeaderClass(field, existing) {
        return (params) => {
            const classes = [];
            if (typeof existing === "function") {
                const result = existing(params);
                if (Array.isArray(result)) {
                    classes.push(...result);
                } else if (result) {
                    classes.push(String(result));
                }
            } else if (Array.isArray(existing)) {
                classes.push(...existing);
            } else if (existing) {
                classes.push(String(existing));
            }

            if (this.isColumnSortable(field)) {
                classes.push("dinext-table-header--sortable");
                const spec = this._sortState.find((s) => s.field === field);
                if (spec?.dir === SORT_DIRS.ASC) {
                    classes.push("dinext-table-header--sort-asc");
                } else if (spec?.dir === SORT_DIRS.DESC) {
                    classes.push("dinext-table-header--sort-desc");
                }
            }
            return classes;
        };
    }

    syncSortHeaderClasses() {
        if (!this.api || !this.isSortEnabled()) {
            return;
        }
        // Rebuild colDefs so headerClass closures see current _sortState
        this.setGridOption("columnDefs", this.buildColumnDefs());
    }

    buildSortGridOptions() {
        // Sort is bound on DinextSortHeader text/icon only — never the full cell.
        return {};
    }

    handleSetOption(key, value) {
        if (key === "sort") {
            this.options.sort = value;
            const opts = this.getSortOptions();
            this._sortState = normalizeSortState(opts.state);
            if (this.isSortEnabled()) {
                this.setGridOption("columnDefs", this.buildColumnDefs());
                if (this._sortState.length) {
                    this.applySortToSource();
                } else {
                    this.syncSortHeaderClasses();
                }
            } else {
                this._sortState = [];
                this.setGridOption("columnDefs", this.buildColumnDefs());
            }
            return true;
        }
        return super.handleSetOption?.(key, value) ?? false;
    }
};
