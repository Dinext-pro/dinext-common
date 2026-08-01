import { parseLocaleNumber } from "../edit/editors.js";
import { findAgGridRootElement, findGridMountElement } from "../shared/utils.js";

const SELECTION_STATUS_DEFAULTS = {
    enabled: undefined,
    metrics: ["average", "count", "sum"],
    minCells: 2
};

const METRIC_LABELS = {
    average: "Average",
    count: "Count",
    sum: "Sum",
    numericCount: "Numerical Count",
    min: "Min",
    max: "Max"
};

/** @typedef {{ rowNode: object, column: object }} SelectedCellRef */

/**
 * Excel-like status bar under the grid: Average | Count | Sum for multi-cell selection.
 * Depends on SelectionMixin ranges; numeric values via getCellValue + locale parse fallback.
 */
export function resolveNumericCellValue(raw, displayValue) {
    if (typeof raw === "number" && Number.isFinite(raw)) return raw;
    const fromRaw = parseLocaleNumber(raw);
    if (fromRaw != null) return fromRaw;
    return parseLocaleNumber(displayValue);
}

/** @param {number[]} numbers */
export function buildSelectionStats(numbers, cellCount) {
    const stats = {
        cellCount,
        numericCount: numbers.length,
        sum: 0,
        average: null,
        min: null,
        max: null
    };

    if (!numbers.length) {
        return stats;
    }

    let sum = 0;
    let min = numbers[0];
    let max = numbers[0];
    for (const value of numbers) {
        sum += value;
        min = Math.min(min, value);
        max = Math.max(max, value);
    }

    stats.sum = sum;
    stats.average = sum / numbers.length;
    stats.min = min;
    stats.max = max;
    return stats;
}

export function formatSelectionStatusNumber(value) {
    if (!Number.isFinite(value)) return "";
    if (Number.isInteger(value)) return String(value);
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function formatSelectionStatusText(stats, metrics = SELECTION_STATUS_DEFAULTS.metrics) {
    const parts = [];

    for (const metric of metrics) {
        if (metric === "count") {
            parts.push(`${METRIC_LABELS.count}: ${stats.cellCount}`);
            continue;
        }
        if (metric === "numericCount") {
            parts.push(`${METRIC_LABELS.numericCount}: ${stats.numericCount}`);
            continue;
        }
        if (stats.numericCount === 0) {
            continue;
        }
        if (metric === "sum") {
            parts.push(`${METRIC_LABELS.sum}: ${formatSelectionStatusNumber(stats.sum)}`);
        } else if (metric === "average") {
            parts.push(`${METRIC_LABELS.average}: ${formatSelectionStatusNumber(stats.average)}`);
        } else if (metric === "min") {
            parts.push(`${METRIC_LABELS.min}: ${formatSelectionStatusNumber(stats.min)}`);
        } else if (metric === "max") {
            parts.push(`${METRIC_LABELS.max}: ${formatSelectionStatusNumber(stats.max)}`);
        }
    }

    return parts.join(" | ");
}

export const SelectionStatusMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._selectionStatusEl = null;
    }

    destroyFeatures() {
        this.container?.classList.remove("dinext-table--status-bar-visible");
        if (this._selectionStatusEl) {
            this._selectionStatusEl.remove();
            this._selectionStatusEl = null;
        }
        super.destroyFeatures();
    }

    afterGridCreated() {
        super.afterGridCreated();
        if (this.isSelectionStatusEnabled()) {
            this.ensureSelectionStatusBar();
            this.updateSelectionStatusBar();
        }
    }

    getSelectionStatusOptions() {
        return { ...SELECTION_STATUS_DEFAULTS, ...(this.options.selectionStatus || {}) };
    }

    /** Default: enabled when selection is enabled. */
    isSelectionStatusEnabled() {
        const enabled = this.getSelectionStatusOptions().enabled;
        if (enabled !== undefined) return !!enabled;
        return this.isSelectionEnabled();
    }

    ensureSelectionStatusBar() {
        if (this._selectionStatusEl || !this.container) {
            return;
        }

        this.container.classList.add("dinext-table--with-status-bar");
        const gridMount = findGridMountElement(this.container);
        const gridHost = findAgGridRootElement(this.container);
        const flexHost = gridMount || gridHost;
        if (flexHost) {
            flexHost.classList.add("dinext-table-grid-host");
        }

        const bar = document.createElement("div");
        bar.className = "dinext-table-status-bar";
        bar.setAttribute("role", "status");
        bar.setAttribute("aria-live", "polite");
        this.container.appendChild(bar);
        this._selectionStatusEl = bar;
    }

    refreshSelectionHighlight() {
        super.refreshSelectionHighlight();
        this.updateSelectionStatusBar();
    }

    /** @returns {SelectedCellRef[]} */
    collectSelectedCells() {
        if (!this.api || !this.cellRanges?.length) return [];

        const columns = this.api.getAllDisplayedColumns();
        const cells = [];

        for (const range of this.cellRanges) {
            const bounds = this.buildRangeBounds(range, columns);
            if (!bounds) {
                continue;
            }

            for (let rowIndex = bounds.minRowIndex; rowIndex <= bounds.maxRowIndex; rowIndex += 1) {
                const rowNode = this.api.getDisplayedRowAtIndex(rowIndex);
                if (!rowNode?.data || !this.shouldApplySelectionToRow(rowNode)) {
                    continue;
                }

                for (let colIndex = bounds.minColIndex; colIndex <= bounds.maxColIndex; colIndex += 1) {
                    if (!this.getCellRangeState(rowIndex, colIndex).inRange) {
                        continue;
                    }
                    const column = columns[colIndex];
                    if (!column?.getColDef()?.field) {
                        continue;
                    }
                    cells.push({ rowNode, column });
                }
            }
        }

        return cells;
    }

    computeSelectionStats() {
        const cells = this.collectSelectedCells();
        const numbers = [];

        for (const { rowNode, column } of cells) {
            const field = column.getColDef().field;
            const raw = typeof this.api?.getCellValue === "function"
                ? this.api.getCellValue({ colKey: column, rowNode })
                : rowNode.data[field];
            const displayValue = typeof this.getCellDisplayValue === "function"
                ? this.getCellDisplayValue(rowNode, column)
                : raw;
            const numeric = resolveNumericCellValue(raw, displayValue);
            if (numeric != null) {
                numbers.push(numeric);
            }
        }

        return buildSelectionStats(numbers, cells.length);
    }

    formatSelectionStatus(stats) {
        const options = this.getSelectionStatusOptions();
        if (typeof options.format === "function") return options.format(stats, this) ?? "";
        return formatSelectionStatusText(stats, options.metrics);
    }

    updateSelectionStatusBar() {
        if (!this.isSelectionStatusEnabled()) return;
        this.ensureSelectionStatusBar();
        if (!this._selectionStatusEl) return;

        const minCells = this.getSelectionStatusOptions().minCells ?? 2;
        const stats = this.computeSelectionStats();
        const visible = stats.cellCount >= minCells;
        const text = visible ? this.formatSelectionStatus(stats) : "";

        this._selectionStatusEl.textContent = text;
        this._selectionStatusEl.classList.toggle("is-hidden", !visible || !text);
        this.container?.classList.toggle(
            "dinext-table--status-bar-visible",
            !!(visible && text)
        );
    }

    getSelectionStats() {
        return { ...this.computeSelectionStats() };
    }
};
