import { matchKeyboardShortcut } from "./utils.js";
import { CELL_CHANGE_SOURCES } from "./edit-changes.js";

const CLIPBOARD_DEFAULTS = {
    enabled: undefined
};

const COMMAND_STACK_LIMIT = 20;

function escapeTsvCell(value) {
    const str = value == null ? "" : String(value);
    if (/[\t\n\r"]/.test(str)) {
        return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
}

/** Minimal TSV parser with quoted-field support (Community-only, no AG Grid clipboard module). */
function parseTsv(text) {
    const rows = [];
    let row = [];
    let cell = "";
    let inQuotes = false;

    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (inQuotes) {
            if (ch === '"') {
                if (text[i + 1] === '"') {
                    cell += '"';
                    i += 1;
                } else {
                    inQuotes = false;
                }
            } else {
                cell += ch;
            }
            continue;
        }
        if (ch === '"') {
            inQuotes = true;
        } else if (ch === "\t") {
            row.push(cell);
            cell = "";
        } else if (ch === "\n" || ch === "\r") {
            if (ch === "\r" && text[i + 1] === "\n") {
                i += 1;
            }
            row.push(cell);
            rows.push(row);
            row = [];
            cell = "";
        } else {
            cell += ch;
        }
    }

    row.push(cell);
    if (row.length > 1 || row[0] !== "" || rows.length) {
        rows.push(row);
    }
    return dropTrailingPhantomRow(rows, text);
}

/** Excel trailing \\r\\n after copy yields an extra [""] row — drop it only then. */
function dropTrailingPhantomRow(rows, sourceText) {
    if (rows.length <= 1) {
        return rows;
    }
    if (!/(?:\r\n|\n|\r)$/.test(sourceText)) {
        return rows;
    }
    const last = rows[rows.length - 1];
    if (last.length === 1 && last[0] === "") {
        rows.pop();
    }
    return rows;
}

async function writeClipboardText(text) {
    if (navigator.clipboard?.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (_err) {
            // fall through to execCommand
        }
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    let ok = false;
    try {
        ok = document.execCommand("copy");
    } finally {
        document.body.removeChild(textarea);
    }
    return ok;
}

async function readClipboardText() {
    if (!navigator.clipboard?.readText) {
        return null;
    }
    try {
        return await navigator.clipboard.readText();
    } catch (_err) {
        return null;
    }
}

function createCommandStack(limit) {
    const undoStack = [];
    const redoStack = [];

    return {
        push(command) {
            undoStack.push(command);
            if (undoStack.length > limit) {
                undoStack.shift();
            }
            redoStack.length = 0;
        },
        undo() {
            const command = undoStack.pop();
            if (!command) {
                return false;
            }
            command.undo();
            redoStack.push(command);
            return true;
        },
        redo() {
            const command = redoStack.pop();
            if (!command) {
                return false;
            }
            command.execute();
            undoStack.push(command);
            return true;
        },
        clear() {
            undoStack.length = 0;
            redoStack.length = 0;
        }
    };
}

/**
 * Custom TSV clipboard for AG Grid Community (no Enterprise clipboard module).
 * Scalar cells only; mutations go through EditMixin.commitCellChanges.
 * Fill handle drag — FillHandleMixin (uses fillRange).
 */
export const ClipboardMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._clipboardCommandStack = createCommandStack(COMMAND_STACK_LIMIT);
    }

    destroyFeatures() {
        this._clipboardCommandStack?.clear();
        this._clipboardCommandStack = null;
        super.destroyFeatures();
    }

    getClipboardOptions() {
        return { ...CLIPBOARD_DEFAULTS, ...(this.options.clipboard || {}) };
    }

    /** Default: enabled when selection.enabled (explicit clipboard.enabled always wins). */
    isClipboardEnabled() {
        const enabled = this.getClipboardOptions().enabled;
        if (enabled !== undefined) {
            return !!enabled;
        }
        return this.isSelectionEnabled();
    }

    getCellDisplayValue(rowNode, column) {
        const colDef = column.getColDef();
        const field = colDef.field;
        if (!field || !rowNode?.data) {
            return "";
        }

        if (typeof this.api?.getValue === "function") {
            const formatted = this.api.getValue(column, rowNode);
            if (formatted != null && formatted !== "") {
                return formatted;
            }
        }

        const raw = rowNode.data[field];
        if (typeof colDef.valueFormatter === "function") {
            return colDef.valueFormatter({
                value: raw,
                data: rowNode.data,
                node: rowNode,
                colDef,
                column,
                api: this.api,
                context: this.api?.getGridOption?.("context")
            });
        }
        return raw == null ? "" : raw;
    }

    parsePastedValue(colDef, column, rowNode, text) {
        if (text === "") {
            return null;
        }
        if (typeof colDef.valueParser === "function") {
            return colDef.valueParser({
                newValue: text,
                oldValue: rowNode.data[colDef.field],
                data: rowNode.data,
                node: rowNode,
                colDef,
                column,
                api: this.api,
                context: this.api?.getGridOption?.("context")
            });
        }
        return text;
    }

    /** Union bounding box of all ranges, or 1×1 around focusedCell. */
    getClipboardTargetBounds() {
        if (!this.api) {
            return null;
        }

        const columns = this.api.getAllDisplayedColumns();
        if (!columns.length) {
            return null;
        }

        if (this.cellRanges?.length) {
            let minRowIndex = Infinity;
            let maxRowIndex = -Infinity;
            let minColIndex = Infinity;
            let maxColIndex = -Infinity;

            for (const range of this.cellRanges) {
                const bounds = this.buildRangeBounds(range, columns);
                if (!bounds) {
                    continue;
                }
                minRowIndex = Math.min(minRowIndex, bounds.minRowIndex);
                maxRowIndex = Math.max(maxRowIndex, bounds.maxRowIndex);
                minColIndex = Math.min(minColIndex, bounds.minColIndex);
                maxColIndex = Math.max(maxColIndex, bounds.maxColIndex);
            }

            if (minRowIndex === Infinity) {
                return null;
            }
            return { minRowIndex, maxRowIndex, minColIndex, maxColIndex };
        }

        if (this.focusedCell) {
            const rowIndex = this.getRowIndexForId(this.focusedCell.rowId);
            const colIndex = this.getColumnIndexById(this.focusedCell.colId, columns);
            if (rowIndex == null || colIndex === -1) {
                return null;
            }
            return {
                minRowIndex: rowIndex,
                maxRowIndex: rowIndex,
                minColIndex: colIndex,
                maxColIndex: colIndex
            };
        }

        return null;
    }

    isCellInClipboardRange(rowIndex, colIndex, columns) {
        if (!this.cellRanges?.length) {
            return true;
        }
        return this.getCellRangeState(rowIndex, colIndex).inRange;
    }

    buildSelectionTsv() {
        const bounds = this.getClipboardTargetBounds();
        if (!bounds || !this.api) {
            return "";
        }

        const columns = this.api.getAllDisplayedColumns();
        const lines = [];

        for (let rowIndex = bounds.minRowIndex; rowIndex <= bounds.maxRowIndex; rowIndex += 1) {
            const rowNode = this.api.getDisplayedRowAtIndex(rowIndex);
            if (!rowNode?.data || !this.shouldApplyClipboardToRow(rowNode)) {
                continue;
            }

            const cells = [];
            for (let colIndex = bounds.minColIndex; colIndex <= bounds.maxColIndex; colIndex += 1) {
                const column = columns[colIndex];
                const field = column.getColDef().field;
                if (!field || !this.isCellInClipboardRange(rowIndex, colIndex, columns)) {
                    cells.push("");
                    continue;
                }
                cells.push(escapeTsvCell(this.getCellDisplayValue(rowNode, column)));
            }
            lines.push(cells.join("\t"));
        }

        return lines.join("\n");
    }

    collectChangesForMatrix(matrix, anchorRowIndex, anchorColIndex, valueFactory) {
        if (!this.api || !matrix.length) {
            return [];
        }

        const columns = this.api.getAllDisplayedColumns();
        const changes = [];

        for (let r = 0; r < matrix.length; r += 1) {
            const rowIndex = anchorRowIndex + r;
            if (rowIndex >= this.api.getDisplayedRowCount()) {
                break;
            }
            const rowNode = this.api.getDisplayedRowAtIndex(rowIndex);
            if (!rowNode?.data || !this.shouldApplyClipboardToRow(rowNode)) {
                continue;
            }

            const rowValues = matrix[r];
            for (let c = 0; c < rowValues.length; c += 1) {
                const colIndex = anchorColIndex + c;
                if (colIndex >= columns.length) {
                    break;
                }
                const column = columns[colIndex];
                const colDef = column.getColDef();
                const field = colDef.field;
                if (!field || !this.isColumnEditableForRow(column, rowNode)) {
                    continue;
                }

                const oldValue = rowNode.data[field];
                const newValue = valueFactory(colDef, column, rowNode, rowValues[c]);
                if (oldValue === newValue || (oldValue == null && newValue == null)) {
                    continue;
                }
                changes.push({ node: rowNode, field, oldValue, newValue });
            }
        }

        return changes;
    }

    applyBatchCellChanges(changes, source = CELL_CHANGE_SOURCES.PASTE) {
        if (!changes.length) {
            return 0;
        }

        const range = this.computeRangeFromRawChanges(changes);
        const { applied, entries } = this.commitCellChanges({
            source,
            changes,
            range,
            alreadyApplied: false
        });

        if (!applied) {
            return 0;
        }

        const undoChanges = entries.map((entry) => ({
            node: entry.node,
            field: entry.field,
            oldValue: entry.newValue,
            newValue: entry.oldValue,
            rowIndex: entry.rowIndex,
            colId: entry.colId
        }));

        this._clipboardCommandStack.push({
            undo: () => {
                this.commitCellChanges({
                    source: CELL_CHANGE_SOURCES.UNDO,
                    changes: undoChanges,
                    range: this.computeRangeFromRawChanges(undoChanges),
                    alreadyApplied: false
                });
            },
            execute: () => {
                this.commitCellChanges({
                    source: CELL_CHANGE_SOURCES.REDO,
                    changes: entries.map((entry) => ({
                        node: entry.node,
                        field: entry.field,
                        oldValue: entry.oldValue,
                        newValue: entry.newValue,
                        rowIndex: entry.rowIndex,
                        colId: entry.colId
                    })),
                    range,
                    alreadyApplied: false
                });
            }
        });

        return applied;
    }

    async copySelectionToClipboard() {
        if (!this.isClipboardEnabled()) {
            return false;
        }
        const tsv = this.buildSelectionTsv();
        return writeClipboardText(tsv);
    }

    async pasteFromClipboard(frozenBounds) {
        if (!this.isClipboardEnabled()) {
            return 0;
        }

        const bounds = frozenBounds ?? this.getClipboardTargetBounds();
        if (!bounds) {
            return 0;
        }

        const text = await readClipboardText();
        if (text == null) {
            return 0;
        }

        return this.applyPasteText(text, bounds);
    }

    applyPasteText(text, bounds) {
        const matrix = parseTsv(text);
        if (!matrix.length || !bounds) {
            return 0;
        }

        const changes = this.collectChangesForMatrix(
            matrix,
            bounds.minRowIndex,
            bounds.minColIndex,
            (colDef, column, rowNode, cellText) => this.parsePastedValue(colDef, column, rowNode, cellText)
        );
        return this.applyBatchCellChanges(changes, CELL_CHANGE_SOURCES.PASTE);
    }

    /**
     * Copy-fill: tile sourceBounds into targetBounds; skips cells inside sourceBounds.
     * @param {{ respectSelectionMask?: boolean }} opts — false for fill-handle (fills full extension)
     */
    fillRange(sourceBounds, targetBounds, opts = {}) {
        if (!this.isClipboardEnabled() || !this.api || !sourceBounds || !targetBounds) {
            return 0;
        }

        const respectSelectionMask = opts.respectSelectionMask !== false;
        const columns = this.api.getAllDisplayedColumns();
        const sourceHeight = sourceBounds.maxRowIndex - sourceBounds.minRowIndex + 1;
        const sourceWidth = sourceBounds.maxColIndex - sourceBounds.minColIndex + 1;
        const mod = (n, m) => ((n % m) + m) % m;
        const changes = [];

        for (let rowIndex = targetBounds.minRowIndex; rowIndex <= targetBounds.maxRowIndex; rowIndex += 1) {
            const rowNode = this.api.getDisplayedRowAtIndex(rowIndex);
            if (!rowNode?.data || !this.shouldApplyClipboardToRow(rowNode)) {
                continue;
            }

            for (let colIndex = targetBounds.minColIndex; colIndex <= targetBounds.maxColIndex; colIndex += 1) {
                if (rowIndex >= sourceBounds.minRowIndex && rowIndex <= sourceBounds.maxRowIndex
                    && colIndex >= sourceBounds.minColIndex && colIndex <= sourceBounds.maxColIndex) {
                    continue;
                }
                if (respectSelectionMask && !this.isCellInClipboardRange(rowIndex, colIndex, columns)) {
                    continue;
                }

                const relRow = rowIndex - sourceBounds.minRowIndex;
                const relCol = colIndex - sourceBounds.minColIndex;
                const sourceRowIndex = sourceBounds.minRowIndex + mod(relRow, sourceHeight);
                const sourceColIndex = sourceBounds.minColIndex + mod(relCol, sourceWidth);

                const sourceRowNode = this.api.getDisplayedRowAtIndex(sourceRowIndex);
                if (!sourceRowNode?.data) {
                    continue;
                }

                const column = columns[colIndex];
                const sourceColumn = columns[sourceColIndex];
                const field = column.getColDef().field;
                const sourceField = sourceColumn.getColDef().field;
                if (!field || !sourceField || !this.isColumnEditableForRow(column, rowNode)) {
                    continue;
                }

                const newValue = sourceRowNode.data[sourceField];
                const oldValue = rowNode.data[field];
                if (oldValue === newValue || (oldValue == null && newValue == null)) {
                    continue;
                }
                changes.push({ node: rowNode, field, oldValue, newValue });
            }
        }

        return this.applyBatchCellChanges(changes, CELL_CHANGE_SOURCES.FILL_HANDLE);
    }

    fillDownSelection() {
        if (!this.isClipboardEnabled()) {
            return 0;
        }

        const bounds = this.getClipboardTargetBounds();
        if (!bounds || bounds.minRowIndex === bounds.maxRowIndex || !this.api) {
            return 0;
        }

        const columns = this.api.getAllDisplayedColumns();
        const sourceRow = this.api.getDisplayedRowAtIndex(bounds.minRowIndex);
        if (!sourceRow?.data) {
            return 0;
        }

        const changes = [];
        for (let rowIndex = bounds.minRowIndex + 1; rowIndex <= bounds.maxRowIndex; rowIndex += 1) {
            const rowNode = this.api.getDisplayedRowAtIndex(rowIndex);
            if (!rowNode?.data || !this.shouldApplyClipboardToRow(rowNode)) {
                continue;
            }
            for (let colIndex = bounds.minColIndex; colIndex <= bounds.maxColIndex; colIndex += 1) {
                if (!this.isCellInClipboardRange(rowIndex, colIndex, columns)) {
                    continue;
                }
                const column = columns[colIndex];
                const field = column.getColDef().field;
                if (!field || !this.isColumnEditableForRow(column, rowNode)) {
                    continue;
                }
                const newValue = sourceRow.data[field];
                const oldValue = rowNode.data[field];
                if (oldValue === newValue || (oldValue == null && newValue == null)) {
                    continue;
                }
                changes.push({ node: rowNode, field, oldValue, newValue });
            }
        }

        return this.applyBatchCellChanges(changes, CELL_CHANGE_SOURCES.FILL_DOWN);
    }

    clearSelectionCells() {
        if (!this.isClipboardEnabled()) {
            return 0;
        }

        const bounds = this.getClipboardTargetBounds();
        if (!bounds || !this.api) {
            return 0;
        }

        const columns = this.api.getAllDisplayedColumns();
        const changes = [];

        for (let rowIndex = bounds.minRowIndex; rowIndex <= bounds.maxRowIndex; rowIndex += 1) {
            const rowNode = this.api.getDisplayedRowAtIndex(rowIndex);
            if (!rowNode?.data || !this.shouldApplyClipboardToRow(rowNode)) {
                continue;
            }
            for (let colIndex = bounds.minColIndex; colIndex <= bounds.maxColIndex; colIndex += 1) {
                if (!this.isCellInClipboardRange(rowIndex, colIndex, columns)) {
                    continue;
                }
                const column = columns[colIndex];
                const field = column.getColDef().field;
                if (!field || !this.isColumnEditableForRow(column, rowNode)) {
                    continue;
                }
                const oldValue = rowNode.data[field];
                if (oldValue == null || oldValue === "") {
                    continue;
                }
                changes.push({ node: rowNode, field, oldValue, newValue: null });
            }
        }

        return this.applyBatchCellChanges(changes, CELL_CHANGE_SOURCES.CLEAR);
    }

    undoClipboard() {
        if (typeof this.api?.undoCellEditing === "function" && this.api.undoCellEditing()) {
            return true;
        }
        return this._clipboardCommandStack?.undo() ?? false;
    }

    handleClipboardCellKeyDown(event) {
        if (!this.isClipboardEnabled()) {
            return;
        }

        const domEvent = event.event;
        if (!domEvent?.key && !domEvent?.code) {
            return;
        }

        const editing = !!this.api?.getEditingCells()?.length;

        if (matchKeyboardShortcut(domEvent, { mod: true, code: "KeyZ", key: "z", shift: false })) {
            domEvent.preventDefault();
            this.undoClipboard();
            return;
        }

        if (editing) return;

        if (matchKeyboardShortcut(domEvent, { mod: true, code: "KeyC", key: "c" })) {
            domEvent.preventDefault();
            this.copySelectionToClipboard();
            return;
        }
        if (matchKeyboardShortcut(domEvent, { mod: true, code: "KeyV", key: "v" })) {
            domEvent.preventDefault();
            const bounds = this.getClipboardTargetBounds();
            void this.pasteFromClipboard(bounds);
            return;
        }
        if (matchKeyboardShortcut(domEvent, { mod: true, code: "KeyD", key: "d" })) {
            domEvent.preventDefault();
            this.fillDownSelection();
            return;
        }
        if (matchKeyboardShortcut(domEvent, { code: "Delete", key: "Delete" })) {
            domEvent.preventDefault();
            this.clearSelectionCells();
        }
    }

    buildClipboardGridOptions() {
        return this.isClipboardEnabled() ? { onCellKeyDown: event => this.handleClipboardCellKeyDown(event) } : {};
    }
};
