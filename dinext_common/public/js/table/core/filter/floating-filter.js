/**
 * AG Grid floating filter UI bound to DinextTable filter state.
 * Parent column uses NoopFilter — row visibility is owned by FilterMixin.
 */

export class DinextNoopFilter {
    init() {}

    isFilterActive() {
        return false;
    }

    doesFilterPass() {
        return true;
    }

    getModel() {
        return null;
    }

    setModel() {}
}

export class DinextTextFloatingFilter {
    init(params) {
        this.params = params;
        this._debounceTimer = null;

        this.eGui = document.createElement("div");
        this.eGui.className = "dinext-table-floating-filter";

        this.input = document.createElement("input");
        this.input.type = "search";
        this.input.className = "dinext-table-floating-filter-input";
        this.input.setAttribute("autocomplete", "off");
        this.input.setAttribute("spellcheck", "false");

        const field = params?.column?.getColDef?.()?.field;
        const headerName = params?.column?.getColDef?.()?.headerName;
        this.input.setAttribute(
            "aria-label",
            headerName ? __("Filter {0}", [headerName]) : __("Filter column")
        );
        // Empty placeholder keeps :placeholder-shown for hover lupa CSS.
        this.input.placeholder = " ";

        const table = params?.context?.dinextTable;
        if (field && table && typeof table.getFilter === "function") {
            this.input.value = table.getFilter()[field] || "";
        }

        this._onInput = () => {
            if (!field || !table || typeof table.setFilterField !== "function") {
                return;
            }
            const value = this.input.value;
            clearTimeout(this._debounceTimer);
            this._debounceTimer = setTimeout(() => {
                table.setFilterField(field, value);
            }, 150);
        };
        this.input.addEventListener("input", this._onInput);

        // Stop header-click sort / column interactions from stealing keystrokes.
        this.input.addEventListener("click", (event) => event.stopPropagation());
        this.input.addEventListener("mousedown", (event) => event.stopPropagation());
        this.input.addEventListener("keydown", (event) => event.stopPropagation());

        this.eGui.appendChild(this.input);
    }

    getGui() {
        return this.eGui;
    }

    onParentModelChanged() {
        // Parent NoopFilter never has a model; sync from table if needed.
        const field = this.params?.column?.getColDef?.()?.field;
        const table = this.params?.context?.dinextTable;
        if (!field || !table || typeof table.getFilter !== "function") {
            return;
        }
        const next = table.getFilter()[field] || "";
        if (this.input && this.input.value !== next) {
            this.input.value = next;
        }
    }

    destroy() {
        clearTimeout(this._debounceTimer);
        this._debounceTimer = null;
        if (this.input && this._onInput) {
            this.input.removeEventListener("input", this._onInput);
        }
        this.input = null;
        this.eGui = null;
        this.params = null;
    }
}
