import {
    findSourceRowInData,
    toVisibleRows,
    treeHasExpandable
} from "./tree.js";
import {
    getRowSection,
    isSummarySectionRow,
    stampSummaryRows,
    TABLE_SECTIONS
} from "./sections.js";

const SUMMARY_DEFAULTS = {
    pin: "bottom",
    clipboard: false,
    selection: false,
    edit: true,
    expandedIds: []
};

function getRowIdField(options) {
    return options.rowIdField || "id";
}

export const SectionMixin = (Base) => class extends Base {
    initSectionState() {
        this.summarySourceData = this.options.summaryRows || [];
        this.summaryExpandedIds = new Set(
            (this.getSummaryOptions().expandedIds || []).map((id) => String(id))
        );
    }

    initFeatures() {
        this.initSectionState();
        super.initFeatures();
    }

    afterGridCreated() {
        super.afterGridCreated();
        this.syncSummarySection();
    }

    getSummaryOptions() {
        return { ...SUMMARY_DEFAULTS, ...(this.options.summary || {}) };
    }

    syncVisibleRows() {
        super.syncVisibleRows();
        this.syncSummarySection();
    }

    syncSummarySection() {
        this.summarySourceData = this.options.summaryRows || [];
        const rows = this.summarySourceData;

        if (!rows.length) {
            this.summaryRowData = [];
            if (this.api) {
                this.setGridOption("pinnedBottomRowData", []);
            }
            return;
        }

        const childrenField = this.getChildrenField();
        let visible;

        if (treeHasExpandable(rows, childrenField, this.options)) {
            visible = toVisibleRows(rows, this.summaryExpandedIds ?? new Set(), this.options);
        } else {
            const rowIdField = getRowIdField(this.options);
            visible = rows.map((row) => ({
                ...row,
                _rowId: String(row[rowIdField])
            }));
        }

        this.summaryRowData = stampSummaryRows(visible);

        const pin = this.getSummaryOptions().pin;
        if (pin === "bottom" || pin === true) {
            this.setGridOption("pinnedBottomRowData", this.summaryRowData);
        } else {
            this.setGridOption("pinnedBottomRowData", []);
        }
    }

    findSourceRow(rowId) {
        const bodyRow = super.findSourceRow(rowId);
        if (bodyRow) {
            return bodyRow;
        }
        return findSourceRowInData(this.summarySourceData, rowId, this.options);
    }

    isSummarySectionRowId(rowId) {
        rowId = String(rowId);
        if (findSourceRowInData(this.sourceData, rowId, this.options)) {
            return false;
        }
        return !!findSourceRowInData(this.summarySourceData, rowId, this.options);
    }

    hasNestedRows() {
        return super.hasNestedRows()
            || treeHasExpandable(this.summarySourceData, this.getChildrenField(), this.options);
    }

    getSummarySourceChildren(rowId) {
        const row = findSourceRowInData(this.summarySourceData, rowId, this.options);
        if (!row) {
            return [];
        }
        return row[this.getChildrenField()] || [];
    }

    clearSummaryExpandedDescendants(rowId) {
        rowId = String(rowId);
        const prefix = `${rowId}:`;
        for (const id of [...this.summaryExpandedIds]) {
            if (id.startsWith(prefix)) {
                this.summaryExpandedIds.delete(id);
            }
        }
    }

    isRowExpanded(rowId) {
        rowId = String(rowId);
        if (this.isSummarySectionRowId(rowId)) {
            return this.summaryExpandedIds.has(rowId);
        }
        return super.isRowExpanded(rowId);
    }

    async expandSummaryRow(rowId) {
        rowId = String(rowId);
        if (this.summaryExpandedIds.has(rowId)) {
            return;
        }

        const eagerChildren = this.getSummarySourceChildren(rowId);
        const needsLazyLoad = !eagerChildren.length
            && typeof this.options.onExpandRow === "function";

        if (!eagerChildren.length && !needsLazyLoad) {
            return;
        }

        this.summaryExpandedIds.add(rowId);

        if (needsLazyLoad) {
            this.setRowLoading(rowId, true);
            try {
                await this.options.onExpandRow({
                    rowId,
                    row: this.findSourceRow(rowId),
                    table: this,
                    section: TABLE_SECTIONS.SUMMARY
                });
            } finally {
                this.setRowLoading(rowId, false);
            }
            if (!this.getSummarySourceChildren(rowId).length) {
                this.summaryExpandedIds.delete(rowId);
            }
            this.syncSummarySection();
            this.refreshTreeToggle(rowId);
            return;
        }

        this.syncSummarySection();
        this.refreshTreeToggle(rowId);
    }

    async expandRow(rowId) {
        if (this.isSummarySectionRowId(rowId)) {
            return this.expandSummaryRow(rowId);
        }
        return super.expandRow(rowId);
    }

    collapseRow(rowId) {
        rowId = String(rowId);
        if (this.isSummarySectionRowId(rowId)) {
            if (!this.summaryExpandedIds.has(rowId)) {
                return;
            }
            this.summaryExpandedIds.delete(rowId);
            this.clearSummaryExpandedDescendants(rowId);
            this.syncSummarySection();
            this.refreshTreeToggle(rowId);
            return;
        }
        super.collapseRow(rowId);
    }

    insertVisibleChildren(rowId) {
        if (this.isSummarySectionRowId(rowId)) {
            this.syncSummarySection();
            return;
        }
        super.insertVisibleChildren(rowId);
    }

    removeVisibleDescendants(rowId) {
        if (this.isSummarySectionRowId(rowId)) {
            this.syncSummarySection();
            return;
        }
        super.removeVisibleDescendants(rowId);
    }

    setRowChildren(rowId, children) {
        rowId = String(rowId);
        if (this.isSummarySectionRowId(rowId)) {
            const row = findSourceRowInData(this.summarySourceData, rowId, this.options);
            if (!row) {
                return;
            }
            row[this.getChildrenField()] = children;
            if (this.summaryExpandedIds.has(rowId)) {
                this.syncSummarySection();
            }
            this.refreshTreeToggle(rowId);
            return;
        }
        super.setRowChildren(rowId, children);
    }

    refresh(data) {
        super.refresh(data);
        this.syncSummarySection();
    }

    setSummaryRows(rows) {
        this.options.summaryRows = rows || [];
        this.syncSummarySection();
    }

    handleSetOption(key, value) {
        if (key === "summaryRows") {
            this.setSummaryRows(value);
            return true;
        }
        if (typeof super.handleSetOption === "function" && super.handleSetOption(key, value)) {
            return true;
        }
        return false;
    }

    shouldApplyClipboardToRow(rowNode) {
        if (!rowNode?.data) {
            return false;
        }
        if (isSummarySectionRow(rowNode.data)) {
            return !!this.getSummaryOptions().clipboard;
        }
        return true;
    }

    shouldApplySelectionToRow(rowNode) {
        if (!rowNode?.data) {
            return false;
        }
        if (isSummarySectionRow(rowNode.data)) {
            return !!this.getSummaryOptions().selection;
        }
        return true;
    }

    isColumnEditableForRow(column, rowNode) {
        const editable = super.isColumnEditableForRow(column, rowNode);
        if (!editable) {
            return false;
        }
        if (isSummarySectionRow(rowNode?.data) && this.getSummaryOptions().edit === false) {
            return false;
        }
        return true;
    }

    buildSectionGridOptions() {
        if (!this.summarySourceData?.length) {
            return {};
        }

        const userGetRowClass = this.options.gridOptions?.getRowClass;

        return {
            getRowClass: (params) => {
                const classes = [];
                if (isSummarySectionRow(params.data)) {
                    classes.push("dinext-table-row--summary");
                }
                if (typeof userGetRowClass === "function") {
                    const userClass = userGetRowClass(params);
                    if (userClass) {
                        classes.push(...(Array.isArray(userClass) ? userClass : [userClass]));
                    }
                }
                return classes.length ? classes : undefined;
            }
        };
    }
};

export { TABLE_SECTIONS, getRowSection, isSummarySectionRow };
