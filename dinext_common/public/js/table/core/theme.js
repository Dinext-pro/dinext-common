const THEME_CLASS = "dinext-table";
/** Quartz + CSS chrome (`--dinext-table-radius`) share this when theme.borderRadius unset. */
const DEFAULT_BORDER_RADIUS = 4;

/**
 * Quartz `false` often leaves transparent 1px seams (gaps between heatmap fills).
 * Opt-in: only when theme flag === false we force vars / classes off.
 */
const BORDER_OFF_CSS = {
	columnBorder: ["--ag-column-border", "--ag-cell-horizontal-border"],
	headerColumnBorder: ["--ag-header-column-border"],
	rowBorder: ["--ag-row-border", "--ag-row-border-width", "--ag-row-border-color", "--ag-row-border-style"],
	headerRowBorder: ["--ag-header-row-border", "--ag-header-row-border-width", "--ag-header-row-border-color", "--ag-header-row-border-style"],
	pinnedColumnBorder: ["--ag-pinned-column-border"],
	pinnedRowBorder: ["--ag-pinned-row-border"],
};

function resolveThemeRadius(themeOpts) {
	return themeOpts.borderRadius ?? themeOpts.wrapperBorderRadius ?? DEFAULT_BORDER_RADIUS;
}

function cssLength(value) {
	return typeof value === "number" ? `${value}px` : String(value);
}

/** AG Grid 35 programmatic theme needs resolved colors, not raw CSS var()/color-mix(). */
function resolveCssColor(value) {
	if (value == null || value === "") return value;
	
	const str = String(value);
	if (!str.includes("var(") && !str.includes("color-mix(")) return str;

	const probe = document.createElement("div");
	probe.style.position = "absolute";
	probe.style.visibility = "hidden";
	probe.style.pointerEvents = "none";
	probe.style.backgroundColor = str;
	document.documentElement.appendChild(probe);
	const resolved = getComputedStyle(probe).backgroundColor;
	probe.remove();

	return resolved && resolved !== "rgba(0, 0, 0, 0)" ? resolved : str;
}

function resolveHeaderColumnBorderOn(themeOpts) {
	
	if (themeOpts.headerColumnBorder !== undefined) {
		return themeOpts.headerColumnBorder !== false;
	}
	return themeOpts.columnBorder !== false;
}

/** Prefer `{ width: 0 }` over boolean false — Quartz false can leave transparent 1px. */
function quartzBorderParam(on) {
	return on ? true : { width: 0 };
}

function borderOffCssValue(cssVar) {
	if (cssVar.endsWith("-width")) return "0px";
	if (cssVar.endsWith("-color")) return "transparent";
	if (cssVar.endsWith("-style")) return "none";
	return "none";
}

/**
 * After Quartz apply: when a border flag is `false`, force zero-width borders.
 * Vars on container + `.ag-root*` — Quartz often defines `--ag-row-border-*` on inner root.
 */
