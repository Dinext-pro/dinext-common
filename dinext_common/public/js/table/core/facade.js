import { DinextTable } from "./base.js";
import { createMergeGroupSpanRows } from "./shared/utils.js";
import { CELL_CHANGE_SOURCES } from "./edit/changes.js";
import { ROW_REORDER_SOURCES } from "./row-reorder/constants.js";

const ASSETS = [
    "/assets/dinext_common/css/dinext-table.css",
    "/assets/dinext_common/js/ag-grid-community.min.js"
];

let loadPromise = null;

function loadAgGrid() {
    loadPromise ??= frappe.require(ASSETS).then(() => {
        if (!window.agGrid?.createGrid) {
            throw new Error("AG Grid failed to load");
        }
        return window.agGrid;
    });
    return loadPromise;
}

DinextTable.VERSION = "35.2.1";
DinextTable.load = loadAgGrid;
DinextTable.createMergeGroupSpanRows = createMergeGroupSpanRows;
DinextTable.CELL_CHANGE_SOURCES = CELL_CHANGE_SOURCES;
DinextTable.ROW_REORDER_SOURCES = ROW_REORDER_SOURCES;
DinextTable.create = async function(options) {
    await loadAgGrid();
    if (!options?.container) {
        throw new Error("DinextTable.create: container is required");
    }
    return new DinextTable(options.container, options);
};

window.DinextTable = DinextTable;

export { DinextTable };
