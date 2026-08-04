(function() {
    const AG_GRID_VERSION = "35.2.1";
    const AG_GRID_JS = "/assets/dinext_common/js/ag-grid-community.min.js";
    const AG_GRID_CSS = [
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

    function ensure() {
        if (window.agGrid && typeof window.agGrid.createGrid === "function") {
            return Promise.resolve(window.agGrid);
        }

        if (!agGridPromise) {
            AG_GRID_CSS.forEach(loadStyleOnce);
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

    window.DinextAgGrid = {
        VERSION: AG_GRID_VERSION,
        ensure,
        loadScriptOnce,
        loadStyleOnce
    };
})();
