// DinextAgGrid cell editors (load after utils.js).
(function() {
    const I = window.DinextAgGridInternals = window.DinextAgGridInternals || {};

    class DinextAgGridTextEditor {
        init(params) {
            this.params = params;
            this.input = document.createElement("input");
            this.input.className = "dinext-ag-grid-editor";
            this.input.type = "text";
            this.input.value = params.charPress || (params.value == null ? "" : String(params.value));

            this.input.addEventListener("keydown", event => {
                if (event.key === "Enter" || event.key === "Tab") {
                    const table = params.context && params.context.dinextTable;
                    if (table) {
                        table.lastEditKey = event.key;
                        table.lastEditDirection = event.key === "Tab" && event.shiftKey ? -1 : 1;
                    }
                    event.preventDefault();
                    params.stopEditing(false);
                } else if (event.key === "Escape") {
                    params.stopEditing(true);
                }
            });
        }

        afterGuiAttached() {
            this.input.focus();
            this.input.select();
        }

        getGui() {
            return this.input;
        }

        getValue() {
            return this.input.value;
        }
    }

    class DinextAgGridNumericEditor extends DinextAgGridTextEditor {
        init(params) {
            super.init(params);
            this.input.type = "number";
            this.input.inputMode = "decimal";
        }

        getValue() {
            const value = this.input.value;
            if (value === "") return null;
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : value;
        }
    }

    I.DinextAgGridTextEditor = DinextAgGridTextEditor;
    I.DinextAgGridNumericEditor = DinextAgGridNumericEditor;
})();
