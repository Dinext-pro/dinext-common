const DEFAULT_CHILDREN_FIELD = "children";
const DEFAULT_ROW_ID_FIELD = "id";
const TREE_INDENT_PX = 20;

function getChildrenField(options) {
    return options.childrenField || DEFAULT_CHILDREN_FIELD;
}

function getRowIdField(options) {
    return options.rowIdField || DEFAULT_ROW_ID_FIELD;
}

function rowHasChildren(row, childrenField) {
    const children = row?.[childrenField];
    return Array.isArray(children) && children.length > 0;
}

/** Eager children or lazy marker `hasChildren: true`. */
export function rowIsExpandable(row, childrenField) {
    if (row?.hasChildren === true) {
        return true;
    }
    return rowHasChildren(row, childrenField);
}

function treeHasExpandable(rows, childrenField) {
    if (!Array.isArray(rows)) {
        return false;
    }
    for (const row of rows) {
        if (rowIsExpandable(row, childrenField)) {
            return true;
        }
        const children = row[childrenField];
        if (Array.isArray(children) && children.length && treeHasExpandable(children, childrenField)) {
            return true;
        }
    }
    return false;
}

function makeVisibleRow(row, rowId, level, parentRowId, childrenField) {
    const expandable = rowIsExpandable(row, childrenField);
    return {
        ...row,
        _rowId: rowId,
        _level: level,
        _hasChildren: expandable,
        _parentRowId: parentRowId || undefined
    };
}

function flattenExpandedChildren(parentRow, parentRowId, parentLevel, expandedIds, options) {
    const childrenField = getChildrenField(options);
    const rowIdField = getRowIdField(options);
    const rows = [];

    for (const child of parentRow[childrenField] || []) {
        const childLocalId = String(child[rowIdField]);
        const childRowId = `${parentRowId}:${childLocalId}`;
        const childLevel = parentLevel + 1;
        const visibleChild = makeVisibleRow(child, childRowId, childLevel, parentRowId, childrenField);
        rows.push(visibleChild);

        if (visibleChild._hasChildren && expandedIds.has(childRowId)) {
            rows.push(...flattenExpandedChildren(child, childRowId, childLevel, expandedIds, options));
        }
    }

    return rows;
}

function walkVisibleRow(row, rowId, level, parentRowId, visible, expandedIds, options) {
    const childrenField = getChildrenField(options);
    visible.push(makeVisibleRow(row, rowId, level, parentRowId, childrenField));

    if (!rowIsExpandable(row, childrenField) || !expandedIds.has(rowId)) {
        return;
    }

    visible.push(...flattenExpandedChildren(row, rowId, level, expandedIds, options));
}

export function toVisibleRows(sourceRows, expandedIds, options = {}) {
    const rowIdField = getRowIdField(options);
    const visible = [];

    for (const row of sourceRows) {
        walkVisibleRow(
            row,
            String(row[rowIdField]),
            0,
            null,
            visible,
            expandedIds,
            options
        );
    }

    return visible;
}

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

