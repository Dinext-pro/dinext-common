import {
    getChildrenField,
    getMergeGroupChildInsertOffset,
    getMergeGroupMeta,
    getRowIdField,
    getTreeSourceRowId
} from "../shared/utils.js";
import {
    collectExpandableRowIds,
    findRawColumnByField,
    findSourceRowInData,
    flattenExpandedChildren,
    resolveTreeColumnField,
    rowIsExpandable,
    toVisibleRows,
    treeHasExpandable
} from "./model.js";
import {
    clearExpandedDescendantIds,
    collapseTreeRow,
    expandTreeRow,
    resolveTreeChildAddIndex
} from "./expand.js";

const TREE_INDENT_PX = 20;

function mountCellContent(contentEl, params, renderFn) {
    contentEl.replaceChildren();
    if (renderFn) {
        const result = renderFn(params);
        if (result instanceof HTMLElement) {
            contentEl.appendChild(result);
            return;
        }
        if (result != null && result !== "") {
            contentEl.textContent = String(result);
            return;
        }
    }
    contentEl.textContent = String(params.value ?? "");
}

/**
 * When to remount tree cell body (not chevron).
 * Core: `_rowId` + column `value` only — no domain fields.
 * Domain extras: column `treeContentKey(params) => string` (e.g. dep flags).
 */
function treeContentStableKey(params, contentKeyFn) {
	const data = params?.data || {};
	const base = `${data._rowId ?? ""}\0${params?.value ?? ""}`;
	if (typeof contentKeyFn !== "function") {
		return base;
	}
	const extra = contentKeyFn(params);
	if (extra == null || extra === "") {
		return base;
	}
	return `${base}\0${extra}`;
}

function createTreeCellRenderer(renderFn, contentKeyFn) {
    return class TreeComposedCellRenderer {
        init(params) {
            this.params = params;
            this.contentKey = null;
            this.eGui = document.createElement("div");
            this.eGui.className = "dinext-table-tree-cell";
            this.leadEl = document.createElement("span");
            this.leadEl.className = "dinext-table-tree-lead";
            this.contentEl = document.createElement("span");
            this.contentEl.className = "dinext-table-tree-content";
            this.eGui.appendChild(this.leadEl);
            this.eGui.appendChild(this.contentEl);
            this.onChevronClick = (e) => {
                e.stopPropagation();
                const table = this.params?.context?.dinextTable;
                const rowId = this.params?.data?._rowId;
                if (table && rowId) {
                    table.toggleRow(rowId);
                }
            };
            this.render(params, { remountContent: true });
        }

        renderLead(params) {
            const table = params.context?.dinextTable;
            const data = params.data || {};
            this.leadEl.replaceChildren();

            if (data._hasChildren && table) {
                const toggle = document.createElement("span");
                toggle.className = "dinext-table-tree-toggle";
                const rowId = String(data._rowId);
                const expanded = table.isRowExpanded(rowId);
                const loading = !!data._treeLoading;
                toggle.classList.toggle("is-expanded", expanded && !loading);
                toggle.classList.toggle("is-collapsed", !expanded && !loading);
                toggle.classList.toggle("is-loading", loading);
                const chevron = document.createElement("span");
                chevron.className = "dinext-table-tree-chevron";
                toggle.appendChild(chevron);
                toggle.onclick = this.onChevronClick;
                this.leadEl.appendChild(toggle);
            }
            // Leaf / no children: leave lead empty. CSS :empty drops the slot so
            // content starts at the chevron X (no reserved gutter).
        }

        render(params, { remountContent } = { remountContent: true }) {
            this.params = params;
            const data = params.data || {};
            const table = params.context?.dinextTable;
            const level = data._level || 0;
            const mergeMeta = getMergeGroupMeta(data, table?.options);
            this.eGui.style.paddingLeft = `${level * TREE_INDENT_PX}px`;
            this.eGui.classList.toggle(
                "dinext-table-tree-cell--merge-group",
                !!(mergeMeta && mergeMeta.index === 0 && mergeMeta.size > 1)
            );
            this.renderLead(params);
            if (remountContent) {
                mountCellContent(this.contentEl, params, renderFn);
                this.contentKey = treeContentStableKey(params, contentKeyFn);
            }
        }

        refresh(params) {
            const nextKey = treeContentStableKey(params, contentKeyFn);
            this.render(params, { remountContent: nextKey !== this.contentKey });
            return true;
        }

        getGui() {
            return this.eGui;
        }
    };
}

