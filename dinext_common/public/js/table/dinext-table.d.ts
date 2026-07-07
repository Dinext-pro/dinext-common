/**
 * DinextTable — типы для IDE (JSDoc / TypeScript).
 *
 * Runtime: JS bundle, `window.DinextTable`. Файл не участвует в build — только подсказки.
 *
 * Слои (layer):
 * - `core`       — facade, lifecycle, setOption
 * - `grid`       — mergeGridOptions, defaultColDef ядра
 * - `theme`      — Frappe light/dark sync
 * - `tree`       — N-level expand, lazy load
 * - `edit`       — scalar edit, validate/save, undo sync
 * - `editors`    — columnTypes presets (text/number/integer/date)
 * - `navigation` — Tab/Enter Excel-like (AG Grid hooks)
 * - `selection`  — custom range (Community, без Enterprise)
 * - `clipboard`  — custom TSV copy/paste/fill (Community)
 * - `fillHandle`   — Excel-like corner drag copy-fill
 * - `formatting` — passthrough styling (→ AG Grid colDef / gridOptions)
 * - `ag-grid`    — passthrough напрямую в AG Grid 35 Community
 *
 * @see README.md — обзор API; usage-guides/ — сценарии
 */

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

/** Слой, которому принадлежит option / callback / method. */
export type DinextTableLayer =
    | "core"
    | "grid"
    | "theme"
    | "tree"
    | "section"
    | "edit"
    | "editors"
    | "navigation"
    | "selection"
    | "clipboard"
    | "fillHandle"
    | "formatting"
    | "ag-grid";

/** AG Grid GridApi (minimal; полный API — docs AG Grid 35). @layer ag-grid */
export interface DinextTableGridApi {
    setGridOption(key: string, value: unknown): void;
    getRowNode(id: string): { data?: DinextTableRowData; rowIndex?: number } | undefined;
    getDisplayedRowAtIndex(index: number): { data?: DinextTableRowData; rowIndex?: number } | undefined;
    getDisplayedRowCount(): number;
    getAllDisplayedColumns(): Array<{ getColId(): string; getColDef(): Record<string, unknown> }>;
    getFirstDisplayedRowIndex(): number | null;
    getLastDisplayedRowIndex(): number | null;
    getValue(key: { rowNode: unknown; colDef: { field?: string }; column?: unknown }): unknown;
    getEditingCells(): unknown[];
    setFocusedCell(rowIndex: number, colKey: string): void;
    startEditingCell(params: { rowIndex: number; colKey: string }): void;
    refreshCells(params?: Record<string, unknown>): void;
    applyTransaction(params: { add?: unknown[]; update?: unknown[]; remove?: unknown[] }): void;
    forEachNode(callback: (node: { data?: DinextTableRowData }) => void): void;
    undoCellEditing(): void;
    redoCellEditing(): void;
    destroy(): void;
    [key: string]: unknown;
}

/** Прямоугольник range selection. @layer selection */
export interface DinextTableCellRange {
    startRowId: string;
    startColId: string;
    endRowId: string;
    endColId: string;
}

/** Индексный bounding box (displayed row/col indices). @layer clipboard / fillHandle */
export interface DinextTableIndexBounds {
    minRowIndex: number;
    maxRowIndex: number;
    minColIndex: number;
    maxColIndex: number;
}

/** @layer tree — только в grid rowData, не задавать в source data */
export interface DinextTableTreeMeta {
    _rowId?: string;
    _level?: number;
    _hasChildren?: boolean;
    _parentRowId?: string;
    _treeLoading?: boolean;
}

/** @layer tree — only on head row (`mergeGroupIndex === 0`); children live here */
export interface DinextTableMergeGroupRowMeta {
    mergeGroupId?: string;
    mergeGroupIndex?: number;
    mergeGroupSize?: number;
}

/** @layer section — only on visible summary rows in grid */
export interface DinextTableSectionMeta {
    _section?: "body" | "summary";
}

