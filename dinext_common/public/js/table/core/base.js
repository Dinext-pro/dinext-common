import { composeMixins, normalizeColumns } from "./utils.js";
import { ThemeMixin } from "./theme.js";
import { TreeMixin } from "./tree.js";
import { EditMixin } from "./edit.js";
import { EditorsMixin } from "./editors.js";
import { NavigationMixin } from "./navigation.js";
import { SectionMixin } from "./section.js";
import { SelectionMixin } from "./selection.js";
import { ClipboardMixin } from "./clipboard.js";
import { FillHandleMixin } from "./fill-handle.js";
import { GridMixin } from "./grid.js";

const SET_OPTION_HANDLERS = {
    data(table, value) {
        table.refresh(value);
    },
    columns(table, value) {
        table.applyColumns(value);
    },
    edit(table) {
        table.setGridOption("columnDefs", table.buildColumnDefs());
    }
};

class DinextTableCore {
    constructor(container, options = {}) {
        this.container = container;
        this.options = options || {};
        this.columns = this.options.columns || [];
        this.sourceData = [];
        this.rowData = [];
        this.api = null;

        this.initFeatures();
        this.api = window.agGrid.createGrid(this.container, this.buildGridOptions());
        this.afterGridCreated();
    }

    initFeatures() {}

    afterGridCreated() {}

    destroyFeatures() {}

    buildColumnDefs() {
        return normalizeColumns(this.columns, this.options.edit);
    }

    syncVisibleRows() {
        this.rowData = this.sourceData ?? this.options.data ?? [];
    }

    refresh(data) {
        if (data !== undefined) {
            this.sourceData = data;
            this.options.data = data;
        }
        this.syncVisibleRows();
        this.setGridOption("rowData", this.rowData);
    }

    applyColumns(columns) {
        this.columns = columns;
        this.setGridOption("columnDefs", this.buildColumnDefs());
    }

    setOption(key, value) {
        this.options[key] = value;

        const handler = SET_OPTION_HANDLERS[key];
        if (handler) {
            handler(this, value);
            return;
        }

        if (typeof this.handleSetOption === "function" && this.handleSetOption(key, value)) {
            return;
        }
    }

    setGridOption(key, value) {
        this.api?.setGridOption(key, value);
    }

    shouldApplyClipboardToRow(rowNode) {
        return !!rowNode?.data;
    }

    shouldApplySelectionToRow(rowNode) {
        return !!rowNode?.data;
    }

    destroy() {
        this.destroyFeatures();
        this.api?.destroy();
        this.api = null;
        this.container.innerHTML = "";
    }
}

class DinextTable extends composeMixins(
    ThemeMixin,
    TreeMixin,
    EditMixin,
    EditorsMixin,
    NavigationMixin,
    SectionMixin,
    SelectionMixin,
    ClipboardMixin,
    FillHandleMixin,
    GridMixin
)(DinextTableCore) {}

export { DinextTable };
