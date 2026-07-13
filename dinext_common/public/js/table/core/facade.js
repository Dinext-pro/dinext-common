import { DinextTable } from "./base.js";
import { createMergeGroupSpanRows } from "./shared/utils.js";
import { CELL_CHANGE_SOURCES } from "./edit/changes.js";
import { ROW_REORDER_SOURCES } from "./row-reorder/constants.js";

const ASSETS = [
    "/assets/dinext_common/css/dinext-table.css",
    "/assets/dinext_common/js/ag-grid-community.min.js"
];

/** Legacy class-theme stylesheets — poison Theming API when enabled. */
const LEGACY_AG_GRID_CSS_MARKERS = [
    "/assets/dinext_common/css/ag-grid.css",
    "/assets/dinext_common/css/ag-theme-quartz.css"
];

let loadPromise = null;

function setLegacyAgGridCssEnabled(enabled) {
    document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
        const href = link.getAttribute("href") || "";
        if (LEGACY_AG_GRID_CSS_MARKERS.some((marker) => href.includes(marker))) {
            link.disabled = !enabled;
        }
    });
}

function loadAgGrid() {
    loadPromise ??= frappe.require(ASSETS).then(() => {
        if (!window.agGrid?.createGrid) {
            throw new Error("AG Grid failed to load");
        }
        // DinextTable = Theming API. Keep legacy class-theme CSS off this page.
        setLegacyAgGridCssEnabled(false);
        return window.agGrid;
    });
    return loadPromise;
}

DinextTable.VERSION = "35.2.1";
DinextTable.load = loadAgGrid;
DinextTable.createMergeGroupSpanRows = createMergeGroupSpanRows;
DinextTable.CELL_CHANGE_SOURCES = CELL_CHANGE_SOURCES;
DinextTable.ROW_REORDER_SOURCES = ROW_REORDER_SOURCES;
DinextTable.setLegacyAgGridCssEnabled = setLegacyAgGridCssEnabled;
DinextTable.create = async function(options) {
    await loadAgGrid();
    if (!options?.container) {
        throw new Error("DinextTable.create: container is required");
    }
    setLegacyAgGridCssEnabled(false);
    return new DinextTable(options.container, options);
};

window.DinextTable = DinextTable;

export { DinextTable };
