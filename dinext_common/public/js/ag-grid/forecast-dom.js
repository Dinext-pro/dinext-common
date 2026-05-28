(function() {
    const INPUT_CLASS = "dinext-ag-grid-forecast-input";

    function translate(text) {
        return typeof window.__ === "function" ? window.__(text) : text;
    }

    function mergeCallbacks(first, second) {
        if (typeof first !== "function") return second;
        if (typeof second !== "function") return first;
        return function() {
            const args = arguments;
            first.apply(this, args);
            return second.apply(this, args);
        };
    }

    function defaultGetNavKey(target) {
        if (!target) return "";
        const group = target.closest(".budget-group, .we-columns-container, .work-efforts-group");
        const roleWrap = target.closest(".we-role-value");
        const parts = [];

        if (group) {
            ["year", "month", "account", "task", "role"].forEach(attr => {
                const value = group.getAttribute(`data-${attr}`);
                if (value != null && value !== "") parts.push(value);
            });
        }
        if (roleWrap) {
            const role = roleWrap.getAttribute("data-role");
            if (role != null && role !== "") parts.push(role);
        }

        const colHost = target.closest("[col-id]");
        if (colHost && colHost.getAttribute("col-id")) {
            parts.push(colHost.getAttribute("col-id"));
        }

        return parts.join("|");
    }

    function getAgApi(table) {
        return table && table.api ? table.api : null;
    }

    function getAgRowElement(table, rowIndex) {
        const api = getAgApi(table);
        if (api && typeof api.getDisplayedRowAtIndex === "function") {
            const node = api.getDisplayedRowAtIndex(rowIndex);
            if (node && typeof api.getRowElement === "function") {
                const rowEl = api.getRowElement({ rowIndex });
                if (rowEl) return rowEl;
            }
        }

        const root = table && table.container ? table.container : document;
        return root.querySelector(`.ag-row[row-index="${rowIndex}"]`)
            || root.querySelector(`.ag-row[aria-rowindex="${rowIndex + 1}"]`);
    }

    function getCellElement(table, params) {
        if (!params || !params.column) return null;

        const api = params.api || getAgApi(table);
        const colKey = typeof params.column.getColId === "function"
            ? params.column.getColId()
            : params.column.colId;

        if (api && typeof api.getCellElement === "function") {
            const cellEl = api.getCellElement({ rowIndex: params.rowIndex, colKey });
            if (cellEl) return cellEl;
        }

        const rowEl = getAgRowElement(table, params.rowIndex);
        if (!rowEl || !colKey) return null;
        return rowEl.querySelector(`[col-id="${colKey}"]`)
            || rowEl.querySelector(`[col-id='${colKey}']`);
    }

    function normalizeText(value) {
        return String(value == null ? "" : value).replace(/\s+/g, "").trim();
    }

    class ForecastDomCell {
        constructor() {
            this.table = null;
            this.options = {};
            this.lastFocusedParams = null;
            this.activeEdit = null;
            this.boundContainerKeydown = null;
            this.previousOnCellFocused = null;
        }

        bindTable(table, options = {}) {
            if (!table || !table.container) {
                throw new Error("ForecastDomCell.bindTable: table with container is required");
            }

            this.unbindTable();

            this.table = table;
            this.options = Object.assign({
                selector: ".editable-forecast",
                getNavKey: defaultGetNavKey
            }, options);

            this.attachToTable(table);
            this.boundContainerKeydown = event => this.handleContainerKeyDown(event);
            table.container.addEventListener("keydown", this.boundContainerKeydown, true);

            return this;
        }

        unbindTable() {
            if (this.activeEdit) {
                this.cancelEdit();
            }

            if (this.table && this.boundContainerKeydown) {
                this.table.container.removeEventListener("keydown", this.boundContainerKeydown, true);
            }

            if (this.table) {
                this.table.options.onCellFocused = this.previousOnCellFocused;
            }

            this.boundContainerKeydown = null;
            this.previousOnCellFocused = null;
            this.lastFocusedParams = null;
            this.table = null;
        }

        attachToTable(table) {
            this.previousOnCellFocused = table.options.onCellFocused;
            table.options.onCellFocused = mergeCallbacks(
                this.previousOnCellFocused,
                params => this.onCellFocused(params)
            );
        }

        onCellFocused(params) {
            this.lastFocusedParams = params || null;
        }

        isEditableTarget(target, params) {
            if (!target) return false;
            if (typeof this.options.isEditable === "function") {
                return !!this.options.isEditable(target, params);
            }
            return true;
        }

        getNavKey(target) {
            const getter = this.options.getNavKey || defaultGetNavKey;
            return getter(target, this.lastFocusedParams);
        }

        listRowEditables(rowIndex, params) {
            const rowEl = getAgRowElement(this.table, rowIndex);
            if (!rowEl) return [];

            const selector = this.options.selector || ".editable-forecast";
            return Array.from(rowEl.querySelectorAll(selector))
                .filter(target => this.isEditableTarget(target, params || this.lastFocusedParams));
        }

        findEditableInRow(rowIndex, navKey, params) {
            const editables = this.listRowEditables(rowIndex, params);
            if (!navKey) return editables[0] || null;
            return editables.find(target => this.getNavKey(target) === navKey) || null;
        }

        findFirstEditableInFocusedCell(params) {
            const cellEl = getCellElement(this.table, params || this.lastFocusedParams);
            if (!cellEl) return null;

            const selector = this.options.selector || ".editable-forecast";
            const targets = Array.from(cellEl.querySelectorAll(selector));
            return targets.find(target => this.isEditableTarget(target, params)) || null;
        }

        handleContainerKeyDown(event) {
            if (!this.table || this.table.options && this.table.options.readonly) return;
            if (this.activeEdit) return;

            const params = this.lastFocusedParams;
            if (!params || !event || !event.key) return;

            if (event.key === "Escape") return;

            if (event.key === "Enter") {
                const target = this.findFirstEditableInFocusedCell(params);
                if (target) {
                    event.preventDefault();
                    event.stopPropagation();
                    this.startEdit(target, params);
                }
                return;
            }

            const printable = event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
            if (!printable) return;

            const target = this.findFirstEditableInFocusedCell(params);
            if (!target) return;

            event.preventDefault();
            event.stopPropagation();
            this.startEdit(target, params, event.key);
        }

        startEdit(target, params, initialChar) {
            if (!target || this.activeEdit) return;
            if (target.querySelector("input, textarea, select")) return;

            const displayText = normalizeText(target.textContent);
            const input = document.createElement("input");
            input.className = INPUT_CLASS;
            input.type = "number";
            input.min = "0";
            input.step = "any";
            input.setAttribute("inputmode", "decimal");

            if (initialChar != null && initialChar !== "") {
                input.value = initialChar;
            } else {
                input.value = displayText;
            }

            const originalHtml = target.innerHTML;
            target.textContent = "";
            target.appendChild(input);

            this.activeEdit = {
                input,
                target,
                params: params || this.lastFocusedParams,
                originalHtml,
                originalText: displayText,
                navKey: this.getNavKey(target)
            };

            if (typeof this.options.onActivate === "function") {
                this.options.onActivate(target, this.activeEdit.params, input);
            }

            this.activeEdit.onInputKeydown = event => this.handleInputKeyDown(event);
            input.addEventListener("keydown", this.activeEdit.onInputKeydown);
            input.focus();
            input.select();
        }

        handleInputKeyDown(event) {
            if (!this.activeEdit || !event) return;
            if (event.target !== this.activeEdit.input) return;

            if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                this.cancelEdit();
                return;
            }

            if (event.key === "Tab" || event.key === "Enter") {
                event.preventDefault();
                event.stopPropagation();
                const moveDown = event.key === "Enter" && !event.shiftKey;
                const moveForward = event.key === "Tab" && !event.shiftKey;
                this.commitEdit({ moveDown, moveForward, moveBackward: event.shiftKey });
            }
        }

        cancelEdit() {
            if (!this.activeEdit) return;

            const { target, originalHtml, input, onInputKeydown } = this.activeEdit;
            if (input && onInputKeydown) {
                input.removeEventListener("keydown", onInputKeydown);
            }
            target.innerHTML = originalHtml;
            this.activeEdit = null;
        }

        commitEdit(navigation) {
            if (!this.activeEdit) return;

            const { input, target, params, navKey, onInputKeydown } = this.activeEdit;
            if (input && onInputKeydown) {
                input.removeEventListener("keydown", onInputKeydown);
            }

            const context = typeof this.options.getContextFromInput === "function"
                ? this.options.getContextFromInput(input)
                : { input, target, params, navKey };

            let saved = true;
            if (typeof this.options.onSave === "function") {
                const result = this.options.onSave(input, context);
                if (result === false) {
                    saved = false;
                }
            }

            this.activeEdit = null;

            if (!saved) {
                return;
            }

            if (!navigation) return;

            if (navigation.moveForward) {
                this.activateNextInRow(target, params, navKey, 1);
                return;
            }

            if (navigation.moveBackward) {
                this.activateNextInRow(target, params, navKey, -1);
                return;
            }

            if (navigation.moveDown) {
                this.activateNextRowSameColumn(params, navKey);
            }
        }

        activateNextInRow(currentTarget, params, navKey, direction) {
            const rowIndex = params && params.rowIndex;
            if (rowIndex == null) return;

            const editables = this.listRowEditables(rowIndex, params);
            const currentIndex = editables.indexOf(currentTarget);
            let nextIndex = currentIndex + direction;

            if (currentIndex < 0 && direction > 0) {
                nextIndex = 0;
            }

            if (nextIndex < 0 || nextIndex >= editables.length) {
                return;
            }

            const nextTarget = editables[nextIndex];
            this.focusAgCellForTarget(params, nextTarget);
            this.startEdit(nextTarget, params);
        }

        activateNextRowSameColumn(params, navKey) {
            if (!params || params.rowIndex == null) return;

            const nextRowIndex = params.rowIndex + 1;
            const nextTarget = this.findEditableInRow(nextRowIndex, navKey, params);
            if (!nextTarget) return;

            const nextParams = Object.assign({}, params, { rowIndex: nextRowIndex });
            this.focusAgCellForTarget(nextParams, nextTarget);
            this.startEdit(nextTarget, nextParams);
        }

        focusAgCellForTarget(params, target) {
            const api = getAgApi(this.table);
            if (!api || !params || !params.column) return;

            const rowIndex = params.rowIndex;
            const colKey = typeof params.column.getColId === "function"
                ? params.column.getColId()
                : params.column.colId;

            if (typeof api.setFocusedCell === "function") {
                api.setFocusedCell(rowIndex, colKey);
            }

            this.lastFocusedParams = Object.assign({}, params, { rowIndex });
        }
    }

    window.DinextAgGrid = window.DinextAgGrid || {};
    window.DinextAgGrid.ForecastDomCell = ForecastDomCell;
    window.DinextAgGrid.adapters = window.DinextAgGrid.adapters || {};
    window.DinextAgGrid.adapters.ForecastDomCell = ForecastDomCell;
})();
