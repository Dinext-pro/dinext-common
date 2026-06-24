/* Copyright (c) 2026, Dinext — generic ECharts helpers (ISS-2026-00002). */
frappe.provide("DinextCharts");

(function () {
	const ECHARTS_ASSET = "/assets/dinext_common/js/echarts.min.js";
	let loadPromise = null;

	function isDarkMode() {
		return document.documentElement.getAttribute("data-theme") === "dark";
	}

	DinextCharts.getThemeName = function () {
		return isDarkMode() ? "dark" : undefined;
	};

	DinextCharts.load = function () {
		if (window.echarts) {
			return Promise.resolve(window.echarts);
		}
		if (!loadPromise) {
			loadPromise = new Promise((resolve, reject) => {
				frappe.require([ECHARTS_ASSET], () => {
					if (window.echarts) {
						resolve(window.echarts);
					} else {
						reject(new Error("ECharts failed to load"));
					}
				});
			});
		}
		return loadPromise;
	};

	function createAgGridAlignedPanel($parent, opts) {
		const title = opts.title || __("Chart");
		const collapsed = !!opts.collapsed;
		const height = opts.height || "280px";
		const panelClass =
			opts.panelClass || "dinext-chart-panel dinext-chart-panel--ag-grid-aligned";

		const $panel = $(`
			<div class="${panelClass}">
				<div class="dinext-chart-panel__body" style="${collapsed ? "display:none;" : ""}">
					<div class="dinext-chart-panel__sync-grid">
						<div class="dinext-chart-panel__gutter-chrome">
							<div class="dinext-chart-panel__gutter-head">
								<button type="button" class="btn btn-xs btn-default dinext-chart-panel__toggle" title="${__("Expand/collapse")}">
									<span class="dinext-chart-panel__toggle-icon">${collapsed ? "▸" : "▾"}</span>
								</button>
								<span class="dinext-chart-panel__title">${frappe.utils.escape_html(title)}</span>
							</div>
							<div class="dinext-chart-panel__gutter-filters"></div>
						</div>
						<div class="dinext-chart-panel__gutter-yaxis"></div>
						<div class="dinext-chart-panel__viewport">
							<div class="dinext-chart-panel__chart-track">
								<div class="dinext-chart-panel__chart"></div>
							</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo($parent);

		const $body = $panel.find(".dinext-chart-panel__body");
		const $chartEl = $panel.find(".dinext-chart-panel__chart");
		$chartEl.css({ width: "100%", height });

		const panel = {
			$panel,
			$body,
			$chartEl,
			$syncGrid: $panel.find(".dinext-chart-panel__sync-grid"),
			$gutterChrome: $panel.find(".dinext-chart-panel__gutter-chrome"),
			$gutterHead: $panel.find(".dinext-chart-panel__gutter-head"),
			$gutterFilters: $panel.find(".dinext-chart-panel__gutter-filters"),
			$gutterYaxis: $panel.find(".dinext-chart-panel__gutter-yaxis"),
			$viewport: $panel.find(".dinext-chart-panel__viewport"),
			$chartTrack: $panel.find(".dinext-chart-panel__chart-track"),
			_chartHeight: height,
			setCollapsed(value) {
				$body.toggle(!value);
				$panel.find(".dinext-chart-panel__toggle-icon").text(value ? "▸" : "▾");
			},
		};

		$panel.find(".dinext-chart-panel__toggle").on("click", () => {
			const isHidden = !$body.is(":visible");
			$body.toggle(isHidden);
			$panel.find(".dinext-chart-panel__toggle-icon").text(isHidden ? "▾" : "▸");
			const chart = $chartEl.data("dinext-chart-instance");
			if (isHidden && chart && !chart.isDisposed()) {
				chart.resize();
			}
		});

		return panel;
	}

	DinextCharts.createPanel = function ($parent, options) {
		const opts = options || {};
		if (opts.layout === "ag-grid-aligned") {
			return createAgGridAlignedPanel($parent, opts);
		}
		const title = opts.title || __("Chart");
		const collapsed = !!opts.collapsed;
		const panelClass = opts.panelClass || "dinext-chart-panel";

		const $panel = $(`
			<div class="${panelClass}">
				<div class="dinext-chart-panel__header">
					<button type="button" class="btn btn-xs btn-default dinext-chart-panel__toggle" title="${__("Expand/collapse")}">
						<span class="dinext-chart-panel__toggle-icon">${collapsed ? "▸" : "▾"}</span>
					</button>
					<span class="dinext-chart-panel__title">${frappe.utils.escape_html(title)}</span>
					<div class="dinext-chart-panel__extra"></div>
				</div>
				<div class="dinext-chart-panel__body" style="${collapsed ? "display:none;" : ""}">
					<div class="dinext-chart-panel__chart"></div>
				</div>
			</div>
		`).appendTo($parent);

		const $body = $panel.find(".dinext-chart-panel__body");
		const $chartEl = $panel.find(".dinext-chart-panel__chart");
		$chartEl.css({ width: "100%", height: opts.height || "280px" });

		$panel.find(".dinext-chart-panel__toggle").on("click", () => {
			const isHidden = !$body.is(":visible");
			$body.toggle(isHidden);
			$panel.find(".dinext-chart-panel__toggle-icon").text(isHidden ? "▾" : "▸");
			if (isHidden && $chartEl.data("dinext-chart-instance")) {
				$chartEl.data("dinext-chart-instance").resize();
			}
		});

		return {
			$panel,
			$body,
			$chartEl,
			$extra: $panel.find(".dinext-chart-panel__extra"),
			setCollapsed(value) {
				$body.toggle(!value);
				$panel.find(".dinext-chart-panel__toggle-icon").text(value ? "▸" : "▾");
			},
		};
	};

	DinextCharts.mount = function (chartEl, option) {
		const el = chartEl instanceof jQuery ? chartEl.get(0) : chartEl;
		if (!el) {
			return null;
		}
		DinextCharts.dispose(el);
		const chart = window.echarts.init(el, DinextCharts.getThemeName());
		chart.setOption(option, { notMerge: true });
		$(el).data("dinext-chart-instance", chart);
		requestAnimationFrame(() => {
			if (chart && !chart.isDisposed()) {
				chart.resize();
			}
		});
		return chart;
	};

	DinextCharts.dispose = function (chartEl) {
		const el = chartEl instanceof jQuery ? chartEl.get(0) : chartEl;
		if (!el) {
			return;
		}
		const existing = $(el).data("dinext-chart-instance");
		if (existing && !existing.isDisposed()) {
			existing.dispose();
		}
		$(el).removeData("dinext-chart-instance");
		$("body > .ec-extension").remove();
	};

	DinextCharts.bindResize = function (chart, chartEl) {
		if (!chart) {
			return () => {};
		}
		const el = chartEl instanceof jQuery ? chartEl.get(0) : chartEl;
		const onResize = () => {
			if (chart && !chart.isDisposed()) {
				chart.resize();
			}
		};
		$(window).on("resize.dinext-charts", onResize);
		if (window.ResizeObserver && el) {
			const ro = new ResizeObserver(onResize);
			ro.observe(el);
			return () => {
				$(window).off("resize.dinext-charts", onResize);
				ro.disconnect();
			};
		}
		return () => $(window).off("resize.dinext-charts", onResize);
	};
})();
