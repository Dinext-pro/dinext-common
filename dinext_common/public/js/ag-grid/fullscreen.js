// DinextAgGrid fullscreen toolbar state (load before table.js).
(function() {
    const I = window.DinextAgGridInternals = window.DinextAgGridInternals || {};

    if (!I.fullscreenTables) {
        I.fullscreenTables = new Set();
    }

    function syncFullscreenBodyClass() {
        if (document.body) {
            document.body.classList.toggle(
                "dinext-ag-grid-table-fullscreen-active",
                I.fullscreenTables.size > 0
            );
        }
    }

    I.syncFullscreenBodyClass = syncFullscreenBodyClass;
})();
