import { cssEscapeAttr, mergeGridOptions } from "./shared/utils.js";

/** Default body row height when consumer omits gridOptions.rowHeight (~AG quartz +5px). */
export const DEFAULT_ROW_HEIGHT = 47;

export const GridMixin = (Base) => class extends Base {
    afterGridCreated() {
        super.afterGridCreated();
        this.ensureHeaderHoverStyle();
    }

    destroyFeatures() {
        this.clearHeaderHoverCol();
        this._headerHoverStyleEl?.remove();
        this._headerHoverStyleEl = null;
        super.destroyFeatures();
    }

    getFeatureGridOptionParts() {
        return [
            this.buildTreeGridOptions?.(),
            this.buildSortGridOptions?.(),
            this.buildFilterGridOptions?.(),
            this.buildSectionGridOptions?.(),
            this.buildEditGridOptions?.(),
            this.buildEditorsGridOptions?.(),
            this.buildNavigationGridOptions?.(),
            this.buildSelectionGridOptions?.(),
            this.buildClipboardGridOptions?.(),
            this.buildFillHandleGridOptions?.(),
            this.buildRowReorderGridOptions?.(),
            this.buildRowCheckGridOptions?.(),
            this.buildPinEndGridOptions?.(),
            this.buildColumnWidthGridOptions?.(),
            this.buildScrollGridOptions?.(),
            this.buildLayoutGridOptions?.(),
            this.buildChromeGridOptions()
        ].filter(part => part && Object.keys(part).length);
    }

    buildChromeGridOptions() {
        return {
            onColumnHeaderMouseOver: (event) => this.handleColumnHeaderMouseOver(event),
            onColumnHeaderMouseLeave: () => this.clearHeaderHoverCol()
        };
    }

    ensureHeaderHoverStyle() {
        if (this._headerHoverStyleEl || !this.container) {
            return;
        }
        const style = document.createElement("style");
        this.container.appendChild(style);
        this._headerHoverStyleEl = style;
    }

    handleColumnHeaderMouseOver(event) {
        const col = event?.column;
        if (!col || typeof col.getColId !== "function") {
            return;
        }
        if (event?.headerRowIndex > 0) {
            return;
        }
        const target = event?.event?.target;
        if (target?.closest?.(".ag-floating-filter, .ag-header-cell-resize")) {
            return;
        }
        this.setHeaderHoverCol(col.getColId());
    }

    setHeaderHoverCol(colId) {
        if (!this.container) {
            return;
        }
        const next = colId == null || colId === "" ? null : String(colId);
        if (this._headerHoverColId === next) {
            return;
        }
        this._headerHoverColId = next;
        this.ensureHeaderHoverStyle();
        if (!next) {
            this.container.removeAttribute("data-dinext-hover-col");
            if (this._headerHoverStyleEl) {
                this._headerHoverStyleEl.textContent = "";
            }
            return;
        }
        const escaped = cssEscapeAttr(next);
        this.container.setAttribute("data-dinext-hover-col", next);
        if (this._headerHoverStyleEl) {
            this._headerHoverStyleEl.textContent = [
                `.dinext-table[data-dinext-hover-col="${escaped}"] .ag-header-row:not(.ag-header-row-column-filter) .ag-header-cell[col-id="${escaped}"] {`,
                "    background-color: var(--dinext-table-col-hover-bg);",
                "}"
            ].join("\n");
        }
    }

    clearHeaderHoverCol() {
        this.setHeaderHoverCol(null);
    }

    buildGridOptions() {
        const userGridOptions = this.options.gridOptions || {};
        const userDefaultColDef = this.options.defaultColDef || {};
        const { columnTypes: userColumnTypes, ...restUserGridOptions } = userGridOptions;

        return mergeGridOptions(
            { rowHeight: DEFAULT_ROW_HEIGHT },
            restUserGridOptions,
            ...this.getFeatureGridOptionParts(),
            {
                theme: this.buildAgGridTheme(),
                rowData: this.rowData,
                columnDefs: this.buildColumnDefs(),
                context: { dinextTable: this },
                defaultColDef: mergeGridOptions(
                    {
                        resizable: true,
                        sortable: false
                    },
                    userGridOptions.defaultColDef || {},
                    userDefaultColDef
                ),
                onGridReady: () => {
                    if (typeof this.options.onReady === "function") {
                        this.options.onReady(this);
                    }
                },
                onCellDoubleClicked: params => {
                    if (typeof this.options.onCellDoubleClicked === "function") {
                        this.options.onCellDoubleClicked(params, this);
                    }
                }
            },
            userColumnTypes ? { columnTypes: userColumnTypes } : {}
        );
    }
};