function createTreeCellRenderer(renderFn) {
    return class TreeComposedCellRenderer {
        init(params) {
            this.params = params;
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
            this.render(params);
        }

        renderLead(params) {
            const table = params.context?.dinextTable;
            const data = params.data || {};
            this.leadEl.replaceChildren();

            if (data._hasChildren && table) {
                const toggle = document.createElement("span");
                toggle.className = "dinext-table-tree-toggle";
                const rowId = String(data._rowId);
                const expanded = table.expandedIds.has(rowId);
                const loading = !!data._treeLoading;
                toggle.classList.toggle("is-expanded", expanded && !loading);
                toggle.classList.toggle("is-collapsed", !expanded && !loading);
                toggle.classList.toggle("is-loading", loading);
                const chevron = document.createElement("span");
                chevron.className = "dinext-table-tree-chevron";
                toggle.appendChild(chevron);
                toggle.onclick = this.onChevronClick;
                this.leadEl.appendChild(toggle);
                return;
            }

            const spacer = document.createElement("span");
            spacer.className = "dinext-table-tree-spacer";
            spacer.setAttribute("aria-hidden", "true");
            this.leadEl.appendChild(spacer);
        }

        render(params) {
            this.params = params;
            const data = params.data || {};
            const level = data._level || 0;
            this.eGui.style.paddingLeft = `${level * TREE_INDENT_PX}px`;
            this.renderLead(params);
            mountCellContent(this.contentEl, params, renderFn);
        }

        refresh(params) {
            this.render(params);
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
        return treeHasExpandable(this.sourceData, this.getChildrenField());
    }

    syncVisibleRows() {
        if (!this.hasNestedRows()) {
            this.rowData = this.sourceData;
            return;
        }
        this.rowData = toVisibleRows(this.sourceData, this.expandedIds, this.options);
    }

    findSourceRow(rowId) {
        rowId = String(rowId);
        const parts = rowId.split(":");
        const rowIdField = getRowIdField(this.options);
        const childrenField = this.getChildrenField();

        let rows = this.sourceData;
        let row = null;

        for (let i = 0; i < parts.length; i++) {
            row = rows.find(item => String(item[rowIdField]) === parts[i]);
            if (!row) {
                return null;
            }
            if (i < parts.length - 1) {
                rows = row[childrenField] || [];
            }
        }

        return row;
    }

    getSourceChildren(rowId) {
        const row = this.findSourceRow(rowId);
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

    refreshTreeToggle(rowId) {
        const node = this.api?.getRowNode(String(rowId));
        if (!node) {
            return;
        }
        const firstCol = this.api.getAllDisplayedColumns()[0];
        if (!firstCol) {
            return;
        }
        this.api.refreshCells({
            rowNodes: [node],
            columns: [firstCol.getColId()],
            force: true
        });
    }

    setRowLoading(rowId, loading) {
        const node = this.api?.getRowNode(String(rowId));
        if (node?.data) {
            node.data._treeLoading = loading;
        }
        this.refreshTreeToggle(rowId);
    }

    setRowChildren(rowId, children) {
        rowId = String(rowId);
        const row = this.findSourceRow(rowId);
        if (!row) {
            return;
        }
        const childrenField = this.getChildrenField();
        row[childrenField] = children;

        const node = this.api?.getRowNode(rowId);
        if (node?.data) {
            node.data._hasChildren = rowIsExpandable(row, childrenField);
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
        const parentRow = this.findSourceRow(rowId);
        if (!parentRow) {
            return;
        }

        const parentLevel = this.getRowLevel(rowId);
        const childRows = flattenExpandedChildren(
            parentRow,
            rowId,
            parentLevel,
            this.expandedIds,
            this.options
        );
        if (!childRows.length) {
            return;
        }

        const parentNode = this.api?.getRowNode(rowId);
        const addIndex = parentNode ? parentNode.rowIndex + 1 : undefined;
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

        if (!toRemove.length) {
            return;
        }

        this.api.applyTransaction({ remove: toRemove });
        this.syncRowDataFromGrid();
    }

    clearExpandedDescendants(rowId) {
        rowId = String(rowId);
        const prefix = `${rowId}:`;
        for (const id of [...this.expandedIds]) {
            if (id.startsWith(prefix)) {
                this.expandedIds.delete(id);
            }
        }
    }

    buildTreeColumnDefs() {
        const columnDefs = super.buildColumnDefs();
        return columnDefs.map((col, index) => {
            if (index !== 0) {
                return col;
            }

            const rawCol = this.columns[index] || {};
            if (rawCol.tree === false) {
                return col;
            }
            if (rawCol.cellRenderer) {
                return { ...col, cellRenderer: rawCol.cellRenderer };
            }

            return {
                ...col,
                cellRenderer: createTreeCellRenderer(rawCol.render)
            };
        });
    }

    buildTreeGridOptions() {
        if (!this.hasNestedRows()) {
            return {};
        }

        return {
            getRowId: params => String(params.data._rowId)
        };
    }

    async expandRow(rowId) {
        rowId = String(rowId);
        if (this.expandedIds.has(rowId)) {
            return;
        }

        const eagerChildren = this.getSourceChildren(rowId);
        const needsLazyLoad = !eagerChildren.length
            && typeof this.options.onExpandRow === "function";

        if (!eagerChildren.length && !needsLazyLoad) {
            return;
        }

        this.expandedIds.add(rowId);

        if (needsLazyLoad) {
            this.setRowLoading(rowId, true);
            try {
                await this.options.onExpandRow({
                    rowId,
                    row: this.findSourceRow(rowId),
                    table: this
                });
            } finally {
                this.setRowLoading(rowId, false);
            }
            if (!this.getSourceChildren(rowId).length) {
                this.expandedIds.delete(rowId);
            }
            this.refreshTreeToggle(rowId);
            return;
        }

        this.insertVisibleChildren(rowId);
        this.refreshTreeToggle(rowId);
    }

    collapseRow(rowId) {
        rowId = String(rowId);
        if (!this.expandedIds.has(rowId)) {
            return;
        }
        this.expandedIds.delete(rowId);
        this.clearExpandedDescendants(rowId);
        this.removeVisibleDescendants(rowId);
        this.refreshTreeToggle(rowId);
    }

    toggleRow(rowId) {
        rowId = String(rowId);
        if (this.expandedIds.has(rowId)) {
            this.collapseRow(rowId);
        } else {
            this.expandRow(rowId);
        }
    }
};
