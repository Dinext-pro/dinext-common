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

    const host = element?.isConnected ? element : document.documentElement;
    const probe = document.createElement("div");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    probe.style.pointerEvents = "none";
    probe.style.backgroundColor = str;
    host.appendChild(probe);
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
    }

    buildAgGridTheme() {
        const columnBorder = this.options.theme?.columnBorder !== false;
        const el = this.container;

        return window.agGrid.themeQuartz.withParams({
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
            columnBorder
        });
    }

    applyTheme() {
        const isDark = isFrappeDarkTheme();
        this.container.classList.toggle(THEME_CLASS_DARK, isDark);
        if (this.api) {
            this.api.setGridOption("theme", this.buildAgGridTheme());
        }
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
