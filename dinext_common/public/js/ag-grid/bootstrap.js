(function() {
    const AG_GRID_VERSION = "35.2.1";
    const AG_GRID_JS = "/assets/dinext_common/js/ag-grid-community.min.js";
    // Class-theme CSS — ONLY for legacy grids (ag-theme-quartz*).
    // DinextTable uses AG Grid Theming API and must NOT load these files:
    // they match [class*=ag-theme-] and break programmatic theme tokens.
    const AG_GRID_LEGACY_CSS = [
        "/assets/dinext_common/css/ag-grid.css",
        "/assets/dinext_common/css/ag-theme-quartz.css"
    ];

    let agGridPromise = null;

    function loadScriptOnce(url, globalCheck) {
        if (globalCheck && globalCheck()) {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[src="${url}"]`);
            if (existing) {
                existing.addEventListener("load", resolve, { once: true });
                existing.addEventListener("error", reject, { once: true });
                if (globalCheck && globalCheck()) resolve();
                return;
            }

            const script = document.createElement("script");
            script.src = url;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function loadStyleOnce(url) {
        if (document.querySelector(`link[href="${url}"]`)) return;

        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        document.head.appendChild(link);
    }

    /** Load JS only. Safe to call from DinextTable / new tables. */
    function ensure() {
        if (window.agGrid && typeof window.agGrid.createGrid === "function") {
            return Promise.resolve(window.agGrid);
        }

        if (!agGridPromise) {
            agGridPromise = loadScriptOnce(
                AG_GRID_JS,
                () => window.agGrid && typeof window.agGrid.createGrid === "function"
            ).then(() => {
                if (!window.agGrid || typeof window.agGrid.createGrid !== "function") {
                    throw new Error(__("Failed to load AG Grid"));
                }
                return window.agGrid;
            });
        }

        return agGridPromise;
    }

    /** Class-theme CSS for legacy ProjectsWorkloadAgGrid / ag-theme-quartz grids. */
    function ensureLegacyThemeCss() {
        AG_GRID_LEGACY_CSS.forEach(loadStyleOnce);
        // Re-enable if DinextTable previously disabled the links.
        document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
            const href = link.getAttribute("href") || "";
            if (AG_GRID_LEGACY_CSS.some((url) => href.includes(url))) {
                link.disabled = false;
            }
        });
    }

    window.DinextAgGrid = {
        VERSION: AG_GRID_VERSION,
        ensure,
        ensureLegacyThemeCss,
        loadScriptOnce,
        loadStyleOnce
    };
})();
