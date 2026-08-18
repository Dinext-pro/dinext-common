import { getRowIdField } from "../shared/utils.js";
import { toVisibleRows, walkLeafColumns } from "../tree/model.js";
import { ROW_CHECK_COL_ID } from "../row-check/constants.js";
import { TOOLBAR_ICON_SVG } from "../toolbar/icons.js";
import {
    filterFlatRows,
    filterTreeRows,
    isFilterStateEmpty,
    normalizeFilterState,
    sameFilterState
} from "./model.js";
import { DinextNoopFilter, DinextTextFloatingFilter } from "./floating-filter.js";

const FILTER_DEFAULTS = {
    enabled: true,
    active: false,
    mergeMatchMode: "atom",
    mergeAncestorMode: "atom",
    mergeInheritedFields: [],
    state: {}
};

/** Compact search row. AG defaults this to `headerHeight` (76px on wtree). */
export const FLOATING_FILTER_ROW_HEIGHT = 28;

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
 * Client column filter layer.
 * Source data untouched; filters visible body rows. Summary out.
 * Tree: match + ancestors (auto-expand ancestors for display only).
 */
export const FilterMixin = (Base) => class extends Base {
    initFeatures() {
        // Before Tree syncVisibleRows so initial filter.state applies on first paint.
        this.initFilterState();
        super.initFeatures();
    }

    afterGridCreated() {
        super.afterGridCreated();
        if (!this.isFilterEnabled()) {
            return;
        }
        if (this.isFilterRowOpen()) {
            this.syncFilterFloatingFilters();
        }
        // Persist may have restored state after options init — re-apply rows.
        if (this.isFilterActive()) {
            this.applyFilterToGrid();
        }
    }

    initFilterState() {
        const opts = this.getFilterOptions();
        this._filterState = normalizeFilterState(opts.state);
        this._filterRowOpen = !!opts.active;
    }

    /**
     * Apply filter slice from UI persist (toolbar.persistKey).
     * Called by ToolbarMixin before Filter.afterGridCreated.
     */
    applyLoadedUiPersistFilter() {
        const snap = this._uiPersistFilter;
        if (!snap || !this.isFilterEnabled()) {
            return;
        }
        if (snap.state != null) {
            this._filterState = normalizeFilterState(snap.state);
        }
        if (typeof snap.active === "boolean") {
            this._filterRowOpen = snap.active;
        }
    }

    persistUiState() {
        this.saveUiPersistedState?.();
    }

    getFilterOptions() {
        return { ...FILTER_DEFAULTS, ...(this.options.filter || {}) };
    }

    isFilterEnabled() {
        return !!this.getFilterOptions().enabled;
    }

    isFilterRowOpen() {
        return this.isFilterEnabled() && !!this._filterRowOpen;
    }

    /** Non-empty filter state (applies even if UI closed — Keep). */
    isFilterActive() {
        return this.isFilterEnabled() && !isFilterStateEmpty(this._filterState);
    }

    /**
     * Auto-injected into toolbar when filter.enabled (like rowCheck).
     * Always present unless `filter.enabled: false`.
     */
    getFilterToolbarItems() {
        if (!this.isFilterEnabled()) {
            return [];
        }
        return [{
            id: "filter",
            title: "Filter columns",
            iconSvg: TOOLBAR_ICON_SVG.search,
            active: ({ table: instance }) => (
                typeof instance.isFilterRowOpen === "function" && instance.isFilterRowOpen()
            ),
            onClick: ({ table: instance }) => {
                instance.toggleFilterRow();
            }
        }];
    }

    getFilter() {
        return { ...this._filterState };
    }

    isColumnFilterable(field) {
        if (!this.isFilterEnabled() || field == null || field === "") {
            return false;
        }
        if (String(field) === ROW_CHECK_COL_ID) {
            return false;
        }
        const col = findRawColumn(this.columns, String(field));
        if (!col) {
            return false;
        }
        if (col.filterable === false) {
            return false;
        }
        return true;
    }

    setFilter(state, { silent = false, syncInputs = true } = {}) {
        if (!this.isFilterEnabled()) {
            return this.getFilter();
        }
        const next = normalizeFilterState(state);
        if (sameFilterState(this._filterState, next)) {
            if (syncInputs) {
                this.syncFloatingFilterInputs();
            }
            return this.getFilter();
        }
        this._filterState = next;
        this.applyFilterToGrid();
        if (syncInputs) {
            this.syncFloatingFilterInputs();
        }
        if (!silent) {
            this.emitFilterChange();
        }
        this.persistUiState();
        this.refreshToolbar?.();
        return this.getFilter();
    }

    setFilterField(field, query, opts = {}) {
        if (!this.isFilterEnabled() || field == null || field === "") {
            return this.getFilter();
        }
        const next = { ...this._filterState };
        const trimmed = query == null ? "" : String(query);
        if (!trimmed.trim()) {
            delete next[String(field)];
        } else {
            next[String(field)] = trimmed;
        }
        // Floating filter already owns the input value — skip header remount (focus).
        return this.setFilter(next, { ...opts, syncInputs: false });
    }

    clearFilter(opts = {}) {
        return this.setFilter({}, opts);
    }

    toggleFilterRow(force) {
        if (!this.isFilterEnabled()) {
            return this.isFilterRowOpen();
        }
        const next = force === undefined ? !this._filterRowOpen : !!force;
        if (next === this._filterRowOpen) {
            return this.isFilterRowOpen();
        }
        this._filterRowOpen = next;
        this.syncFilterFloatingFilters();
        this.emitFilterChange();
        this.persistUiState();
        this.refreshToolbar?.();
        return this.isFilterRowOpen();
    }

    syncVisibleRows() {
        super.syncVisibleRows();
        if (this.isFilterActive()) {
            this.rebuildFilterPassIds();
        } else {
            this._filterPassIds = null;
        }
    }

    getFilterRowId(row) {
        if (!row) {
            return "";
        }
        if (row._rowId !== undefined) {
            return String(row._rowId);
        }
        return String(row[getRowIdField(this.options)]);
    }

    rebuildFilterPassIds() {
        if (!this.isFilterActive()) {
            this._filterPassIds = null;
            return;
        }

        const ids = new Set();
        const nested = typeof this.hasNestedRows === "function" && this.hasNestedRows();
        if (nested) {
            const { rows: pruned, expandIds } = filterTreeRows(
                this.sourceData || [],
                this._filterState,
                this.options
            );
            const expanded = new Set([
                ...(this.expandedIds || []),
                ...expandIds
            ]);
            const visible = toVisibleRows(pruned, expanded, this.options);
            for (const row of visible) {
                ids.add(this.getFilterRowId(row));
            }
        } else {
            const rows = filterFlatRows(
                this.sourceData || this.rowData || [],
                this._filterState,
                this.options
            );
            for (const row of rows) {
                ids.add(this.getFilterRowId(row));
            }
        }
        this._filterPassIds = ids;
    }

    doesExternalFilterPass(node) {
        if (!this.isFilterActive()) {
            return true;
        }
        if (!this._filterPassIds) {
            this.rebuildFilterPassIds();
        }
        const id = this.getFilterRowId(node?.data);
        if (!id) {
            return true;
        }
        return this._filterPassIds.has(id);
    }

    ensureFilterAncestorsExpanded() {
        if (!this.isFilterActive() || typeof this.hasNestedRows !== "function") {
            return;
        }
        if (!this.hasNestedRows() || !this.expandedIds) {
            return;
        }

        const { expandIds } = filterTreeRows(
            this.sourceData || [],
            this._filterState,
            this.options
        );
        const sorted = [...expandIds].sort((a, b) => a.length - b.length);
        for (const id of sorted) {
            const wasExpanded = this.expandedIds.has(id);
            this.expandedIds.add(id);
            if (wasExpanded) {
                continue;
            }
            if (this.api?.getRowNode?.(id)) {
                super.insertVisibleChildren(id);
            }
        }
    }

    refreshFilteredProjection() {
        this.rebuildFilterPassIds();
        this.api?.onFilterChanged?.();
        this._filterProjectionRefreshVersion =
            (this._filterProjectionRefreshVersion || 0) + 1;
    }

    /** Active filter: insert as usual, then hide via AG external filter. */
    insertVisibleChildren(rowId) {
        super.insertVisibleChildren(rowId);
        if (this.isFilterActive()) {
            this.refreshFilteredProjection();
        }
    }

    /**
     * Lazy children stay in the row model. Re-run external filter once if
     * Tree/Sort did not already notify AG (same version guard as before).
     */
    setRowChildren(rowId, children) {
        const refreshVersion = this._filterProjectionRefreshVersion || 0;
        const result = super.setRowChildren(rowId, children);
        if (
            this.isFilterActive()
            && (this._filterProjectionRefreshVersion || 0) === refreshVersion
        ) {
            this.refreshFilteredProjection();
        }
        return result;
    }

    applyFilterToGrid() {
        this.ensureFilterAncestorsExpanded();
        this.rebuildFilterPassIds();
        if (this.api?.onFilterChanged) {
            this.api.onFilterChanged();
        }
        if (typeof this.clearCellSelection === "function") {
            this.clearCellSelection();
        }
    }

    emitFilterChange() {
        if (typeof this.options.onFilterChange === "function") {
            this.options.onFilterChange({
                filter: this.getFilter(),
                active: this.isFilterRowOpen(),
                table: this
            });
        }
    }

    refresh(data) {
        super.refresh(data);
        this.syncFloatingFilterInputs();
    }

    buildColumnDefs() {
        const defs = super.buildColumnDefs();
        if (!this.isFilterEnabled()) {
            return defs;
        }
        return this.applyFilterMetaToColumnDefs(defs);
    }

    applyFilterMetaToColumnDefs(columnDefs) {
        const rowOpen = this.isFilterRowOpen();
        return (columnDefs || []).map((col) => {
            if (Array.isArray(col.children) && col.children.length) {
                return {
                    ...col,
                    children: this.applyFilterMetaToColumnDefs(col.children)
                };
            }

            const field = col.field;
            const colId = col.colId;
            if (colId === ROW_CHECK_COL_ID || !field) {
                return {
                    ...col,
                    floatingFilter: false,
                    filter: false
                };
            }

            if (!this.isColumnFilterable(field)) {
                return {
                    ...col,
                    floatingFilter: false,
                    filter: false
                };
            }

            if (!rowOpen) {
                return {
                    ...col,
                    floatingFilter: false,
                    filter: false
                };
            }

            return {
                ...col,
                filter: DinextNoopFilter,
                floatingFilter: true,
                suppressHeaderFilterButton: true,
                suppressFloatingFilterButton: true,
                floatingFilterComponent: DinextTextFloatingFilter
            };
        });
    }

    syncFilterFloatingFilters() {
        if (!this.api || !this.isFilterEnabled()) {
            return;
        }
        this.setGridOption("columnDefs", this.buildColumnDefs());
        this.container?.classList.toggle("dinext-table--filter-row", this.isFilterRowOpen());
    }

    syncFloatingFilterInputs() {
        if (!this.api || !this.isFilterRowOpen()) {
            return;
        }
        this.api.refreshHeader?.();
    }

    buildFilterGridOptions() {
        if (!this.isFilterEnabled()) {
            return {};
        }
        return {
            floatingFiltersHeight: FLOATING_FILTER_ROW_HEIGHT,
            isExternalFilterPresent: () => this.isFilterActive(),
            doesExternalFilterPass: (node) => this.doesExternalFilterPass(node)
        };
    }

    handleSetOption(key, value) {
        if (key === "filter") {
            this.options.filter = value;
            const opts = this.getFilterOptions();
            this._filterState = normalizeFilterState(opts.state);
            this._filterRowOpen = !!opts.active;
            if (this.isFilterEnabled()) {
                this.syncFilterFloatingFilters();
                this.applyFilterToGrid();
            } else {
                this._filterState = {};
                this._filterRowOpen = false;
                this.syncFilterFloatingFilters();
                this.applyFilterToGrid();
            }
            this.refreshToolbar?.();
            return true;
        }
        return super.handleSetOption?.(key, value) ?? false;
    }
};