/** Строка данных клиента (+ опционально tree meta в grid). */
export type DinextTableRowData = Record<string, unknown> & DinextTableTreeMeta & DinextTableMergeGroupRowMeta & DinextTableSectionMeta;

/** Пресеты `column.type` из EditorsMixin. @layer editors */
export type DinextTableColumnTypePreset = "text" | "number" | "integer" | "date";

// ---------------------------------------------------------------------------
// Column
// ---------------------------------------------------------------------------

/** AG Grid cell renderer params (упрощённо). @layer ag-grid */
export interface DinextTableCellRendererParams {
    value: unknown;
    data: DinextTableRowData;
    node: unknown;
    colDef: Record<string, unknown>;
    column: unknown;
    api: DinextTableGridApi;
    context: { dinextTable?: DinextTableInstance };
}

/**
 * Колонка DinextTable → нормализуется в AG Grid columnDef.
 * Ключи без пометки layer — см. группы ниже.
 */
export interface DinextTableColumnDef {
    // --- core / grid (обязательные для data-bound col) ---
    /** @layer core */
    field?: string;
    /** @layer ag-grid */
    headerName?: string;

    // --- edit (→ AG Grid editable) ---
    /** @layer edit — приоритет выше `options.edit` */
    edit?: boolean | ((row: DinextTableRowData, field: string) => boolean);

    // --- tree col 0 ---
    /** @layer tree — inner content; indent+chevron добавляет ядро */
    render?: (params: DinextTableCellRendererParams) => HTMLElement | string;
    /** @layer tree — default true на col 0 */
    tree?: boolean;
    /** @layer tree — full override без tree chrome */
    cellRenderer?: unknown;

    // --- editors ---
    /** @layer editors — preset: text | number | integer | date */
    type?: DinextTableColumnTypePreset | string;

    // --- layout @layer ag-grid ---
    width?: number;
    flex?: number;
    minWidth?: number;
    maxWidth?: number;
    pinned?: "left" | "right";
    hide?: boolean;

    // --- display / edit @layer ag-grid ---
    cellDataType?: string;
    valueFormatter?: (params: DinextTableCellRendererParams) => string;
    valueParser?: (params: { newValue: unknown; oldValue: unknown; data: DinextTableRowData }) => unknown;
    cellEditor?: string | unknown;
    cellEditorParams?: Record<string, unknown>;

    // --- formatting @layer formatting (passthrough → AG Grid) ---
    cellStyle?: Record<string, string> | ((params: DinextTableCellRendererParams) => Record<string, string>);
    cellClass?: string | string[] | ((params: DinextTableCellRendererParams) => string | string[]);
    cellClassRules?: Record<string, (params: DinextTableCellRendererParams) => boolean>;

