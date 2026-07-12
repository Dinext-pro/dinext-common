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
 * - `rowReorder`   — gutter row drag-and-drop reorder
 * - `selectionStatus` — Excel-like status bar aggregates
 * - `toolbar`        — floating trigger + slide-down command bar
 * - `fullscreen`     — native Fullscreen API on container/shell
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
    | "rowReorder"
    | "selectionStatus"
    | "toolbar"
    | "fullscreen"
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
export type DinextTableColumnTypePreset = "text" | "number" | "integer" | "date" | "checkbox" | "boolean";

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

    // --- tree ---
    /** @layer tree — inner content; indent + chevron добавляет ядро */
    render?: (params: DinextTableCellRendererParams) => HTMLElement | string;
    /**
     * @layer tree
     * `true` — chevron/indent на этой колонке.
     * На первой leaf-колонке по умолчанию включено; `false` — отключить.
     */
    tree?: boolean;
    /** @layer tree — full override без tree chrome */
    cellRenderer?: unknown;

    // --- editors ---
    /** @layer editors — preset: text | number | integer | date | checkbox | boolean */
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
        /** @layer theme — vertical borders in body; default true */
        columnBorder?: boolean;
        /**
         * Vertical borders in header. Default: same as `columnBorder`
         * (Quartz treats header separately from body).
         */
        headerColumnBorder?: boolean | Record<string, unknown>;
        /** AG Grid Quartz `spacing` — base density unit (px number or CSS length) */
        spacing?: number | string;
        /** AG Grid Quartz `cellHorizontalPadding` — start/end padding in cells/headers */
        cellHorizontalPadding?: number | string;
        /** AG Grid Quartz `wrapperBorderRadius`; also sets `--dinext-table-radius` for status bar */
        borderRadius?: number | string;
        wrapperBorderRadius?: number | string;
    };
}

