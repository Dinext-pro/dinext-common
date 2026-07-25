/**
 * Workspace sidebar icon-rail + animated hover flyout (position:fixed overlay).
 * Desktop only. Enabled when frappe.boot.dinext_workspace_sidebar_hover_expand is true.
 */
(function () {
	const STORAGE_KEY = "dinext_workspace_sidebar_collapsed";
	const BODY_COLLAPSED = "dinext-ws-sidebar-collapsed";
	const BODY_HOVER_OPEN = "dinext-ws-sidebar-hover-open";
	const EXPAND_DELAY_MS = 300;
	const COLLAPSE_DELAY_MS = 500;

	if (!frappe.boot || !frappe.boot.dinext_workspace_sidebar_hover_expand) {
		return;
	}

	let expand_timer = null;
	let collapse_timer = null;
	let active_side_section = null;
	let active_page = null;
	let suppress_open = false;

	function is_mobile() {
		return frappe.utils.is_xs() || frappe.utils.is_sm();
	}

	function has_desk_sidebar(page) {
		return page && page.wrapper && $(page.wrapper).find(".desk-sidebar").length > 0;
	}

	function get_pinned_collapsed() {
		return localStorage.getItem(STORAGE_KEY) === "1";
	}

	function get_list_sidebar($side_section) {
		return $side_section.find(".list-sidebar.overlay-sidebar").first();
	}

	function clear_flyout_rect($side_section) {
		const $list = $side_section
			? get_list_sidebar($side_section)
			: $(".layout-side-section:has(.desk-sidebar) .list-sidebar.overlay-sidebar");
		$list.each(function () {
			this.style.removeProperty("top");
			this.style.removeProperty("left");
			this.style.removeProperty("height");
			this.style.removeProperty("--dinext-ws-rail-pad-left");
			this.style.removeProperty("padding-left");
			this.style.removeProperty("transition");
		});
	}

	function sync_rail_pad($side_section, $list) {
		const side_el = $side_section.get(0);
		const list_el = $list.get(0);
		if (!side_el || !list_el) {
			return;
		}
		const page = side_el.closest(".page-container") || (active_page && active_page.wrapper);
		const toggle =
			(page && page.querySelector(".page-head .sidebar-toggle-btn")) ||
			document.querySelector(".page-head .sidebar-toggle-btn");
		if (!toggle) {
			return;
		}
		const icon = toggle.querySelector("svg") || toggle;
		const pad = Math.round(icon.getBoundingClientRect().left - side_el.getBoundingClientRect().left);
		const clamped = Math.min(24, Math.max(16, pad));
		const pad_px = `${clamped}px`;
		list_el.style.setProperty("--dinext-ws-rail-pad-left", pad_px);
		list_el.style.paddingLeft = pad_px;
	}

	function position_flyout($side_section) {
		if (!$side_section || !$side_section.length) {
			return;
		}
		const el = $side_section.get(0);
		const $list = get_list_sidebar($side_section);
		if (!el || !$list.length) {
			return;
		}
		const rect = el.getBoundingClientRect();
		const top = Math.max(rect.top, 0);
		const bottom = Math.min(rect.bottom, window.innerHeight);
		$list.css({
			top: `${top}px`,
			left: `${rect.left}px`,
			height: `${Math.max(bottom - top, 100)}px`,
		});
		if (
			document.body.classList.contains(BODY_COLLAPSED) &&
			!document.body.classList.contains(BODY_HOVER_OPEN) &&
			!is_mobile()
		) {
			sync_rail_pad($side_section, $list);
		}
	}

	function sync_collapsed_flyout($side_section) {
		if (!$side_section || !$side_section.length) {
			return;
		}
		if (!document.body.classList.contains(BODY_COLLAPSED) || is_mobile()) {
			return;
		}
		active_side_section = $side_section;
		position_flyout($side_section);
	}

	function open_hover_flyout($side_section) {
		active_side_section = $side_section;
		position_flyout($side_section);
		document.body.classList.add(BODY_HOVER_OPEN);
		requestAnimationFrame(() => position_flyout($side_section));
	}

	function close_hover_flyout($side_section) {
		document.body.classList.remove(BODY_HOVER_OPEN);
		const $side = $side_section || active_side_section;
		// Keep fixed rail positioned while still collapsed (width animates via CSS).
		if ($side && document.body.classList.contains(BODY_COLLAPSED) && !is_mobile()) {
			position_flyout($side);
			active_side_section = $side;
		} else {
			clear_flyout_rect($side);
			active_side_section = null;
		}
	}

	function set_pinned_collapsed(collapsed, $side_section) {
		localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
		if (!collapsed) {
			document.body.classList.remove(BODY_COLLAPSED, BODY_HOVER_OPEN);
			clear_flyout_rect($side_section || active_side_section);
			active_side_section = null;
			return;
		}

		const $list = $side_section ? get_list_sidebar($side_section) : $();
		const list_el = $list.get(0);
		// Seed pad + freeze transitions before body class so first paint is never pad=0.
		if (list_el) {
			list_el.style.setProperty("--dinext-ws-rail-pad-left", "16px");
			list_el.style.paddingLeft = "16px";
			list_el.style.transition = "none";
		}
		document.body.classList.add(BODY_COLLAPSED);
		if (!$side_section) {
			return;
		}
		sync_collapsed_flyout($side_section);
		if (list_el) {
			void list_el.offsetWidth;
		}
		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				if (!document.body.classList.contains(BODY_COLLAPSED) || is_mobile()) {
					return;
				}
				if (list_el) {
					list_el.style.removeProperty("transition");
				}
				sync_collapsed_flyout($side_section);
			});
		});
		setTimeout(() => {
			if (document.body.classList.contains(BODY_COLLAPSED) && !is_mobile()) {
				sync_collapsed_flyout($side_section);
			}
		}, 50);
	}

	function clear_timers() {
		if (expand_timer) {
			clearTimeout(expand_timer);
			expand_timer = null;
		}
		if (collapse_timer) {
			clearTimeout(collapse_timer);
			collapse_timer = null;
		}
	}

	function update_toggle_icon(page) {
		const $toggle = $(page.wrapper).find(".page-head .sidebar-toggle-btn");
		const $icon = $toggle.find(".sidebar-toggle-icon");
		if (!$icon.length) {
			return;
		}
		const collapsed = document.body.classList.contains(BODY_COLLAPSED);
		$icon.html(
			frappe.utils.icon(collapsed ? "es-line-sidebar-expand" : "es-line-sidebar-collapse", "md")
		);
	}

	function restore_frappe_toggle(page) {
		if (!page || !page.wrapper) {
			return;
		}
		const $toggle = $(page.wrapper).find(".page-head .sidebar-toggle-btn");
		$toggle.off("click.dinextWsSidebar");
		// Re-bind standard Frappe desktop/mobile toggle if our handler was attached.
		$toggle.off("click");
		const sidebar_wrapper = $(page.wrapper).find(".layout-side-section");
		$toggle.on("click", () => {
			if (frappe.utils.is_xs() || frappe.utils.is_sm()) {
				page.setup_overlay_sidebar();
			} else {
				sidebar_wrapper.toggle();
			}
			$(document.body).trigger("toggleSidebar");
			page.update_sidebar_icon();
		});
	}

	function bind_hover($side_section) {
		if ($side_section.data("dinext-ws-hover")) {
			return;
		}
		$side_section.data("dinext-ws-hover", 1);

		const $list = get_list_sidebar($side_section);

		function schedule_open() {
			if (is_mobile()) {
				return;
			}
			if (!document.body.classList.contains(BODY_COLLAPSED)) {
				return;
			}
			if (suppress_open) {
				return;
			}
			clearTimeout(collapse_timer);
			collapse_timer = null;
			expand_timer = setTimeout(() => {
				open_hover_flyout($side_section);
			}, EXPAND_DELAY_MS);
		}

		function schedule_close() {
			if (is_mobile()) {
				return;
			}
			if (!document.body.classList.contains(BODY_COLLAPSED)) {
				return;
			}
			suppress_open = false;
			clearTimeout(expand_timer);
			expand_timer = null;
			collapse_timer = setTimeout(() => {
				close_hover_flyout($side_section);
			}, COLLAPSE_DELAY_MS);
		}

		$side_section.on("mouseenter.dinextWsSidebar", schedule_open);
		$side_section.on("mouseleave.dinextWsSidebar", schedule_close);
		$list.on("mouseenter.dinextWsSidebar", schedule_open);
		$list.on("mouseleave.dinextWsSidebar", schedule_close);
	}

	// Capture phase: Frappe sidebar links often stopPropagation on click.
	function on_sidebar_item_click_capture(e) {
		const anchor = e.target && e.target.closest && e.target.closest(
			".layout-side-section .desk-sidebar .item-anchor"
		);
		if (!anchor) {
			return;
		}
		if (!document.body.classList.contains(BODY_COLLAPSED) || is_mobile()) {
			return;
		}
		clear_timers();
		suppress_open = true;
		const $side = active_side_section && active_side_section.length
			? active_side_section
			: $(anchor.closest(".layout-side-section"));
		close_hover_flyout($side);
	}

	document.removeEventListener("click", on_sidebar_item_click_capture, true);
	document.addEventListener("click", on_sidebar_item_click_capture, true);

	function enhance_page(page) {
		if (is_mobile() || !has_desk_sidebar(page)) {
			return;
		}

		const $wrapper = $(page.wrapper);
		const $side = $wrapper.find(".layout-side-section");
		if (!$side.length) {
			return;
		}

		active_page = page;
		$side.show();

		set_pinned_collapsed(get_pinned_collapsed(), $side);
		update_toggle_icon(page);
		bind_hover($side);
		sync_collapsed_flyout($side);

		const $toggle = $wrapper.find(".page-head .sidebar-toggle-btn");
		$toggle.off("click");
		$toggle.on("click.dinextWsSidebar", () => {
			if (is_mobile()) {
				restore_frappe_toggle(page);
				page.setup_overlay_sidebar();
				$(document.body).trigger("toggleSidebar");
				return;
			}
			const next_collapsed = !document.body.classList.contains(BODY_COLLAPSED);
			set_pinned_collapsed(next_collapsed, $side);
			update_toggle_icon(page);
			if (next_collapsed) {
				sync_collapsed_flyout($side);
			}
			$(document.body).trigger("toggleSidebar");
		});
	}

	function cleanup(opts) {
		const restore_toggle = !opts || opts.restore_toggle !== false;
		const page = active_page;
		clear_timers();
		suppress_open = false;
		document.body.classList.remove(BODY_COLLAPSED, BODY_HOVER_OPEN);
		clear_flyout_rect();
		active_side_section = null;
		$(".layout-side-section").off(".dinextWsSidebar").removeData("dinext-ws-hover");
		$(".list-sidebar.overlay-sidebar").off(".dinextWsSidebar");
		$(".page-head .sidebar-toggle-btn").off("click.dinextWsSidebar");
		if (restore_toggle && page) {
			restore_frappe_toggle(page);
		}
	}

	const original_setup_sidebar_toggle = frappe.ui.Page.prototype.setup_sidebar_toggle;
	frappe.ui.Page.prototype.setup_sidebar_toggle = function () {
		original_setup_sidebar_toggle.apply(this, arguments);
		if (!is_mobile() && has_desk_sidebar(this)) {
			enhance_page(this);
		}
	};

	const original_update_sidebar_icon = frappe.ui.Page.prototype.update_sidebar_icon;
	frappe.ui.Page.prototype.update_sidebar_icon = function () {
		if (
			frappe.boot.dinext_workspace_sidebar_hover_expand &&
			!is_mobile() &&
			has_desk_sidebar(this) &&
			document.body.classList.contains(BODY_COLLAPSED)
		) {
			update_toggle_icon(this);
			return;
		}
		return original_update_sidebar_icon.apply(this, arguments);
	};

	function patch_workspace() {
		if (!frappe.views || !frappe.views.Workspace) {
			return false;
		}
		if (frappe.views.Workspace.prototype._dinext_ws_sidebar_patched) {
			return true;
		}

		const original_prepare = frappe.views.Workspace.prototype.prepare_container;
		frappe.views.Workspace.prototype.prepare_container = function () {
			original_prepare.apply(this, arguments);
			enhance_page(this.page);
		};

		const original_show = frappe.views.Workspace.prototype.show;
		frappe.views.Workspace.prototype.show = function () {
			const result = original_show.apply(this, arguments);
			enhance_page(this.page);
			return result;
		};

		frappe.views.Workspace.prototype._dinext_ws_sidebar_patched = true;
		return true;
	}

	function reposition_if_needed() {
		if (
			document.body.classList.contains(BODY_COLLAPSED) &&
			!is_mobile() &&
			active_side_section &&
			active_side_section.length
		) {
			position_flyout(active_side_section);
		}
	}

	function on_viewport_change() {
		reposition_if_needed();
		const route = frappe.get_route && frappe.get_route();
		if (is_mobile()) {
			if (document.body.classList.contains(BODY_COLLAPSED) || active_page) {
				cleanup({ restore_toggle: true });
			}
			return;
		}
		if (route && route[0] === "Workspaces" && frappe.workspace && frappe.workspace.page) {
			enhance_page(frappe.workspace.page);
		}
	}

	$(window).on("resize.dinextWsSidebar", on_viewport_change);
	document.addEventListener("scroll", reposition_if_needed, true);

	patch_workspace();

	function on_desk_ready() {
		patch_workspace();
		if (!is_mobile() && frappe.workspace && frappe.workspace.page) {
			enhance_page(frappe.workspace.page);
		}
	}

	$(on_desk_ready);
	$(document).on("app_ready", on_desk_ready);

	$(document).on("page-change", () => {
		const route = frappe.get_route();
		if (!route || route[0] !== "Workspaces") {
			cleanup({ restore_toggle: false });
			active_page = null;
		} else if (!is_mobile() && frappe.workspace && frappe.workspace.page) {
			enhance_page(frappe.workspace.page);
		}
	});
})();
