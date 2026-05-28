(function() {
    const CACHE_BUSTER = "?v=iss-865-tree-v6";
    const BOOTSTRAP_URL = "/assets/dinext_projects/js/ag_grid/bootstrap.js" + CACHE_BUSTER;
    const WORKLOAD_URL = "/assets/dinext_projects/js/project_workload/projects-workload-ag-grid.js" + CACHE_BUSTER;

    let loadPromise = null;

    function loadScriptOnce(url) {
        const existing = document.querySelector(`script[src="${url}"]`);
        if (existing) {
            return new Promise((resolve, reject) => {
                existing.addEventListener("load", resolve, { once: true });
                existing.addEventListener("error", reject, { once: true });
            });
        }

        return new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = url;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function loadModules() {
        if (window.ProjectsWorkloadAgGrid
            && window.ProjectsWorkloadAgGrid !== shim
            && typeof window.ProjectsWorkloadAgGrid.ensure === "function") {
            return Promise.resolve(window.ProjectsWorkloadAgGrid);
        }

        if (!loadPromise) {
            loadPromise = loadScriptOnce(BOOTSTRAP_URL)
                .then(() => loadScriptOnce(WORKLOAD_URL))
                .then(() => {
                    const api = window.ProjectsWorkloadAgGrid;
                    if (!api || api === shim || typeof api.ensure !== "function") {
                        throw new Error("ProjectsWorkloadAgGrid не загрузился из dinext_projects");
                    }
                    return api;
                });
        }

        return loadPromise;
    }

    const shim = {
        ensure() {
            return loadModules().then(api => api.ensure());
        }
    };

    if (!window.ProjectsWorkloadAgGrid || window.ProjectsWorkloadAgGrid === shim) {
        window.ProjectsWorkloadAgGrid = shim;
    }
})();
