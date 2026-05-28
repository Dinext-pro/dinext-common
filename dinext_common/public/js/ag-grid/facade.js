// DinextAgGrid public facade — assigns window.DinextAgGrid (load after table.js, profiles.js).
(function() {
    const loader = window.DinextAgGridLoader;
    const I = window.DinextAgGridInternals;

    if (!loader) {
        throw new Error("DinextAgGridLoader must be loaded before ag-grid/facade.js");
    }
    if (!I || typeof I.DinextAgGridTable !== "function") {
        throw new Error("DinextAgGrid.Table must be loaded before ag-grid/facade.js");
    }
    if (typeof I.useScenario !== "function") {
        throw new Error("DinextAgGrid profiles must load before ag-grid/facade.js");
    }

    const AG_GRID_VERSION = loader.AG_GRID_VERSION;
    const DINEXT_AG_GRID_BUILD = loader.BUILD;
    const AG_GRID_FEATURE_CSS = loader.AG_GRID_FEATURE_CSS;
    const DinextAgGridTable = I.DinextAgGridTable;
    const DinextAgGridTextEditor = I.DinextAgGridTextEditor;
    const DinextAgGridNumericEditor = I.DinextAgGridNumericEditor;

    let reportFactoryPromise = null;

    function isReportFactoryReady() {
        return !!(window.DinextAgGrid
            && typeof window.DinextAgGrid.createReportTable === "function"
            && window.DinextAgGrid.createReportTable.__isFactory === true);
    }

    function ensureReportFactoryScript() {
        if (isReportFactoryReady()) {
            return Promise.resolve();
        }

        if (!reportFactoryPromise) {
            const factoryUrl = `/assets/dinext_common/js/ag-grid/report-factory.js?v=${DINEXT_AG_GRID_BUILD}`;
            reportFactoryPromise = loader.loadScriptOnce(factoryUrl, isReportFactoryReady).then(() => {
                if (!isReportFactoryReady()) {
                    throw new Error("DinextAgGrid report factory не загрузился");
                }
            });
        }

        return reportFactoryPromise;
    }

    function createReportTableLazy(config) {
        return ensureReportFactoryScript().then(() => window.DinextAgGrid.createReportTable(config));
    }

    createReportTableLazy.__isLazyLoader = true;

    const SCENARIOS = Object.keys(I.AG_GRID_SCENARIOS || {});

    function use(scenario, options = {}) {
        return I.useScenario(scenario, options).then(() => ({
            Table: I.getScenarioTable(scenario)
        }));
    }

    window.DinextAgGrid = Object.assign(window.DinextAgGrid || {}, {
        version: AG_GRID_VERSION,
        build: DINEXT_AG_GRID_BUILD,
        SCENARIOS,
        use,
        ensure: I.ensureAgGrid,
        load: I.ensureAgGrid,
        ensureModules: I.ensureModules,
        profiles: I.AG_GRID_PROFILES,
        scenarios: I.AG_GRID_SCENARIOS,
        ensureFeatureStyles: I.ensureFeatureStyles,
        ensureReportFactory: ensureReportFactoryScript,
        featureStyles: AG_GRID_FEATURE_CSS,
        getStableFallbackRowId: I.getStableFallbackRowId,
        Table: DinextAgGridTable,
        createReportTable: createReportTableLazy,
        editors: {
            Text: DinextAgGridTextEditor,
            Numeric: DinextAgGridNumericEditor
        },
        column: {
            htmlHeader: I.htmlHeaderParams,
            ensureFieldIds: I.ensureFieldIds,
            participant: I.participantColumnDef
        },
        treeCell: I.treeCell,
        components: {
            HtmlHeader: I.DinextAgGridHtmlHeader
        },
        adapters: (window.DinextAgGrid && window.DinextAgGrid.adapters) || {}
    });
})();