function applyBorderOffCssVars(container, themeOpts) {
	const columnOff = themeOpts.columnBorder === false;
	const headerColumnOff = !resolveHeaderColumnBorderOn(themeOpts);
	const rowOff = themeOpts.rowBorder === false;
	const headerRowOff = themeOpts.headerRowBorder === false;
	const pinnedColumnOff = themeOpts.pinnedColumnBorder === false;
	const pinnedRowOff = themeOpts.pinnedRowBorder === false;

	const off = {
		columnBorder: columnOff,
		headerColumnBorder: headerColumnOff,
		rowBorder: rowOff,
		headerRowBorder: headerRowOff,
		pinnedColumnBorder: pinnedColumnOff,
		pinnedRowBorder: pinnedRowOff,
	};

	const targets = [container];
	container.querySelectorAll(".ag-root-wrapper, .ag-root").forEach((el) => {
		targets.push(el);
	});

	for (const el of targets) {
		for (const [key, cssVars] of Object.entries(BORDER_OFF_CSS)) {
			for (const cssVar of cssVars) {
				if (off[key]) {
					el.style.setProperty(cssVar, borderOffCssValue(cssVar));
				} else {
					el.style.removeProperty(cssVar);
				}
			}
		}
	}

	container.classList.toggle("dinext-table--no-row-borders", rowOff);
	container.classList.toggle("dinext-table--no-column-borders", columnOff);
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
		this.syncThemeCssVars();
	}

	buildAgGridTheme() {
		const themeOpts = this.options.theme || {};
		const columnBorder = themeOpts.columnBorder !== false;
		const radius = resolveThemeRadius(themeOpts);

		const params = {
			backgroundColor: resolveCssColor("var(--card-bg)"),
			foregroundColor: resolveCssColor("var(--text-color)"),
			borderColor: resolveCssColor(
				// Desk-like hairline; was 15% — too heavy vs DataTable / gray borders
				"color-mix(in srgb, var(--text-color) 10%, transparent)"
			),
			headerBackgroundColor: resolveCssColor(
				"color-mix(in srgb, var(--card-bg), var(--text-color) 2%)"
			),
			// Quartz: columnBorder = body only; header needs headerColumnBorder
			columnBorder: quartzBorderParam(columnBorder),
			headerColumnBorder: quartzBorderParam(resolveHeaderColumnBorderOn(themeOpts)),
			borderRadius: radius,
			wrapperBorderRadius: themeOpts.wrapperBorderRadius
				?? themeOpts.borderRadius
				?? radius,
		};

		for (const key of [ "rowBorder", "headerRowBorder", "wrapperBorder", "pinnedColumnBorder", "pinnedRowBorder"]) {
			if (themeOpts[key] !== undefined) {
				params[key] = themeOpts[key] === false
					? { width: 0 }
					: themeOpts[key];
			}
		}

		if (themeOpts.spacing != null) {
			params.spacing = themeOpts.spacing;
		}
		if (themeOpts.cellHorizontalPadding != null) {
			params.cellHorizontalPadding = themeOpts.cellHorizontalPadding;
		}

		return window.agGrid.themeQuartz.withParams(params);
	}

	applyTheme() {
		this.syncThemeCssVars();
		if (this.api) this.api.setGridOption("theme", this.buildAgGridTheme());
		applyBorderOffCssVars(this.container, this.options.theme || {});
		// After theme class lands: stamp tokens (beats legacy ag-grid.css).
		this.syncAgThemeTokens();
	}

	syncThemeCssVars() {
		const themeOpts = this.options.theme || {};
		const radius = resolveThemeRadius(themeOpts);

		this.container.style.setProperty("--dinext-table-radius", cssLength(radius));

		if (themeOpts.cellHorizontalPadding != null) {
			this.container.style.setProperty("--ag-cell-horizontal-padding", cssLength(themeOpts.cellHorizontalPadding));
		} else {
			this.container.style.removeProperty("--ag-cell-horizontal-padding");
		}
	}

	/**
	 * Legacy `ag-grid.css` sets `--ag-background-color: #fff` on `[class*=ag-theme-]`.
	 * Theming API uses `:where(.ag-theme-params-N)` (specificity 0) and loses → white grid.
	 * Inline tokens on the params host win over that stylesheet.
	 */
	syncAgThemeTokens() {
		const host = this.container.querySelector('[class*="ag-theme-params"]');
		if (!host) return;

		const bg = resolveCssColor("var(--card-bg)");
		const fg = resolveCssColor("var(--text-color)");
		const border = resolveCssColor(
			"color-mix(in srgb, var(--text-color) 10%, transparent)"
		);
		const headerBg = resolveCssColor(
			"color-mix(in srgb, var(--card-bg), var(--text-color) 2%)"
		);

		host.style.setProperty("--ag-background-color", bg);
		host.style.setProperty("--ag-data-background-color", bg);
		host.style.setProperty("--ag-odd-row-background-color", bg);
		host.style.setProperty("--ag-foreground-color", fg);
		host.style.setProperty("--ag-data-color", fg);
		host.style.setProperty("--ag-header-foreground-color", fg);
		host.style.setProperty("--ag-header-background-color", headerBg);
		host.style.setProperty("--ag-border-color", border);
	}

	watchTheme() {
		this.themeObserver = new MutationObserver(() => this.applyTheme());
		this.themeObserver.observe(document.documentElement, {
			attributes: true,
			attributeFilter: ["data-theme", "data-theme-mode"],
		});
	}

	destroyTheme() {
		if (this.themeObserver) {
			this.themeObserver.disconnect();
			this.themeObserver = null;
		}
	}
};
