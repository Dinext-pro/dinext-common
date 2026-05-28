(function() {
    const AG_GRID_VERSION = "35.2.1";
    const DINEXT_AG_GRID_BUILD = "refactor-v1";
    const AG_GRID_JS = "/assets/dinext_common/js/ag-grid/ag-grid-community.min.js";
    const AG_GRID_CORE_CSS = `/assets/dinext_common/css/ag-grid-core.css?v=${DINEXT_AG_GRID_BUILD}`;
    const AG_GRID_FEATURE_CSS = {
        timesheet: `/assets/dinext_common/css/ag-grid-timesheet.css?v=${DINEXT_AG_GRID_BUILD}`,
        "work-efforts": `/assets/dinext_common/css/ag-grid-work-efforts.css?v=${DINEXT_AG_GRID_BUILD}`,
        "project-workload": `/assets/dinext_common/css/ag-grid-project-workload.css?v=${DINEXT_AG_GRID_BUILD}`,
        "workload-report": `/assets/dinext_common/css/ag-grid-workload-report.css?v=${DINEXT_AG_GRID_BUILD}`
    };
    const AG_GRID_CSS = [
        "/assets/dinext_common/css/ag-grid.css",
        "/assets/dinext_common/css/ag-theme-quartz.css",
        AG_GRID_CORE_CSS
    ];

    const loadedFeatureStyles = new Set();
    let agGridPromise = null;

    function loadScriptOnce(url, globalCheck) {
        if (globalCheck && globalCheck()) {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            const existing = Array.from(document.scripts || []).find(script => {
                try {
                    return new URL(script.src, window.location.origin).pathname === url;
                } catch (error) {
                    return script.getAttribute("src") === url;
                }
            });

            if (existing) {
                if (globalCheck && globalCheck()) {
                    resolve();
                    return;
                }
                existing.addEventListener("load", resolve, { once: true });
                existing.addEventListener("error", reject, { once: true });
                return;
            }

            const script = document.createElement("script");
            script.src = url;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function stylePath(url) {
        return String(url || "").split("?")[0];
    }

    function loadStyleOnce(url) {
        const path = stylePath(url);
        const exists = Array.from(document.querySelectorAll("link[rel='stylesheet']")).some(link => {
            try {
                return new URL(link.href, window.location.origin).pathname === path;
            } catch (error) {
                return stylePath(link.getAttribute("href")) === path;
            }
        });

        if (exists) return;

        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        document.head.appendChild(link);
    }

    function ensureFeatureStyles(feature) {
        const features = Array.isArray(feature) ? feature : [feature];
        features.forEach(name => {
            const url = AG_GRID_FEATURE_CSS[name];
            if (!url || loadedFeatureStyles.has(name)) return;
            loadedFeatureStyles.add(name);
            loadStyleOnce(url);
        });
    }

    function ensureAgGridCommunity() {
        AG_GRID_CSS.forEach(loadStyleOnce);

        if (window.agGrid && typeof window.agGrid.createGrid === "function") {
            return Promise.resolve();
        }

        if (!agGridPromise) {
            agGridPromise = loadScriptOnce(
                AG_GRID_JS,
                () => window.agGrid && typeof window.agGrid.createGrid === "function"
            ).then(() => {
                if (!window.agGrid || typeof window.agGrid.createGrid !== "function") {
                    throw new Error("AG Grid не загрузился");
                }
            });
        }

        return agGridPromise;
    }

    window.DinextAgGridLoader = {
        AG_GRID_VERSION,
        BUILD: DINEXT_AG_GRID_BUILD,
        DINEXT_AG_GRID_BUILD,
        AG_GRID_JS,
        AG_GRID_CSS,
        AG_GRID_FEATURE_CSS,
        loadScriptOnce,
        loadStyleOnce,
        stylePath,
        ensureAgGridCommunity,
        ensureFeatureStyles
    };
})();
