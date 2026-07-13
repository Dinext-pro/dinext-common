const THEME_CLASS = "dinext-table";
const THEME_CLASS_DARK = "dinext-table-dark";

function isFrappeDarkTheme() {
    const root = document.documentElement;
    const resolved = root.getAttribute("data-theme");
    if (resolved === "dark" || resolved === "light") {
        return resolved === "dark";
    }
    return root.getAttribute("data-theme-mode") === "dark";
}

/** AG Grid 35 programmatic theme needs resolved colors, not raw CSS var()/color-mix(). */
function resolveCssColor(value, element) {
    if (value == null || value === "") {
        return value;
    }
    const str = String(value);
    if (!str.includes("var(") && !str.includes("color-mix(")) {
        return str;
    }

    const probeHost = document.documentElement;
    const probe = document.createElement("div");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    probe.style.pointerEvents = "none";
    probe.style.backgroundColor = str;
    probeHost.appendChild(probe);
    const resolved = getComputedStyle(probe).backgroundColor;
    probe.remove();

    return resolved && resolved !== "rgba(0, 0, 0, 0)" ? resolved : str;
}

export const ThemeMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this.applyContainerClasses();
        this.watchTheme();
    }

    afterGridCreated() {
        super.afterGridCreated();
        this.applyTheme();
    }

    destroyFeatures() {
        this.destroyTheme();
        super.destroyFeatures();
    }

    applyContainerClasses() {
        this.container.classList.add(THEME_CLASS);
        this.syncTableRadiusCssVar();
        this.syncAgGridLayoutCssVars();
    }

    buildAgGridTheme() {
        const themeOpts = this.options.theme || {};
        const columnBorder = themeOpts.columnBorder !== false;
        const el = this.container;

        const params = {
            backgroundColor: resolveCssColor("var(--card-bg)", el),
            foregroundColor: resolveCssColor("var(--text-color)", el),
            borderColor: resolveCssColor(
                "color-mix(in srgb, var(--text-color) 15%, transparent)",
                el
            ),
            headerBackgroundColor: resolveCssColor(
                "color-mix(in srgb, var(--card-bg), var(--text-color) 2%)",
                el
            ),
            // Quartz: columnBorder = body only; header needs headerColumnBorder
            columnBorder,
            headerColumnBorder: themeOpts.headerColumnBorder !== undefined
                ? themeOpts.headerColumnBorder
                : columnBorder
        };

        // Official Quartz theme params (no CSS hacks on .ag-cell)
        if (themeOpts.spacing != null) {
            params.spacing = themeOpts.spacing;
        }
        if (themeOpts.cellHorizontalPadding != null) {
            params.cellHorizontalPadding = themeOpts.cellHorizontalPadding;
        }

        const radius = themeOpts.borderRadius ?? themeOpts.wrapperBorderRadius ?? 4;
        params.borderRadius = radius;
        params.wrapperBorderRadius = themeOpts.wrapperBorderRadius ?? themeOpts.borderRadius ?? radius;

        return window.agGrid.themeQuartz.withParams(params);
    }

    applyTheme() {
        const isDark = isFrappeDarkTheme();
        this.container.classList.toggle(THEME_CLASS_DARK, isDark);
        this.syncTableRadiusCssVar();
        this.syncAgGridLayoutCssVars();
        if (this.api) {
            this.api.setGridOption("theme", this.buildAgGridTheme());
        }
    }

    syncAgGridLayoutCssVars() {
        const themeOpts = this.options.theme || {};
        const radius = themeOpts.borderRadius ?? themeOpts.wrapperBorderRadius;

        if (radius != null) {
            this.container.style.setProperty(
                "--dinext-table-radius",
                typeof radius === "number" ? `${radius}px` : String(radius)
            );
        }

        if (themeOpts.cellHorizontalPadding != null) {
            this.container.style.setProperty(
                "--ag-cell-horizontal-padding",
                `${themeOpts.cellHorizontalPadding}px`
            );
        } else {
            this.container.style.removeProperty("--ag-cell-horizontal-padding");
        }
    }

    syncTableRadiusCssVar() {
        const themeOpts = this.options.theme || {};
        const radius = themeOpts.borderRadius ?? themeOpts.wrapperBorderRadius;
        if (radius == null) {
            this.container.style.removeProperty("--dinext-table-radius");
            return;
        }
        this.container.style.setProperty(
            "--dinext-table-radius",
            typeof radius === "number" ? `${radius}px` : String(radius)
        );
    }

    watchTheme() {
        this.themeObserver = new MutationObserver(() => this.applyTheme());
        this.themeObserver.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-theme", "data-theme-mode"]
        });
    }

    destroyTheme() {
        if (this.themeObserver) {
            this.themeObserver.disconnect();
            this.themeObserver = null;
        }
    }
};
