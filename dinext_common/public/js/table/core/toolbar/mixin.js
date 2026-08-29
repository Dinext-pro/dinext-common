import { findAgGridRootElement, findGridMountElement } from "../shared/utils.js";
import { TOOLBAR_ICON_SVG } from "./icons.js";
import {
    normalizeToolbarItem,
    resolveToolbarFlag,
    resolveToolbarValue
} from "./utils.js";
import {
    parseUiPersistRaw,
    readUiPersistRaw,
    writeUiPersist
} from "./persist.js";
import { resolveToolbarItems } from "./presets.js";

const TOOLBAR_DEFAULTS = {
    enabled: true,
    /** Show toolbar panel by default (pin). Flip false to start collapsed. */
    defaultPinned: true,
    /**
     * Keep toolbar pinned; unpin control disabled.
     * Persist still stores filter; pin state forced on.
     */
    lockPinned: false,
    /**
     * Opt-in localStorage key suffix for UI snapshot (pin + filter).
     * Storage: `dinext-table:toolbar:${persistKey}` → JSON `{ pinned, filter }`.
     * Per-table: unique key (e.g. `work-efforts:${project}`).
     */
    persistKey: null,
    presets: ["history", "tree", "fullscreen"],
    items: []
};

/**
 * Table command toolbar: floating trigger, in-flow slide-down panel, preset actions.
 */
