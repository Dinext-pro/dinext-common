// DinextAgGrid.createReportTable — Workload tab / Workload Report (rows + columnDefs).
(function() {
    const VALID_FEATURES = ["workload-report", "project-workload"];

    function buildTableOptions(config) {
        const {
            container,
            feature,
            tableClass,
            rows,
            columnDefs,
            onCellDoubleClicked,
            visibilityMode,
            fullscreen,
            toolbarTarget,
            fullscreenTarget,
            ...rest
        } = config;

        const options = Object.assign({}, rest);

        if (columnDefs !== undefined) {
            options.columnDefs = columnDefs;
        }
        if (rows !== undefined) {
            options.rows = rows;
        }
        if (visibilityMode !== undefined) {
            options.visibilityMode = visibilityMode;
        }
        if (fullscreen !== undefined) {
            options.fullscreen = fullscreen;
        }
        if (toolbarTarget !== undefined) {
            options.toolbarTarget = toolbarTarget;
        }
        if (fullscreenTarget !== undefined) {
            options.fullscreenTarget = fullscreenTarget;
        }
        if (onCellDoubleClicked !== undefined) {
            options.onCellDoubleClicked = onCellDoubleClicked;
        }

        return options;
    }

    function createReportTable(config) {
        if (!config || !config.container) {
            return Promise.reject(new Error("DinextAgGrid.createReportTable: container is required"));
        }

        if (!config.feature) {
            return Promise.reject(new Error("DinextAgGrid.createReportTable: feature is required"));
        }

        if (!VALID_FEATURES.includes(config.feature)) {
            return Promise.reject(new Error(
                `DinextAgGrid.createReportTable: unknown feature "${config.feature}"`
            ));
        }

        if (!window.DinextAgGrid || typeof window.DinextAgGrid.use !== "function") {
            return Promise.reject(new Error("DinextAgGrid.use не загружен"));
        }

        return window.DinextAgGrid.use(config.feature, { feature: config.feature }).then(() => {
            const TableClass = config.tableClass
                || (window.DinextAgGrid.presets && window.DinextAgGrid.presets.workload && window.DinextAgGrid.presets.workload.Table);
            if (!TableClass) {
                throw new Error("DinextAgGrid.presets.workload.Table не доступен");
            }

            return new TableClass(config.container, buildTableOptions(config));
        });
    }

    createReportTable.__isFactory = true;

    if (!window.DinextAgGrid) {
        throw new Error("DinextAgGrid must be loaded before ag-grid/report-factory.js");
    }

    window.DinextAgGrid.createReportTable = createReportTable;
})();