/** @layer tree */
export interface DinextTableTreeOptions {
    childrenField?: string;
    rowIdField?: string;
    expandedIds?: string[];
    /** @layer tree — явное поле колонки для chevron/indent (приоритет над `tree: true`) */
    treeColumnField?: string;
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

/** @layer rowReorder */
export interface DinextTableRowReorderMove {
    section: "body" | "summary";
    parentRowId: string | null;
    rowId: string;
    fromIndex: number;
    toIndex: number;
    blockSize: number;
    orderedLocalRowIds: string[];
    orderedRowIds: string[];
    rows: DinextTableRowData[];
}

/** @layer rowReorder */
export interface DinextTableRowReorderContext {
    table: DinextTableInstance;
    source: string;
    move: DinextTableRowReorderMove;
}

/** @layer rowReorder */
export interface DinextTableRowReorderOptions {
    rowReorder?: {
        /** Default: true */
        enabled?: boolean;
        /** Default: `"gutter"`. `"column"` reserved */
        handle?: "gutter" | "column";
        gutterWidth?: number;
        allowSummary?: boolean;
        /** Default: `"siblings"`. `false` = top-level body only */
        allowTree?: "siblings" | false;
    };
    /** @layer rowReorder — sync, before commit */
    onValidateRowReorder?: (ctx: DinextTableRowReorderContext) => boolean | string;
    /** @layer rowReorder — after commit; false/reject → revert */
    onRowReorder?: (ctx: DinextTableRowReorderContext) => void | false | Promise<void | false>;
    /** @layer rowReorder — per-row guard */
    canReorderRow?: (ctx: {
        table: DinextTableInstance;
        row: DinextTableRowData;
        rowId: string;
        section: "body" | "summary";
        parentRowId: string | null;
    }) => boolean;
}

/** @layer selectionStatus */
export interface DinextTableSelectionStatusStats {
    cellCount: number;
    numericCount: number;
    sum: number;
    average: number | null;
    min: number | null;
    max: number | null;
}

/** @layer selectionStatus */
export interface DinextTableSelectionStatusOptions {
    selectionStatus?: {
        /** Default: selection.enabled */
        enabled?: boolean;
        /** Show bar when at least this many cells selected. Default: 2 */
        minCells?: number;
        /** Default: ["average", "count", "sum"] */
        metrics?: Array<"average" | "count" | "sum" | "numericCount" | "min" | "max">;
        /** Custom text; return "" to hide */
        format?: (stats: DinextTableSelectionStatusStats, table: DinextTableInstance) => string;
    };
}

/** @layer toolbar */
export interface DinextTableToolbarActionContext {
    table: DinextTableInstance;
    api: DinextTableGridApi;
    event: MouseEvent;
    closeToolbar: () => void;
}

/** @layer toolbar */
export interface DinextTableToolbarItem {
    id?: string;
    type?: "button" | "separator";
    label?: string;
    title?: string;
    /** Frappe / Desk icon class, e.g. `icon-refresh` */
    icon?: string;
    /** Inline SVG markup for preset icons */
    iconSvg?: string;
    /** `end` — right-aligned group (e.g. fullscreen) */
    align?: "end";
    disabled?: boolean | ((ctx: DinextTableToolbarActionContext) => boolean);
    hidden?: boolean | ((ctx: DinextTableToolbarActionContext) => boolean);
    onClick?: (ctx: DinextTableToolbarActionContext) => void;
}

/** @layer toolbar */
export interface DinextTableToolbarOptions {
    toolbar?: {
        /** Default: true */
        enabled?: boolean;
        defaultPinned?: boolean;
        /** localStorage key suffix for pinned state */
        persistKey?: string;
        /** Default: `["history", "tree", "fullscreen"]`; set `[]` to disable presets */
        presets?: Array<"history" | "tree" | "clipboard" | "fullscreen">;
        items?: DinextTableToolbarItem[];
    };
}

/** @layer fullscreen */
export interface DinextTableFullscreenOptions {
    fullscreen?: {
        enabled?: boolean;
        /** `container` (default) or `shell` */
        target?: "container" | "shell";
        /** Required when `target: "shell"` */
        shell?: HTMLElement;
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
        DinextTableRowReorderOptions,
        DinextTableSelectionStatusOptions,
        DinextTableToolbarOptions,
        DinextTableFullscreenOptions,
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
    /** @layer core — keys: data | columns | edit | toolbar | summaryRows, … */
    setOption(key: "data" | "columns" | "edit" | "toolbar" | "summaryRows", value: unknown): void;
    /** @layer core */
    destroy(): void;

    // --- tree ---
    /** @layer tree — resolved field for chevron/indent, or null */
    getTreeColumnField(): string | null;
    /** @layer tree */
    toggleRow(rowId: string): void;
    /** @layer tree */
    expandRow(rowId: string): Promise<void>;
    /** @layer tree */
    collapseRow(rowId: string): void;
    /** @layer tree — expand every expandable row (incl. lazy via onExpandRow) */
    expandAll(): Promise<void>;
    /** @layer tree */
    collapseAll(): void;
    /** @layer tree — lazy load result */
    setRowChildren(rowId: string, children: DinextTableRowData[]): void;
    /** @layer section */
    setSummaryRows(rows: DinextTableRowData[]): void;

    // --- selection ---
    /** @layer selection */
    getCellRanges(): DinextTableCellRange[];
    /** @layer selection */
    clearCellSelection(): void;
    /** @layer selectionStatus — snapshot aggregates for current selection */
    getSelectionStats(): DinextTableSelectionStatusStats;

    // --- toolbar ---
    /** @layer toolbar */
    isToolbarEnabled(): boolean;
    /** @layer toolbar */
    getToolbarItems(): DinextTableToolbarItem[];
    /** @layer toolbar */
    registerToolbarItem(item: DinextTableToolbarItem): void;
    /** @layer toolbar */
    setToolbarItems(items: DinextTableToolbarItem[]): void;
    /** @layer toolbar */
    isToolbarPinned(): boolean;
    /** @layer toolbar */
    isToolbarOpen(): boolean;
    /** @layer toolbar */
    setToolbarPinned(pinned: boolean, opts?: { persist?: boolean }): void;
    /** @layer toolbar */
    toggleToolbarPinned(): void;
    /** @layer toolbar */
    closeToolbarMenu(): void;
    /** @layer toolbar */
    refreshToolbar(): void;

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
    /** @layer clipboard — unified CommandStack (edit, paste, fill, clear) */
    undoClipboard(): boolean;
    /** @layer clipboard — unified CommandStack (edit, paste, fill, clear) */
    redoClipboard(): boolean;

    /** @layer rowReorder */
    isRowReorderEnabled(): boolean;

    // --- fullscreen ---
    /** @layer fullscreen */
    isFullscreenEnabled(): boolean;
    /** @layer fullscreen */
    isFullscreen(): boolean;
    /** @layer fullscreen */
    enterFullscreen(): Promise<boolean>;
    /** @layer fullscreen */
    exitFullscreen(): Promise<boolean>;
    /** @layer fullscreen */
    toggleFullscreen(): Promise<boolean>;

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
