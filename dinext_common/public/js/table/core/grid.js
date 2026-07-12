import { mergeGridOptions } from "./shared/utils.js";

export const GridMixin = (Base) => class extends Base {
    getFeatureGridOptionParts() {
        return [
            this.buildTreeGridOptions?.(),
            this.buildSectionGridOptions?.(),
            this.buildEditGridOptions?.(),
            this.buildEditorsGridOptions?.(),
            this.buildNavigationGridOptions?.(),
            this.buildSelectionGridOptions?.(),
            this.buildClipboardGridOptions?.(),
            this.buildFillHandleGridOptions?.(),
            this.buildRowReorderGridOptions?.()
        ].filter(part => part && Object.keys(part).length);
    }

    buildGridOptions() {
        const userGridOptions = this.options.gridOptions || {};
        const userDefaultColDef = this.options.defaultColDef || {};
        const { columnTypes: userColumnTypes, ...restUserGridOptions } = userGridOptions;

        return mergeGridOptions(
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
