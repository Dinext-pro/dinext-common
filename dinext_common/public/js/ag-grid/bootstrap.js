// Shared script loader for DinextAgGrid core (ordered IIFE chain, no ES modules).
(function() {
    const BUILD = (window.DinextAgGridLoader && window.DinextAgGridLoader.BUILD)
        || (window.DinextAgGrid && window.DinextAgGrid.build)
        || "refactor-v1";

    const BASE = `/assets/dinext_common/js/ag-grid`;

    const SCRIPTS = {
        loader: `${BASE}/loader.js?v=${BUILD}`,
        utils: `${BASE}/utils.js?v=${BUILD}`,
        "tree-cell": `${BASE}/tree-cell.js?v=${BUILD}`,
        editors: `${BASE}/editors.js?v=${BUILD}`,
        navigation: `${BASE}/navigation.js?v=${BUILD}`,
        fullscreen: `${BASE}/fullscreen.js?v=${BUILD}`,
        profiles: `${BASE}/profiles.js?v=${BUILD}`,
        table: `${BASE}/table.js?v=${BUILD}`,
        facade: `${BASE}/facade.js?v=${BUILD}`,
        "forecast-dom": `${BASE}/forecast-dom.js?v=${BUILD}`,
        "tree-report": `${BASE}/tree-report.js?v=${BUILD}`,
        "budget-tree": `/assets/dinext_common/js/presets/budget-tree.js?v=${BUILD}`
    };

    const CORE_SEQUENCE = [
        "loader",
        "utils",
        "tree-cell",
        "editors",
        "navigation",
        "fullscreen",
        "profiles",
        "table",
        "facade"
    ];

    const TREE_DOM_SEQUENCE = ["forecast-dom", "tree-report", "budget-tree"];

    function scriptReady(key) {
        const I = window.DinextAgGridInternals;

        if (key === "loader") {
            return !!(window.DinextAgGridLoader && window.DinextAgGridLoader.loadScriptOnce);
        }
        if (key === "utils") {
            return !!(I && typeof I.normalizeColumn === "function");
        }
        if (key === "tree-cell") {
            return !!(I && typeof I.buildTreeToggleHtml === "function");
        }
        if (key === "editors") {
            return !!(I && I.DinextAgGridTextEditor);
        }
        if (key === "navigation") {
            return !!(I && typeof I.getNextEditableCell === "function");
        }
        if (key === "fullscreen") {
            return !!(I && typeof I.syncFullscreenBodyClass === "function");
        }
        if (key === "profiles") {
            return !!(I && typeof I.useScenario === "function");
        }
        if (key === "table") {
            return !!(I && typeof I.DinextAgGridTable === "function");
        }
        if (key === "facade") {
            return !!(
                window.DinextAgGrid
                && typeof window.DinextAgGrid.use === "function"
                && typeof window.DinextAgGrid.Table === "function"
            );
        }
        if (key === "forecast-dom") {
            return !!(window.DinextAgGrid && window.DinextAgGrid.ForecastDomCell);
        }
        if (key === "tree-report") {
            return !!(window.DinextAgGrid && window.DinextAgGrid.TreeReport);
        }
        if (key === "budget-tree") {
            return !!(
                window.DinextAgGrid
                && window.DinextAgGrid.presets
                && window.DinextAgGrid.presets.budgetTree
            );
        }
        return false;
    }

    function loadScript(url, key) {
        if (scriptReady(key)) {
            return Promise.resolve();
        }

        const loadOnce = window.DinextAgGridLoader && window.DinextAgGridLoader.loadScriptOnce;
        if (loadOnce) {
            return loadOnce(url, () => scriptReady(key)).then(() => {
                if (!scriptReady(key)) {
                    throw new Error(`Script not ready after load: ${key}`);
                }
            });
        }

        return new Promise((resolve, reject) => {
            const path = url.split("?")[0];
            const existing = Array.from(document.scripts || []).find(script => {
                try {
                    return new URL(script.src, window.location.origin).pathname === path;
                } catch (error) {
                    return (script.getAttribute("src") || "").split("?")[0] === path;
                }
            });

            if (existing) {
                if (scriptReady(key)) {
                    resolve();
                    return;
                }
                existing.addEventListener("load", () => resolve(), { once: true });
                existing.addEventListener("error", reject, { once: true });
                return;
            }

            const script = document.createElement("script");
            script.src = url;
            script.onload = () => resolve();
            script.onerror = reject;
            document.head.appendChild(script);
        }).then(() => {
            if (!scriptReady(key)) {
                throw new Error(`Script not ready after load: ${key}`);
            }
        });
    }

    function loadSequence(keys) {
        return keys.reduce(
            (chain, key) => chain.then(() => loadScript(SCRIPTS[key], key)),
            Promise.resolve()
        );
    }

    function ensureCore() {
        if (window.DinextAgGrid && typeof window.DinextAgGrid.use === "function") {
            return Promise.resolve();
        }

        if (!window.__dinext_ag_grid_core_bootstrap) {
            window.__dinext_ag_grid_core_bootstrap = loadSequence(CORE_SEQUENCE);
        }

        return window.__dinext_ag_grid_core_bootstrap;
    }

    function ensureTreeDom() {
        if (
            window.DinextAgGrid
            && window.DinextAgGrid.TreeReport
            && window.DinextAgGrid.ForecastDomCell
            && window.DinextAgGrid.presets
            && window.DinextAgGrid.presets.budgetTree
        ) {
            return Promise.resolve();
        }

        if (!window.__dinext_ag_grid_tree_dom_bootstrap) {
            window.__dinext_ag_grid_tree_dom_bootstrap = ensureCore().then(() =>
                loadSequence(TREE_DOM_SEQUENCE)
            );
        }

        return window.__dinext_ag_grid_tree_dom_bootstrap;
    }

    window.DinextAgGridCoreBootstrap = {
        BUILD,
        SCRIPTS,
        CORE_SEQUENCE,
        TREE_DOM_SEQUENCE,
        ensureCore,
        ensureTreeDom
    };

    // Start core load when bootstrap is included via doctype_js (DinextAgGrid is async).
    if (!window.__dinext_ag_grid_core_bootstrap_kicked) {
        window.__dinext_ag_grid_core_bootstrap_kicked = true;
        ensureCore().catch(err => {
            console.error("DinextAgGrid ensureCore failed:", err);
        });
    }

    if (typeof window.ensureDinextAgGridCoreBootstrap !== "function") {
        window.ensureDinextAgGridCoreBootstrap = function ensureDinextAgGridCoreBootstrap() {
            return ensureCore().then(() => window.DinextAgGridCoreBootstrap);
        };
    }
})();
