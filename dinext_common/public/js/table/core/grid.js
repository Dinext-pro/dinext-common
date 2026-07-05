import { mergeGridOptions } from "./utils.js";

const FEATURE_GRID_OPTION_BUILDERS = [
    "buildTreeGridOptions"
];

export const GridMixin = (Base) => class extends Base {
    getFeatureGridOptionParts() {
        return FEATURE_GRID_OPTION_BUILDERS
            .map(name => (typeof this[name] === "function" ? this[name]() : null))
            .filter(part => part && Object.keys(part).length);
    }

    buildGridOptions() {
        const userGridOptions = this.options.gridOptions || {};
        const userDefaultColDef = this.options.defaultColDef || {};

        return mergeGridOptions(
            userGridOptions,
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
            }
        );
    }
};