export const TreeMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this.initTreeState();
    }

    buildColumnDefs() {
        if (!this.hasNestedRows() || !this.columns.length) {
            return super.buildColumnDefs();
        }
        return this.buildTreeColumnDefs();
    }

    initTreeState() {
        this.sourceData = this.options.data || [];
        this.expandedIds = new Set(
            (this.options.expandedIds || []).map(id => String(id))
        );
        this.syncVisibleRows();
    }

    getChildrenField() {
        return getChildrenField(this.options);
    }

    hasNestedRows() {
        return treeHasExpandable(this.sourceData, this.getChildrenField(), this.options);
    }

    syncVisibleRows() {
        if (!this.hasNestedRows()) {
            this.rowData = this.sourceData;
            return;
        }
        this.rowData = toVisibleRows(this.sourceData, this.expandedIds, this.options);
    }

    resolveProjectedSourceRowId(rowId, { includeLeaf = false } = {}) {
        const displayParts = String(rowId).split(":");
        const sourceParts = [...displayParts];
        const limit = includeLeaf ? displayParts.length : Math.max(displayParts.length - 1, 0);
        for (let index = 0; index < limit; index++) {
            const displayPath = displayParts.slice(0, index + 1).join(":");
            const visibleRow = (this.rowData || []).find(
                (row) => String(row?._rowId) === displayPath
            );
            const sourceLocalId = getTreeSourceRowId(visibleRow);
            if (sourceLocalId != null) {
                sourceParts[index] = sourceLocalId;
            }
        }
        return sourceParts.join(":");
    }

    findSourceRow(rowId) {
        const sourceRowId = this.resolveProjectedSourceRowId(rowId);
        return findSourceRowInData(this.sourceData, sourceRowId, this.options);
    }

    findTreeSourceRow(rowId) {
        const sourceRowId = this.resolveProjectedSourceRowId(rowId, { includeLeaf: true });
        return findSourceRowInData(this.sourceData, sourceRowId, this.options);
    }

    isRowExpanded(rowId) {
        return this.expandedIds.has(String(rowId));
    }

    getSourceChildren(rowId) {
        const row = this.findTreeSourceRow(rowId);
        if (!row) {
            return [];
        }
        return row[this.getChildrenField()] || [];
    }

    getRowLevel(rowId) {
        const node = this.api?.getRowNode(String(rowId));
        if (node?.data?._level !== undefined) {
            return node.data._level;
        }
        return String(rowId).split(":").length - 1;
    }

    syncRowDataFromGrid() {
        const rows = [];
        this.api?.forEachNode(node => {
            if (node.data) {
                rows.push(node.data);
            }
        });
        this.rowData = rows;
    }

    getTreeColumnField() {
        return resolveTreeColumnField(this.columns, this.options);
    }

    refreshTreeToggle(rowId) {
        const treeField = this.getTreeColumnField();
        const node = this.api?.getRowNode(String(rowId));
        if (!treeField || !node) return;
        this.api.refreshCells({ rowNodes: [node], columns: [treeField], force: true });
    }

    /** Force chevron/lead re-render (rowData replace alone may reuse cells without refresh). */
    refreshAllTreeToggles() {
        const treeField = this.getTreeColumnField();
        if (!treeField || !this.api) return;
        this.api.refreshCells({columns: [treeField], force: true });
    }

    setRowLoading(rowId, loading) {
        const node = this.api?.getRowNode(String(rowId));
        if (node?.data) node.data._treeLoading = loading;
        this.refreshTreeToggle(rowId);
    }

    setRowChildren(rowId, children) {
        rowId = String(rowId);
        const row = this.findTreeSourceRow(rowId);
        if (!row) return;
        
        const childrenField = this.getChildrenField();
        row[childrenField] = children;

        const node = this.api?.getRowNode(rowId);
        if (node?.data) {
            node.data._hasChildren = rowIsExpandable(row, childrenField, this.options);
        }

        if (this.expandedIds.has(rowId)) {
            this.removeVisibleDescendants(rowId);
            if (children?.length) {
                this.insertVisibleChildren(rowId);
            }
        }
        this.refreshTreeToggle(rowId);
    }

    insertVisibleChildren(rowId) {
        const parentRow = this.findTreeSourceRow(rowId);
        if (!parentRow) return;

        const parentLevel = this.getRowLevel(rowId);
        const childRows = flattenExpandedChildren(
            parentRow,
            rowId,
            parentLevel,
            this.expandedIds,
            this.options
        );
        if (!childRows.length) return;

        const parentNode = this.api?.getRowNode(rowId);
        const insertOffset = getMergeGroupChildInsertOffset(parentRow, this.options);
        const addIndex = resolveTreeChildAddIndex(parentNode, insertOffset);
        this.api.applyTransaction({ add: childRows, addIndex });
        this.syncRowDataFromGrid();
    }

    removeVisibleDescendants(rowId) {
        rowId = String(rowId);
        const prefix = `${rowId}:`;
        const toRemove = [];

        this.api?.forEachNode(node => {
            const id = String(node.data?._rowId || "");
            if (id.startsWith(prefix)) {
                toRemove.push(node.data);
            }
        });

        if (!toRemove.length) return;

        this.api.applyTransaction({ remove: toRemove });
        this.syncRowDataFromGrid();
    }

    clearExpandedDescendants(rowId) {
        clearExpandedDescendantIds(this.expandedIds, rowId);
    }

    applyTreeRendererToColumnDefs(columnDefs, treeField) {
        return columnDefs.map((col) => {
            if (Array.isArray(col.children) && col.children.length) {
                return {
                    ...col,
                    children: this.applyTreeRendererToColumnDefs(col.children, treeField)
                };
            }
            if (col.field !== treeField) {
                return col;
            }

            const rawCol = findRawColumnByField(this.columns, treeField);
            if (!rawCol || rawCol.tree === false) {
                return col;
            }
            if (rawCol.cellRenderer) {
                return { ...col, cellRenderer: rawCol.cellRenderer };
            }

            return {
                ...col,
                cellRenderer: createTreeCellRenderer(
                    rawCol.render,
                    rawCol.treeContentKey
                )
            };
        });
    }

    buildTreeColumnDefs() {
        const treeField = this.getTreeColumnField();
        const columnDefs = super.buildColumnDefs();
        if (!treeField) return columnDefs;

        return this.applyTreeRendererToColumnDefs(columnDefs, treeField);
    }

    buildTreeGridOptions() {
        const rowIdField = getRowIdField(this.options);

        return {
            getRowId: params => {
                const row = params.data;
                if (row._rowId !== undefined) {
                    return String(row._rowId);
                }
                return String(row[rowIdField]);
            }
        };
    }

    async expandRow(rowId) {
        return expandTreeRow(this, rowId, {
            expandedIds: this.expandedIds,
            getChildren: (id) => this.getSourceChildren(id),
            revealChildren: (id, { lazy }) => {
                if (!lazy) {
                    this.insertVisibleChildren(id);
                }
            }
        });
    }

    collapseRow(rowId) {
        collapseTreeRow(this, rowId, {
            expandedIds: this.expandedIds,
            clearDescendants: (id) => clearExpandedDescendantIds(this.expandedIds, id),
            hideDescendants: (id) => this.removeVisibleDescendants(id)
        });
    }

    toggleRow(rowId) {
        rowId = String(rowId);
        if (this.isRowExpanded(rowId)) {
            this.collapseRow(rowId);
        } else {
            this.expandRow(rowId);
        }
    }

    async expandAll() {
        if (!this.hasNestedRows()) return;
        
        const rowIds = collectExpandableRowIds(this.sourceData, this.options);
        for (const rowId of rowIds) {
            await this.expandRow(rowId);
        }
    }

    collapseAll() {
        if (!this.hasNestedRows()) return;
        
        this.expandedIds.clear();
        this.syncVisibleRows();
        if (this.api) {
            this.api.setGridOption("rowData", [...this.rowData]);
            // Parents stay in grid with same getRowId — without force refresh chevrons
            // keep is-expanded from before (toolbar Collapse all).
            this.refreshAllTreeToggles();
        }
    }
};
