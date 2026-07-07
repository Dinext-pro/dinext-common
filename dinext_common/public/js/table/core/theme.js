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

        return window.agGrid.themeQuartz.withParams({
            backgroundColor: "var(--card-bg)",
            foregroundColor: "var(--text-color)",
            borderColor: "color-mix(in srgb, var(--text-color) 15%, transparent)",
            headerBackgroundColor: "color-mix(in srgb, var(--card-bg), var(--text-color) 2%)",
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
