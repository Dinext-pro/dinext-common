/**
 * Workspace sidebar icon-rail + animated hover flyout (position:fixed overlay).
 * Desktop only. Enabled when frappe.boot.dinext_workspace_sidebar_hover_expand is true.
 * Mounts .desk-sidebar into Workspaces native side-section, or a dedicated
 * .dinext-ws-rail-section column (56px) on other Desk routes. Geometry is CSS-only.
 */
(function () {
	const STORAGE_KEY = "dinext_workspace_sidebar_collapsed";
	const BODY_COLLAPSED = "dinext-ws-sidebar-collapsed";
	const BODY_HOVER_OPEN = "dinext-ws-sidebar-hover-open";
	const RAIL_SECTION_CLASS = "dinext-ws-rail-section";
	const EXPAND_DELAY_MS = 300;
	const COLLAPSE_DELAY_MS = 500;

	function feature_enabled() {
		return !!(frappe.boot && frappe.boot.dinext_workspace_sidebar_hover_expand);
	}

	if (frappe.boot && !feature_enabled()) {
		return;
	}

	let expand_timer = null;
	let collapse_timer = null;
	let active_side_section = null;
	let active_page = null;
	let suppress_open = false;
	let ensure_promise = null;
	let started = false;

	function is_mobile() {
		return frappe.utils.is_xs() || frappe.utils.is_sm();
	}

	function is_workspaces_route() {
		const route = frappe.get_route && frappe.get_route();
		return !!(route && route[0] === "Workspaces");
	}

	function get_route_str_safe() {
		const route = frappe.get_route && frappe.get_route();
		return Array.isArray(route) ? route.join("/") : "";
	}

	function get_pinned_collapsed() {
		return localStorage.getItem(STORAGE_KEY) === "1";
	}

	function get_workspace_list_sidebar() {
		// Prefer Workspace's jQuery ref — survives .layout-side-section.empty() detach.
		if (frappe.workspace && frappe.workspace.sidebar && frappe.workspace.sidebar.length) {
			const $list = frappe.workspace.sidebar.closest(".list-sidebar.overlay-sidebar");
			if ($list.length) {
				return $list;
			}
		}
		return $(".list-sidebar.overlay-sidebar:has(.desk-sidebar)").first();
	}

	function get_list_sidebar($side_section) {
		if (!$side_section || !$side_section.length) {
			return $();
		}
		return $side_section.find(".list-sidebar.overlay-sidebar:has(.desk-sidebar)").first();
	}

	function get_current_page() {
		// Prefer the visible page-container's Page instance (reliable after route changes).
		const visible = [...document.querySelectorAll(".page-container")].find(
			(el) => getComputedStyle(el).display !== "none"
		);
		if (visible && visible.page) {
			return visible.page;
		}
		if (frappe.container && frappe.container.page && frappe.container.page.page) {
			return frappe.container.page.page;
		}
		const route = get_route_str_safe();
		if (route && frappe.ui.pages[route]) {
			return frappe.ui.pages[route];
		}
		if (frappe.workspace && frappe.workspace.page) {
			return frappe.workspace.page;
		}
		return null;
	}

	function ensure_main_flex_col($layout) {
		const $main = $layout.children(".layout-main-section-wrapper").first();
		if ($main.length) {
			$main.removeClass("col-md-12").addClass("col");
		}
	}

	function get_workspaces_side_section($wrapper) {
		const $layout = $wrapper.find(".row.layout-main").first();
		if (!$layout.length) {
			return $();
		}
		let $side = $layout
			.children(`.layout-side-section:not(.${RAIL_SECTION_CLASS})`)
			.first();
		if ($side.length) {
			$side.show();
			return $side;
		}
		$side = $('<div class="col-lg-2 layout-side-section"></div>');
		$layout.prepend($side);
		ensure_main_flex_col($layout);
		return $side;
	}

	function get_or_create_rail_section($wrapper) {
		const $layout = $wrapper.find(".row.layout-main").first();
		if (!$layout.length) {
			return $();
		}
		let $side = $layout.children(`.layout-side-section.${RAIL_SECTION_CLASS}`).first();
		if ($side.length) {
			$side.show();
			return $side;
		}
		$side = $(
			`<div class="col-lg-2 layout-side-section ${RAIL_SECTION_CLASS}"></div>`
		);
		$layout.prepend($side);
		ensure_main_flex_col($layout);
		return $side;
	}

	function get_mount_side_section($wrapper) {
		if (is_workspaces_route()) {
			return get_workspaces_side_section($wrapper);
		}
		return get_or_create_rail_section($wrapper);
	}

	function unbind_hover($side_section) {
		if (!$side_section || !$side_section.length) {
			return;
		}
		$side_section.off(".dinextWsSidebar").removeData("dinext-ws-hover");
		get_list_sidebar($side_section).off(".dinextWsSidebar");
	}

	function remove_legacy_rail_host() {
		$("#dinext-ws-rail-host").remove();
	}

	function mount_desk_sidebar($side) {
		const $list = get_workspace_list_sidebar();
		if (!$list.length || !$side.length) {
			return $();
		}
		if ($list.parent()[0] !== $side[0]) {
			if (active_side_section && active_side_section[0] !== $side[0]) {
				unbind_hover(active_side_section);
			}
			$side.prepend($list);
		}
		remove_legacy_rail_host();
		$side.show();
		return $list;
	}

	function ensure_workspace_page() {
		if (frappe.workspace) {
			return true;
		}
		if (!(frappe.standard_pages && typeof frappe.standard_pages.Workspaces === "function")) {
			return false;
		}
		// Page() calls frappe.get_route_str().join — wait until router finished set_route().
		if (!Array.isArray(frappe.get_route && frappe.get_route())) {
			return false;
		}
		if (!frappe.pages["Workspaces"]) {
			// Page() registers under frappe.get_route_str() — preserve the active route entry.
			const route_str = get_route_str_safe();
			const saved_page = route_str ? frappe.ui.pages[route_str] : null;
			try {
				frappe.standard_pages.Workspaces();
			} catch (e) {
				console.warn("dinext_workspace_sidebar: failed to init Workspaces", e);
			}
			if (route_str) {
				if (saved_page) {
					frappe.ui.pages[route_str] = saved_page;
				} else {
					delete frappe.ui.pages[route_str];
				}
			}
			if (frappe.workspace && frappe.workspace.page) {
				frappe.ui.pages["Workspaces"] = frappe.workspace.page;
			}
		}
		return !!frappe.workspace;
	}

	function wait_for_desk_sidebar(timeout_ms) {
		const limit = timeout_ms || 20000;
		return new Promise((resolve) => {
			const start = Date.now();
			function check() {
				// Keep trying — standard_pages.Workspaces may register after first app_ready tick.
				ensure_workspace_page();
				patch_workspace();
				const $list = get_workspace_list_sidebar();
				if ($list.length) {
					resolve($list);
					return;
				}
				if (Date.now() - start > limit) {
					resolve($());
					return;
				}
				setTimeout(check, 100);
			}
			check();
		});
	}

	function ensure_workspace_sidebar() {
		if (ensure_promise) {
			return ensure_promise;
		}
		ensure_promise = wait_for_desk_sidebar().finally(() => {
			ensure_promise = null;
		});
		return ensure_promise;
	}

	function open_hover_flyout($side_section) {
		if (document.body.classList.contains(BODY_HOVER_OPEN)) {
			active_side_section = $side_section;
			return;
		}
		active_side_section = $side_section;
		document.body.classList.add(BODY_HOVER_OPEN);
	}

	function close_hover_flyout($side_section) {
		if (!document.body.classList.contains(BODY_HOVER_OPEN)) {
			const $side = $side_section || active_side_section;
			if ($side && document.body.classList.contains(BODY_COLLAPSED) && !is_mobile()) {
				active_side_section = $side;
			} else {
				active_side_section = null;
			}
			return;
		}
		document.body.classList.remove(BODY_HOVER_OPEN);
		const $side = $side_section || active_side_section;
		if ($side && document.body.classList.contains(BODY_COLLAPSED) && !is_mobile()) {
			active_side_section = $side;
		} else {
			active_side_section = null;
		}
	}

	function apply_collapsed_state(collapsed, $side_section, opts) {
		const persist = !opts || opts.persist !== false;
		if (persist) {
			localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
		}
		if (!collapsed) {
			document.body.classList.remove(BODY_COLLAPSED, BODY_HOVER_OPEN);
			active_side_section = null;
			return;
		}

		document.body.classList.add(BODY_COLLAPSED);
		if ($side_section && $side_section.length) {
			active_side_section = $side_section;
		}
	}

	function set_pinned_collapsed(collapsed, $side_section) {
		apply_collapsed_state(collapsed, $side_section, { persist: true });
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
		unbind_hover($side_section);
		$side_section.data("dinext-ws-hover", 1);

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
			clear_timers();
			if (document.body.classList.contains(BODY_HOVER_OPEN)) {
				return;
			}
			expand_timer = setTimeout(() => {
				expand_timer = null;
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
			clear_timers();
			if (!document.body.classList.contains(BODY_HOVER_OPEN)) {
				return;
			}
			collapse_timer = setTimeout(() => {
				collapse_timer = null;
				close_hover_flyout($side_section);
			}, COLLAPSE_DELAY_MS);
		}

		// Only the column: list is a descendant (incl. absolute overflow flyout).
		$side_section.on("mouseenter.dinextWsSidebar", schedule_open);
		$side_section.on("mouseleave.dinextWsSidebar", schedule_close);
	}

	function on_sidebar_item_click_capture(e) {
		const anchor =
			e.target &&
			e.target.closest &&
			e.target.closest(".layout-side-section .desk-sidebar .item-anchor");
		if (!anchor) {
			return;
		}
		if (!document.body.classList.contains(BODY_COLLAPSED) || is_mobile()) {
			return;
		}
		clear_timers();
		suppress_open = true;
		const $side =
			active_side_section && active_side_section.length
				? active_side_section
				: $(anchor.closest(".layout-side-section"));
		close_hover_flyout($side);
	}

	document.removeEventListener("click", on_sidebar_item_click_capture, true);
	document.addEventListener("click", on_sidebar_item_click_capture, true);

	function bind_workspaces_toggle(page, $side) {
		const $wrapper = $(page.wrapper);
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
			$(document.body).trigger("toggleSidebar");
		});
	}

	function enhance_page(page) {
		if (is_mobile() || !page || !page.wrapper) {
			return;
		}

		const $wrapper = $(page.wrapper);
		const $side = get_workspaces_side_section($wrapper);
		if (!$side.length) {
			return;
		}
		if (!mount_desk_sidebar($side).length) {
			return;
		}

		active_page = page;
		$side.show();

		set_pinned_collapsed(get_pinned_collapsed(), $side);
		update_toggle_icon(page);
		bind_hover($side);
		bind_workspaces_toggle(page, $side);
	}

	function show_global_collapsed_rail(page, $side) {
		if (is_mobile() || !page || !$side || !$side.length) {
			return;
		}
		if (active_page && active_page !== page && is_workspaces_page(active_page)) {
			$(active_page.wrapper).find(".page-head .sidebar-toggle-btn").off("click.dinextWsSidebar");
			restore_frappe_toggle(active_page);
		}
		active_page = page;
		apply_collapsed_state(true, $side, { persist: false });
		bind_hover($side);
	}

	function is_workspaces_page(page) {
		if (!page || !page.wrapper) {
			return false;
		}
		const route = $(page.wrapper).attr("data-page-route") || (page.wrapper && page.wrapper.id);
		return route === "Workspaces" || route === "page-Workspaces";
	}

	function cleanup_mobile() {
		clear_timers();
		suppress_open = false;
		document.body.classList.remove(BODY_COLLAPSED, BODY_HOVER_OPEN);
		if (active_side_section) {
			unbind_hover(active_side_section);
		}
		active_side_section = null;
		$(".page-head .sidebar-toggle-btn").off("click.dinextWsSidebar");
		if (active_page) {
			restore_frappe_toggle(active_page);
		}
		// Return desk sidebar to Workspaces page so DOM stays consistent.
		if (frappe.workspace && frappe.workspace.page && frappe.workspace.page.wrapper) {
			const $home = get_workspaces_side_section($(frappe.workspace.page.wrapper));
			if ($home.length) {
				mount_desk_sidebar($home);
			}
		}
		active_page = null;
	}

	let page_retry_timer = null;
	let page_retry_count = 0;

	function sync_for_route() {
		if (!feature_enabled()) {
			return;
		}
		if (is_mobile()) {
			if (document.body.classList.contains(BODY_COLLAPSED) || active_page) {
				cleanup_mobile();
			}
			return;
		}

		ensure_workspace_sidebar().then(($list) => {
			if (!$list.length || is_mobile()) {
				return;
			}
			const page = get_current_page();
			if (!page || !page.wrapper) {
				if (page_retry_count < 30) {
					page_retry_count += 1;
					clearTimeout(page_retry_timer);
					page_retry_timer = setTimeout(sync_for_route, 200);
				}
				return;
			}
			page_retry_count = 0;
			const $side = get_mount_side_section($(page.wrapper));
			if (!$side.length) {
				return;
			}
			mount_desk_sidebar($side);

			if (is_workspaces_route()) {
				enhance_page(page);
			} else {
				show_global_collapsed_rail(page, $side);
			}
		});
	}

	const original_setup_sidebar_toggle = frappe.ui.Page.prototype.setup_sidebar_toggle;
	frappe.ui.Page.prototype.setup_sidebar_toggle = function () {
		original_setup_sidebar_toggle.apply(this, arguments);
		if (!is_mobile() && is_workspaces_route() && this === (frappe.workspace && frappe.workspace.page)) {
			enhance_page(this);
		}
	};

	const original_update_sidebar_icon = frappe.ui.Page.prototype.update_sidebar_icon;
	frappe.ui.Page.prototype.update_sidebar_icon = function () {
		if (
			frappe.boot.dinext_workspace_sidebar_hover_expand &&
			!is_mobile() &&
			is_workspaces_route() &&
			this === (frappe.workspace && frappe.workspace.page) &&
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
			if (is_workspaces_route()) {
				enhance_page(this.page);
			}
		};

		const original_show = frappe.views.Workspace.prototype.show;
		frappe.views.Workspace.prototype.show = function () {
			const result = original_show.apply(this, arguments);
			if (!is_mobile()) {
				sync_for_route();
			}
			return result;
		};

		const original_make_sidebar = frappe.views.Workspace.prototype.make_sidebar;
		frappe.views.Workspace.prototype.make_sidebar = function () {
			original_make_sidebar.apply(this, arguments);
			if (!is_mobile()) {
				sync_for_route();
			}
		};

		frappe.views.Workspace.prototype._dinext_ws_sidebar_patched = true;
		return true;
	}

	function on_viewport_change() {
		sync_for_route();
	}

	function start() {
		if (started) {
			return;
		}
		if (!feature_enabled()) {
			return;
		}
		started = true;
		patch_workspace();
		sync_for_route();

		$(window).on("resize.dinextWsSidebar", on_viewport_change);
		$(document).on("page-change", sync_for_route);
		$(document).on("list_sidebar_setup", () => {
			if (!is_mobile()) {
				sync_for_route();
			}
		});
		$(document).on("form-load form-refresh", () => {
			if (!is_mobile() && !is_workspaces_route()) {
				sync_for_route();
			}
		});

		let startup_tries = 0;
		const startup_timer = setInterval(() => {
			startup_tries += 1;
			if (is_mobile() || document.body.classList.contains(BODY_COLLAPSED) || startup_tries > 50) {
				clearInterval(startup_timer);
				return;
			}
			if (frappe.standard_pages && frappe.standard_pages.Workspaces) {
				sync_for_route();
				if (frappe.workspace && get_workspace_list_sidebar().length) {
					clearInterval(startup_timer);
				}
			}
		}, 200);
	}

	patch_workspace();
	$(start);
	$(document).on("app_ready", start);
})();