    /** Любые другие AG Grid ColDef keys @layer ag-grid */
    [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Options — grouped by layer
// ---------------------------------------------------------------------------

/** @layer core */
export interface DinextTableCoreOptions {
    /** @layer core — required */
    container: HTMLElement;
    /** @layer core */
    data?: DinextTableRowData[];
    /** @layer core */
    columns?: DinextTableColumnDef[];
    /** @layer edit — global editable default */
    edit?: boolean;
}

/** @layer theme */
export interface DinextTableThemeOptions {
    theme?: {
        /** @layer theme — vertical cell borders; default true */
        columnBorder?: boolean;
    };
}

/** @layer tree */
export interface DinextTableTreeOptions {
    childrenField?: string;
    rowIdField?: string;
    expandedIds?: string[];
    /** @layer tree — merge-group row metadata field names */
    mergeGroup?: {
        idField?: string;
        indexField?: string;
        sizeField?: string;
    };
    onExpandRow?: (ctx: {
        rowId: string;
        row: DinextTableRowData | null;
        table: DinextTableInstance;
        section?: "body" | "summary";
    }) => void | Promise<void>;
}

/** @layer section */
export interface DinextTableSectionOptions {
    summaryRows?: DinextTableRowData[];
    summary?: {
        pin?: "bottom" | false;
        expandedIds?: string[];
        edit?: boolean;
        clipboard?: boolean;
        selection?: boolean;
    };
}

/** @layer edit — one item in onValidateCells / onSaveCells batch */
export interface DinextTableCellChange {
    rowId: string;
    rowIndex: number | null | undefined;
    colId: string | undefined;
    field: string;
    oldValue: unknown;
    newValue: unknown;
    row: DinextTableRowData;
    section: "body" | "summary";
}

/** @layer edit — bounding box of a batch mutation */
export interface DinextTableCellChangeRange {
    startRowId?: string;
    endRowId?: string;
    startColId?: string;
    endColId?: string;
    minRowIndex?: number;
    maxRowIndex?: number;
    minColIndex?: number;
    maxColIndex?: number;
}

/** @layer edit */
export type DinextTableCellChangeSource =
    | "edit"
    | "paste"
    | "fillDown"
    | "fillHandle"
    | "clear"
    | "undo"
    | "redo";

/** @layer edit */
export interface DinextTableCellChangeContext {
    table: DinextTableInstance;
    source: DinextTableCellChangeSource;
    range: DinextTableCellChangeRange | null;
    changes: DinextTableCellChange[];
}

/** @layer edit */
export interface DinextTableEditOptions {
    /** @layer edit — batch validate before commit; `true` ok, else reject batch */
    onValidateCells?: (ctx: DinextTableCellChangeContext) => true | string | false;
    /** @layer edit — batch persist after commit; `false` or throw → revert batch */
    onSaveCells?: (ctx: DinextTableCellChangeContext) => void | false | Promise<void | false>;
    /** @layer edit + ag-grid — onCellEditRequest pipeline */
    readOnlyEdit?: boolean;
}

/** @layer navigation */
export interface DinextTableNavigationOptions {
    navigation?: {
        enabled?: boolean;
        skipNonEditable?: boolean;
        enterMovesDown?: boolean;
        tabWraps?: boolean;
        isRowNavigable?: (row: DinextTableRowData) => boolean;
        isCellNavigable?: (row: DinextTableRowData, field: string) => boolean;
    };
}

/** @layer selection */
export interface DinextTableSelectionOptions {
    selection?: {
        enabled?: boolean;
        suppressMultiRanges?: boolean;
    };
}

/** @layer clipboard */
export interface DinextTableClipboardOptions {
    clipboard?: {
        enabled?: boolean;
    };
}

/** @layer fillHandle */
export interface DinextTableFillHandleOptions {
    fillHandle?: {
        enabled?: boolean;
    };
}

/** @layer core + ag-grid */
export interface DinextTableCallbackOptions {
    /** @layer core */
    onReady?: (table: DinextTableInstance) => void;
    /** @layer grid — chained with mixins */
    onCellDoubleClicked?: (params: unknown, table: DinextTableInstance) => void;
}

/**
 * AG Grid passthrough. Callbacks с тем же именем в mixins склеиваются (chainHandlers).
 * @layer ag-grid
 */
export interface DinextTableAgGridPassthrough {
    /** @layer ag-grid — deep merge; columnTypes merged last from user */
    gridOptions?: Record<string, unknown>;
    /** @layer ag-grid — deep merge с ядром (resizable, sortable, enableCellChangeFlash) */
    defaultColDef?: Record<string, unknown>;
}

/** Полный объект `DinextTable.create(options)`. */
export interface DinextTableCreateOptions
    extends DinextTableCoreOptions,
        DinextTableThemeOptions,
        DinextTableTreeOptions,
        DinextTableSectionOptions,
        DinextTableEditOptions,
        DinextTableNavigationOptions,
        DinextTableSelectionOptions,
        DinextTableClipboardOptions,
        DinextTableFillHandleOptions,
        DinextTableCallbackOptions,
        DinextTableAgGridPassthrough {}

// ---------------------------------------------------------------------------
// Instance
// ---------------------------------------------------------------------------

export interface DinextTableInstance {
    // --- properties ---
    /** @layer core */
    options: DinextTableCreateOptions;
    /** @layer core */
    columns: DinextTableColumnDef[];
    /** @layer core — top-level source rows */
    sourceData: DinextTableRowData[];
    /** @layer section — summary source rows */
    summarySourceData?: DinextTableRowData[];
    /** @layer section — visible summary rows (pinned) */
    summaryRowData?: DinextTableRowData[];
    /** @layer core — visible flat rows in grid */
    rowData: DinextTableRowData[];
    /** @layer ag-grid */
    api: DinextTableGridApi | null;
    /** @layer tree */
    expandedIds: Set<string>;
    /** @layer selection — read-only snapshot */
    readonly focusedCell?: { rowId: string; colId: string } | null;

    // --- core lifecycle ---
    /** @layer core */
    refresh(data?: DinextTableRowData[]): void;
    /** @layer core — keys: data | columns | edit */
    setOption(key: "data" | "columns" | "edit", value: unknown): void;
    /** @layer core */
    destroy(): void;

    // --- tree ---
    /** @layer tree */
    toggleRow(rowId: string): void;
    /** @layer tree */
    expandRow(rowId: string): Promise<void>;
    /** @layer tree */
    collapseRow(rowId: string): void;
    /** @layer tree — lazy load result */
    setRowChildren(rowId: string, children: DinextTableRowData[]): void;
    /** @layer section */
    setSummaryRows(rows: DinextTableRowData[]): void;

    // --- selection ---
    /** @layer selection */
    getCellRanges(): DinextTableCellRange[];
    /** @layer selection */
    clearCellSelection(): void;

    // --- clipboard ---
    /** @layer clipboard */
    copySelectionToClipboard(): Promise<boolean>;
    /** @layer clipboard */
    pasteFromClipboard(): Promise<number>;
    /** @layer clipboard */
    fillDownSelection(): number;
    /** @layer clipboard — tile source pattern into target extension cells */
    fillRange(
        sourceBounds: DinextTableIndexBounds,
        targetBounds: DinextTableIndexBounds,
        opts?: { respectSelectionMask?: boolean }
    ): number;
    /** @layer clipboard */
    clearSelectionCells(): number;
    /** @layer clipboard — AG Grid undo first, else CommandStack */
    undoClipboard(): boolean;

    // --- edit (advanced / used by clipboard) ---
    /** @layer edit — write nested sourceData by path id */
    writeSourceField?(rowId: string, field: string, value: unknown): DinextTableRowData | null;
}

// ---------------------------------------------------------------------------
// Static facade
// ---------------------------------------------------------------------------

export interface DinextTableStatic {
    /** @layer core — AG Grid version string */
    VERSION: string;
    /** @layer core — load CSS + ag-grid-community */
    load(): Promise<unknown>;
    /** @layer tree — spanRows callback for merge-group columns */
    createMergeGroupSpanRows(options?: DinextTableCreateOptions): (params: {
        nodeA?: { data?: DinextTableRowData };
        nodeB?: { data?: DinextTableRowData };
    }) => boolean;
    /** @layer edit — batch mutation source constants */
    readonly CELL_CHANGE_SOURCES: Record<
        "EDIT" | "PASTE" | "FILL_DOWN" | "FILL_HANDLE" | "CLEAR" | "UNDO" | "REDO",
        DinextTableCellChangeSource
    >;
    /** @layer core */
    create(options: DinextTableCreateOptions): Promise<DinextTableInstance>;
}

declare global {
    /** @layer core */
    const DinextTable: DinextTableStatic;

    interface Window {
        DinextTable: DinextTableStatic;
    }
}

export {};