export const ToolbarMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._toolbarEl = null;
        this._toolbarPanelEl = null;
        this._toolbarTriggerEl = null;
        this._toolbarPinned = false;
        this._toolbarOpen = false;
        this._toolbarCustomItems = [];
        this._toolbarItemsOverride = null;
        /** @type {Map<string, HTMLElement>} reuse hosts across renderToolbarItems */
        this._toolbarCustomHosts = new Map();
    }

    destroyFeatures() {
        this.destroyToolbarListeners();
        this.clearToolbarDomClasses();
        this._toolbarCustomHosts?.clear();
        this._toolbarCustomHosts = null;
        this._toolbarEl = null;
        this._toolbarPanelEl = null;
        this._toolbarTriggerEl = null;
        super.destroyFeatures();
    }

    getToolbarOptions() {
        return { ...TOOLBAR_DEFAULTS, ...(this.options.toolbar || {}) };
    }

    isToolbarEnabled() {
        return !!this.getToolbarOptions().enabled;
    }

    getToolbarItems() {
        if (this._toolbarItemsOverride != null) {
            return this._toolbarItemsOverride;
        }
        return [...resolveToolbarItems(this, this.getToolbarOptions()), ...this._toolbarCustomItems];
    }

    registerToolbarItem(item) {
        this._toolbarCustomItems = [
            ...this._toolbarCustomItems,
            normalizeToolbarItem(
                { ...item, zone: item?.zone || "custom" },
                this._toolbarCustomItems.length
            )
        ];
        this.renderToolbarItems();
    }

    setToolbarItems(items) {
        this._toolbarItemsOverride = (items || []).map((item, index) => normalizeToolbarItem(item, index));
        this.renderToolbarItems();
    }

    isToolbarPinned() {
        return this._toolbarPinned;
    }

    isToolbarPinLocked() {
        return !!this.getToolbarOptions().lockPinned;
    }

    isToolbarOpen() {
        return this._toolbarOpen;
    }

    /**
     * Load pin + filter snapshot from localStorage (`toolbar.persistKey`).
     * Legacy `"1"`/`"0"` still supported. Filter part applied via FilterMixin hook.
     */
    loadToolbarPersistedState() {
        const opts = this.getToolbarOptions();
        const defaultPinned = !!opts.defaultPinned;
        const lockPinned = !!opts.lockPinned;
        this._uiPersistFilter = null;

        if (!opts.persistKey) {
            this._toolbarPinned = lockPinned || defaultPinned;
            return;
        }

        const raw = readUiPersistRaw(opts.persistKey);
        if (raw == null) {
            this._toolbarPinned = lockPinned || defaultPinned;
            return;
        }

        const parsed = parseUiPersistRaw(raw);
        this._uiPersistFilter = parsed.filter;
        this._toolbarPinned = lockPinned
            ? true
            : (parsed.pinned != null ? parsed.pinned : defaultPinned);
    }

    /** Persist pin + filter UI/state (same key as pin-only legacy). */
    saveToolbarPersistedState() {
        this.saveUiPersistedState();
    }

    saveUiPersistedState() {
        if (this._uiPersistRestoring) {
            return;
        }
        const persistKey = this.getToolbarOptions().persistKey;
        if (!persistKey) {
            return;
        }
        writeUiPersist(persistKey, {
            pinned: !!this._toolbarPinned,
            filter: {
                active: !!this._filterRowOpen,
                state: typeof this.getFilter === "function" ? this.getFilter() : {}
            }
        });
    }

    afterGridCreated() {
        // Persist key lives on toolbar.*; restore pin + filter before inner afterGridCreated.
        this._uiPersistRestoring = true;
        this.loadToolbarPersistedState();
        this.applyLoadedUiPersistFilter?.();
        this._uiPersistRestoring = false;

        super.afterGridCreated();
        if (this.isToolbarEnabled()) {
            this.ensureToolbarDom();
            this.syncToolbarState();
        }
    }

    ensureToolbarDom() {
        if (this._toolbarEl || !this.container) {
            return;
        }

        const gridMount = findGridMountElement(this.container);
        const gridHost = findAgGridRootElement(this.container);
        const flexHost = gridMount || gridHost;
        if (flexHost) {
            flexHost.classList.add("dinext-table-grid-host");
        }

        const toolbar = document.createElement("div");
        toolbar.className = "dinext-table-toolbar";

        const trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "dinext-table-toolbar-trigger";
        trigger.setAttribute("aria-label", "Table menu");
        trigger.setAttribute("aria-haspopup", "true");
        trigger.innerHTML = TOOLBAR_ICON_SVG.menu;
        trigger.addEventListener("click", event => this.handleToolbarTriggerClick(event));

        const panel = document.createElement("div");
        panel.className = "dinext-table-toolbar-panel";
        panel.setAttribute("role", "toolbar");

        toolbar.appendChild(panel);
        toolbar.appendChild(trigger);

        if (gridMount) {
            this.container.insertBefore(toolbar, gridMount);
        } else {
            this.container.prepend(toolbar);
        }

        this._toolbarEl = toolbar;
        this._toolbarTriggerEl = trigger;
        this._toolbarPanelEl = panel;

        this.renderToolbarItems();
        this.bindToolbarListeners();
        this.syncToolbarDomPlacement();
    }

    syncToolbarDomPlacement() {
        if (!this._toolbarEl || !this.container) {
            return;
        }

        const gridMount = findGridMountElement(this.container);
        if (gridMount && this._toolbarEl.nextElementSibling !== gridMount) {
            this.container.insertBefore(this._toolbarEl, gridMount);
        }
    }

    bindToolbarListeners() {
        this.destroyToolbarListeners();
        this._onToolbarDocumentMouseDown = (event) => {
            if (!this._toolbarOpen || this._toolbarPinned) {
                return;
            }
            const target = event.target;
            if (this._toolbarEl?.contains(target)) {
                return;
            }
            this.closeToolbarMenu();
        };
        this._onToolbarDocumentKeyDown = (event) => {
            if (event.key === "Escape") {
                this.closeToolbarMenu();
            }
        };
        document.addEventListener("mousedown", this._onToolbarDocumentMouseDown);
        document.addEventListener("keydown", this._onToolbarDocumentKeyDown);
    }

    destroyToolbarListeners() {
        if (this._onToolbarDocumentMouseDown) {
            document.removeEventListener("mousedown", this._onToolbarDocumentMouseDown);
            this._onToolbarDocumentMouseDown = null;
        }
        if (this._onToolbarDocumentKeyDown) {
            document.removeEventListener("keydown", this._onToolbarDocumentKeyDown);
            this._onToolbarDocumentKeyDown = null;
        }
    }

    clearToolbarDomClasses() {
        this.container?.classList.remove(
            "dinext-table--toolbar-enabled",
            "dinext-table--toolbar-pinned",
            "dinext-table--toolbar-open"
        );
    }

    syncToolbarState() {
        if (!this.container || !this.isToolbarEnabled()) {
            return;
        }
        this.container.classList.add("dinext-table--toolbar-enabled");
        this.container.classList.toggle("dinext-table--toolbar-pinned", this._toolbarPinned);
        this.container.classList.toggle("dinext-table--toolbar-open", this._toolbarOpen && !this._toolbarPinned);
        if (this._toolbarTriggerEl) {
            this._toolbarTriggerEl.setAttribute("aria-expanded", String(this._toolbarOpen || this._toolbarPinned));
        }
        this.syncToolbarDomPlacement();
    }

    handleToolbarTriggerClick(event) {
        event.preventDefault();
        event.stopPropagation();
        if (this._toolbarPinned) {
            return;
        }
        this._toolbarOpen = !this._toolbarOpen;
        this.syncToolbarState();
        if (this._toolbarOpen) {
            this.renderToolbarItems();
        }
    }

    closeToolbarMenu() {
        if (!this._toolbarOpen) {
            return;
        }
        this._toolbarOpen = false;
        this.syncToolbarState();
    }

    setToolbarPinned(pinned, { persist = true } = {}) {
        if (this.isToolbarPinLocked()) {
            pinned = true;
        }
        this._toolbarPinned = !!pinned;
        if (this._toolbarPinned) {
            this._toolbarOpen = false;
        }
        if (persist) {
            this.saveToolbarPersistedState();
        }
        this.syncToolbarState();
    }

    toggleToolbarPinned() {
        this.setToolbarPinned(!this._toolbarPinned);
    }

    getToolbarActionContext(event) {
        return {
            table: this,
            api: this.api,
            event,
            closeToolbar: () => this.closeToolbarMenu()
        };
    }

    createToolbarPinButton() {
        const locked = this.isToolbarPinLocked();
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dinext-table-toolbar-item dinext-table-toolbar-item--pin";
        button.setAttribute("role", "button");
        button.disabled = locked;
        button.title = locked
            ? "Toolbar always visible"
            : this._toolbarPinned
                ? "Unpin toolbar"
                : "Pin toolbar";
        button.innerHTML = this._toolbarPinned
            ? TOOLBAR_ICON_SVG.unpin
            : TOOLBAR_ICON_SVG.pin;

        button.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (locked) {
                return;
            }
            this.toggleToolbarPinned();
            this.renderToolbarItems();
        });
        return button;
    }

    createToolbarItemButton(item) {
        const ctx = this.getToolbarActionContext();
        if (resolveToolbarFlag(item.hidden, ctx)) {
            return null;
        }

        const button = document.createElement("button");
        button.type = "button";
        button.className = "dinext-table-toolbar-item";
        if (item.align === "end") {
            button.classList.add("dinext-table-toolbar-item--end");
        }
        button.setAttribute("role", "button");
        const title = resolveToolbarValue(item.title, ctx, "")
            || resolveToolbarValue(item.label, ctx, "");
        button.title = title;
        button.disabled = resolveToolbarFlag(item.disabled, ctx);
        const isActive = resolveToolbarFlag(item.active, ctx);
        button.classList.toggle("dinext-table-toolbar-item--active", isActive);
        button.setAttribute("aria-pressed", String(isActive));

        const iconSvg = resolveToolbarValue(item.iconSvg, ctx, null);
        const iconClass = resolveToolbarValue(item.icon, ctx, null);
        if (iconSvg) {
            const icon = document.createElement("span");
            icon.className = "dinext-table-toolbar-item-icon";
            icon.setAttribute("aria-hidden", "true");
            icon.innerHTML = iconSvg;
            button.appendChild(icon);
        } else if (iconClass) {
            const icon = document.createElement("span");
            icon.className = `dinext-table-toolbar-item-icon ${iconClass}`;
            icon.setAttribute("aria-hidden", "true");
            button.appendChild(icon);
        }
        const labelText = resolveToolbarValue(item.label, ctx, "");
        if (labelText) {
            const label = document.createElement("span");
            label.className = "dinext-table-toolbar-item-label";
            label.textContent = labelText;
            button.appendChild(label);
        }

        button.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (button.disabled) {
                return;
            }
            item.onClick?.(this.getToolbarActionContext(event));
            if (!this._toolbarPinned) {
                this.closeToolbarMenu();
            }
        });
        return button;
    }

    createToolbarItemCheckbox(item) {
        const ctx = this.getToolbarActionContext();
        if (resolveToolbarFlag(item.hidden, ctx)) {
            return null;
        }

        const wrap = document.createElement("label");
        wrap.className = "dinext-table-toolbar-item dinext-table-toolbar-item--checkbox";
        if (item.align === "end") {
            wrap.classList.add("dinext-table-toolbar-item--end");
        }
        wrap.title = item.title || item.label || "";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.className = "dinext-table-toolbar-checkbox-input";
        input.disabled = resolveToolbarFlag(item.disabled, ctx);
        input.checked = resolveToolbarFlag(item.checked, ctx);
        input.indeterminate = resolveToolbarFlag(item.indeterminate, ctx);
        input.setAttribute("aria-label", item.title || item.label || "Toggle");

        input.addEventListener("click", (event) => {
            event.stopPropagation();
        });
        input.addEventListener("change", (event) => {
            event.stopPropagation();
            if (input.disabled) {
                return;
            }
            item.onChange?.({
                ...this.getToolbarActionContext(event),
                checked: !!input.checked
            });
            // Keep menu open while multi-selecting rows (pinned or not).
            this.renderToolbarItems();
        });

        wrap.appendChild(input);
        if (item.label) {
            const label = document.createElement("span");
            label.className = "dinext-table-toolbar-item-label";
            label.textContent = item.label;
            wrap.appendChild(label);
        }
        return wrap;
    }

    /**
     * Mount host for `type: "custom"` — reuse by id across refreshes.
     * @returns {HTMLElement|null}
     */
    createToolbarItemCustom(item) {
        const ctx = this.getToolbarActionContext();
        if (resolveToolbarFlag(item.hidden, ctx)) {
            return null;
        }

        const id = item.id || "custom";
        let host = this._toolbarCustomHosts?.get(id);
        if (!host) {
            host = document.createElement("div");
            host.className = "dinext-table-toolbar-custom";
            host.dataset.toolbarCustomId = id;
            this._toolbarCustomHosts?.set(id, host);
        }
        if (item.align === "end") {
            host.classList.add("dinext-table-toolbar-custom--end");
        } else {
            host.classList.remove("dinext-table-toolbar-custom--end");
        }

        const renderCtx = {
            ...ctx,
            host
        };

        if (typeof item.render === "function") {
            const result = item.render(renderCtx);
            if (result instanceof HTMLElement && result !== host) {
                if (host.firstChild !== result || host.childNodes.length !== 1) {
                    host.replaceChildren(result);
                }
            }
        } else if (item.element instanceof HTMLElement) {
            if (host.firstChild !== item.element || host.childNodes.length !== 1) {
                host.replaceChildren(item.element);
            }
        }

        return host;
    }

    appendToolbarItem(groupEl, item, usedCustomIds) {
        if (item.type === "separator") {
            const sep = document.createElement("div");
            sep.className = "dinext-table-toolbar-separator";
            sep.setAttribute("role", "separator");
            groupEl.appendChild(sep);
            return;
        }
        if (item.type === "custom") {
            const el = this.createToolbarItemCustom(item);
            if (el) {
                usedCustomIds?.add(item.id || "custom");
                groupEl.appendChild(el);
            }
            return;
        }
        const el = item.type === "checkbox"
            ? this.createToolbarItemCheckbox(item)
            : this.createToolbarItemButton(item);
        if (el) {
            groupEl.appendChild(el);
        }
    }

    /** Drop custom hosts that are no longer in the item list. */
    pruneToolbarCustomHosts(usedIds) {
        if (!this._toolbarCustomHosts) {
            return;
        }
        for (const id of [...this._toolbarCustomHosts.keys()]) {
            if (!usedIds.has(id)) {
                this._toolbarCustomHosts.delete(id);
            }
        }
    }

    createToolbarZoneSeparator() {
        const sep = document.createElement("div");
        sep.className = "dinext-table-toolbar-separator dinext-table-toolbar-separator--zone";
        sep.setAttribute("role", "separator");
        sep.setAttribute("aria-orientation", "vertical");
        return sep;
    }

    renderToolbarItems() {
        if (!this._toolbarPanelEl) {
            return;
        }

        const items = this.getToolbarItems();
        const ctx = this.getToolbarActionContext();
        const isVisible = (item) => !resolveToolbarFlag(item.hidden, ctx);
        const endItems = items.filter(item => item.align === "end" && isVisible(item));
        const domainItems = items.filter(
            item => item.align !== "end" && item.zone === "custom" && isVisible(item)
        );
        const primaryItems = items.filter(
            item => item.align !== "end" && item.zone !== "custom"
        );
        const usedCustomIds = new Set();

        this._toolbarPanelEl.replaceChildren();
        this._toolbarPanelEl.classList.toggle(
            "dinext-table-toolbar-panel--has-custom",
            domainItems.length > 0
        );

        const primaryGroup = document.createElement("div");
        primaryGroup.className = "dinext-table-toolbar-group dinext-table-toolbar-group--primary";
        primaryGroup.appendChild(this.createToolbarPinButton());
        for (const item of primaryItems) {
            this.appendToolbarItem(primaryGroup, item, usedCustomIds);
        }
        this._toolbarPanelEl.appendChild(primaryGroup);

        if (domainItems.length) {
            this._toolbarPanelEl.appendChild(this.createToolbarZoneSeparator());

            const customGroup = document.createElement("div");
            customGroup.className = "dinext-table-toolbar-group dinext-table-toolbar-group--custom";
            for (const item of domainItems) {
                this.appendToolbarItem(customGroup, item, usedCustomIds);
            }
            this._toolbarPanelEl.appendChild(customGroup);

            if (endItems.length) {
                this._toolbarPanelEl.appendChild(this.createToolbarZoneSeparator());
            }
        }

        if (endItems.length) {
            const endGroup = document.createElement("div");
            endGroup.className = "dinext-table-toolbar-group dinext-table-toolbar-group--end";
            for (const item of endItems) {
                this.appendToolbarItem(endGroup, item, usedCustomIds);
            }
            this._toolbarPanelEl.appendChild(endGroup);
        }

        this.pruneToolbarCustomHosts(usedCustomIds);
    }

    refreshToolbar() {
        this.renderToolbarItems();
    }

    handleSetOption(key, value) {
        if (key === "toolbar") {
            this.options.toolbar = value;
            if (this.isToolbarEnabled()) {
                this.ensureToolbarDom();
                this.renderToolbarItems();
                this.syncToolbarState();
            } else {
                this.closeToolbarMenu();
                this.destroyToolbarListeners();
                this.clearToolbarDomClasses();
                this._toolbarCustomHosts?.clear();
                this._toolbarEl?.remove();
                this._toolbarEl = null;
                this._toolbarPanelEl = null;
                this._toolbarTriggerEl = null;
            }
            return true;
        }
        return super.handleSetOption?.(key, value) ?? false;
    }
};
