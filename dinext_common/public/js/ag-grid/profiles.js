// DinextAgGrid profiles and lazy module loading (load after loader.js).
(function() {
    const loader = window.DinextAgGridLoader;
    if (!loader) {
        throw new Error("DinextAgGridLoader must be loaded before ag-grid/profiles.js");
    }

    const DINEXT_AG_GRID_BUILD = loader.BUILD;
    const BUDGET_TREE_SCRIPT = `/assets/dinext_common/js/presets/budget-tree.js?v=${DINEXT_AG_GRID_BUILD}`;
    const WORK_EFFORTS_PRESET_SCRIPT = `/assets/dinext_common/js/presets/projects-work-efforts-table.js?v=${DINEXT_AG_GRID_BUILD}`;
    const modulePromises = {};

    const MODULE_SCRIPTS = {
        "forecast-dom": `/assets/dinext_common/js/ag-grid/forecast-dom.js?v=${DINEXT_AG_GRID_BUILD}`,
        "tree-report": `/assets/dinext_common/js/ag-grid/tree-report.js?v=${DINEXT_AG_GRID_BUILD}`
    };

    function ensureAgGrid() {
        return loader.ensureAgGridCommunity();
    }

    function ensureFeatureStyles(feature) {
        return loader.ensureFeatureStyles(feature);
    }

    function loadModuleScript(moduleName) {
        const url = MODULE_SCRIPTS[moduleName];
        if (!url) {
            return Promise.reject(new Error(`Unknown DinextAgGrid module: ${moduleName}`));
        }

        if (moduleName === "forecast-dom" && window.DinextAgGrid && window.DinextAgGrid.ForecastDomCell) {
            return Promise.resolve();
        }
        if (moduleName === "tree-report" && window.DinextAgGrid && window.DinextAgGrid.TreeReport) {
            return Promise.resolve();
        }

        if (!modulePromises[moduleName]) {
            const globalCheck = () => {
                if (moduleName === "forecast-dom") {
                    return !!(window.DinextAgGrid && window.DinextAgGrid.ForecastDomCell);
                }
                if (moduleName === "tree-report") {
                    return !!(window.DinextAgGrid && window.DinextAgGrid.TreeReport);
                }
                return false;
            };

            modulePromises[moduleName] = loader.loadScriptOnce(url, globalCheck).then(() => {
                if (!globalCheck()) {
                    throw new Error(`DinextAgGrid module "${moduleName}" не загрузился`);
                }
            });
        }

        return modulePromises[moduleName];
    }

    function ensureModules(modules) {
        const names = Array.isArray(modules) ? modules : [modules];
        const ordered = ["forecast-dom", "tree-report"].filter(name => names.includes(name));
        const extras = names.filter(name => !ordered.includes(name));

        return ensureAgGrid().then(() => {
            let chain = Promise.resolve();
            [...ordered, ...extras].forEach(moduleName => {
                chain = chain.then(() => loadModuleScript(moduleName));
            });
            return chain;
        });
    }

    const AG_GRID_PROFILES = {
        "flat-grid": { modules: [] },
        "tree-dom": { modules: ["forecast-dom", "tree-report"] },
        "tree-readonly": {
            modules: ["tree-report"],
            domainScript: "presets/projects-workload-table.js"
        }
    };

    const AG_GRID_SCENARIOS = {
        "flat-grid": { kind: "profile", profile: "flat-grid", defaultFeature: "timesheet" },
        "tree-dom": { kind: "profile", profile: "tree-dom" },
        "tree-readonly": { kind: "profile", profile: "tree-readonly" },
        "budget-tree": { kind: "tree-dom" },
        "work-efforts": { kind: "preset", preset: "workEfforts", defaultFeature: "work-efforts" },
        "workload-report": { kind: "profile", profile: "tree-readonly", defaultFeature: "workload-report" },
        "project-workload": { kind: "profile", profile: "tree-readonly", defaultFeature: "project-workload" }
    };

    function ensureCoreStack() {
        let chain = ensureAgGrid();

        if (!window.DinextAgGrid || typeof window.DinextAgGrid.Table !== "function") {
            if (window.DinextAgGridCoreBootstrap && typeof window.DinextAgGridCoreBootstrap.ensureCore === "function") {
                chain = chain.then(() => window.DinextAgGridCoreBootstrap.ensureCore());
            } else {
                const tableUrl = `/assets/dinext_common/js/ag-grid/table.js?v=${DINEXT_AG_GRID_BUILD}`;
                const facadeUrl = `/assets/dinext_common/js/ag-grid/facade.js?v=${DINEXT_AG_GRID_BUILD}`;
                chain = chain
                    .then(() => loader.loadScriptOnce(
                        tableUrl,
                        () => window.DinextAgGridInternals && typeof window.DinextAgGridInternals.DinextAgGridTable === "function"
                    ))
                    .then(() => loader.loadScriptOnce(
                        facadeUrl,
                        () => window.DinextAgGrid && typeof window.DinextAgGrid.use === "function"
                    ));
            }
        }

        return chain;
    }

    function ensureBudgetTreePreset() {
        return loader.loadScriptOnce(
            BUDGET_TREE_SCRIPT,
            () => !!(window.DinextAgGrid && window.DinextAgGrid.presets && window.DinextAgGrid.presets.budgetTree)
        );
    }

    function ensureWorkEffortsPresetScript() {
        return loader.loadScriptOnce(
            WORK_EFFORTS_PRESET_SCRIPT,
            () => !!(
                window.DinextAgGrid
                && window.DinextAgGrid.presets
                && window.DinextAgGrid.presets.workEfforts
                && typeof window.DinextAgGrid.presets.workEfforts.ensureReady === "function"
            )
        );
    }

    function ensureTreeDomStack() {
        return ensureCoreStack()
            .then(() => ensureModules(["forecast-dom", "tree-report"]))
            .then(() => ensureBudgetTreePreset());
    }

    function loadProfileChain(profileName, options = {}) {
        const profile = AG_GRID_PROFILES[profileName];
        if (!profile) {
            return Promise.reject(new Error(`Unknown DinextAgGrid profile: ${profileName}`));
        }

        let chain = ensureCoreStack();

        if (profile.modules.length) {
            chain = chain.then(() => ensureModules(profile.modules));
        }

        if (options.feature) {
            chain = chain.then(() => { ensureFeatureStyles(options.feature); });
        }

        if (profile.domainScript) {
            const url = `/assets/dinext_common/js/${profile.domainScript}?v=${DINEXT_AG_GRID_BUILD}`;
            chain = chain.then(() => loader.loadScriptOnce(
                url,
                () => {
                    const preset = window.DinextAgGrid
                        && window.DinextAgGrid.presets
                        && window.DinextAgGrid.presets.workload;
                    return !!(preset && preset.Table);
                }
            ));
        }

        return chain;
    }

    function ensurePresetReady(presetName) {
        const preset = window.DinextAgGrid
            && window.DinextAgGrid.presets
            && window.DinextAgGrid.presets[presetName];
        const ready = preset && typeof preset.ensureReady === "function"
            ? preset.ensureReady()
            : Promise.resolve(preset && preset.Table);
        return ready.then(TableClass => {
            if (!TableClass) {
                throw new Error(`DinextAgGrid.presets.${presetName} не готов`);
            }
            return TableClass;
        });
    }

    function useScenario(scenario, options = {}) {
        const spec = AG_GRID_SCENARIOS[scenario];
        if (!spec) {
            return Promise.reject(new Error(`Unknown DinextAgGrid scenario: ${scenario}`));
        }

        const opts = Object.assign({}, options);
        if (spec.defaultFeature != null && opts.feature == null) {
            opts.feature = spec.defaultFeature;
        }

        if (spec.kind === "profile") {
            return loadProfileChain(spec.profile, opts);
        }

        if (spec.kind === "tree-dom") {
            let chain = ensureTreeDomStack();
            if (opts.feature) {
                chain = chain.then(() => { ensureFeatureStyles(opts.feature); });
            }
            return chain;
        }

        if (spec.kind === "preset") {
            let chain = ensureTreeDomStack();
            if (spec.defaultFeature) {
                chain = chain.then(() => { ensureFeatureStyles(spec.defaultFeature); });
            }
            if (spec.preset === "workEfforts") {
                chain = chain.then(() => ensureWorkEffortsPresetScript());
            }
            return chain.then(() => ensurePresetReady(spec.preset));
        }

        return Promise.reject(new Error(`Invalid DinextAgGrid scenario: ${scenario}`));
    }

    function getScenarioTable(scenario) {
        if (!AG_GRID_SCENARIOS[scenario]) {
            throw new Error(`Unknown DinextAgGrid scenario: ${scenario}`);
        }

        if (scenario === "flat-grid") {
            if (!window.DinextAgGrid || typeof window.DinextAgGrid.Table !== "function") {
                throw new Error("DinextAgGrid.Table не загружен (scenario: flat-grid)");
            }
            return window.DinextAgGrid.Table;
        }

        if (scenario === "tree-dom") {
            if (!window.DinextAgGrid || typeof window.DinextAgGrid.TreeReport !== "function") {
                throw new Error("DinextAgGrid.TreeReport не загружен (scenario: tree-dom)");
            }
            return window.DinextAgGrid.TreeReport;
        }

        if (scenario === "budget-tree") {
            const preset = window.DinextAgGrid && window.DinextAgGrid.presets && window.DinextAgGrid.presets.budgetTree;
            if (!preset || typeof preset.Table === "undefined") {
                throw new Error("DinextAgGrid.presets.budgetTree не загружен (scenario: budget-tree)");
            }
            return preset.Table;
        }

        if (scenario === "work-efforts") {
            const preset = window.DinextAgGrid && window.DinextAgGrid.presets && window.DinextAgGrid.presets.workEfforts;
            if (!preset || !preset.Table) {
                throw new Error("DinextAgGrid.presets.workEfforts не загружен (scenario: work-efforts)");
            }
            return preset.Table;
        }

        if (scenario === "tree-readonly" || scenario === "workload-report" || scenario === "project-workload") {
            const preset = window.DinextAgGrid && window.DinextAgGrid.presets && window.DinextAgGrid.presets.workload;
            if (!preset || !preset.Table) {
                throw new Error("DinextAgGrid.presets.workload не загружен (scenario: " + scenario + ")");
            }
            return preset.Table;
        }

        throw new Error(`DinextAgGrid scenario table resolver missing: ${scenario}`);
    }

    const I = window.DinextAgGridInternals = window.DinextAgGridInternals || {};
    I.MODULE_SCRIPTS = MODULE_SCRIPTS;
    I.ensureAgGrid = ensureAgGrid;
    I.ensureFeatureStyles = ensureFeatureStyles;
    I.loadModuleScript = loadModuleScript;
    I.ensureModules = ensureModules;
    I.AG_GRID_PROFILES = AG_GRID_PROFILES;
    I.AG_GRID_SCENARIOS = AG_GRID_SCENARIOS;
    I.useScenario = useScenario;
    I.getScenarioTable = getScenarioTable;
})();
