frappe.provide("dinext_common.ui_tour");

(function () {
	const ANCHOR_ATTR = "data-dinext-tour";
	const ANCHOR_CLASS = "dinext-ui-tour-anchor";
	const WRAP_CLASS = "dinext-ui-tour-anchors";
	const SOURCE_RAISED_CLASS = "dinext-tour-source-raised";
	const SOURCE_HOST_CLASS = "dinext-tour-source-host";
	const STAGE_CUTOUT_CLASS = "dinext-tour-stage-cutout";
	const DEFAULT_STAGE_BACKGROUND = "#ffffff";
	const WAIT_MS = 8000;
	const tour_selector_cache = new Map();
	const placed = new Map();
	const owner_ids = new Map();
	const owner_listeners = new Map();
	const ready_owners = new Set();
	const observers = new WeakMap();
	const SCROLL_KEYS = new Set([
		"ArrowUp",
		"ArrowDown",
		"ArrowLeft",
		"ArrowRight",
		"PageUp",
		"PageDown",
		"Home",
		"End",
		" ",
		"Spacebar",
	]);
	let wrap_el = null;
	let raised_nodes = [];
	let raised_host = null;
	let scroll_lock = null;
	let active_highlight = null;
	let pending_landmark = false;

	const union_client_rect = (nodes) => {
		let left = Infinity;
		let top = Infinity;
		let right = -Infinity;
		let bottom = -Infinity;
		let found = false;
		(nodes || []).forEach((node) => {
			if (!node || !node.getBoundingClientRect) {
				return;
			}
			const rect = node.getBoundingClientRect();
			if (rect.width <= 0 && rect.height <= 0) {
				return;
			}
			found = true;
			left = Math.min(left, rect.left);
			top = Math.min(top, rect.top);
			right = Math.max(right, rect.right);
			bottom = Math.max(bottom, rect.bottom);
		});
		if (!found) {
			return null;
		}
		return { left, top, width: right - left, height: bottom - top };
	};

	const ensure_wrap = () => {
		if (wrap_el && wrap_el.isConnected) {
			return wrap_el;
		}
		if (!document.body) {
			return null;
		}
		wrap_el = document.createElement("div");
		wrap_el.className = WRAP_CLASS;
		wrap_el.setAttribute("aria-hidden", "true");
		document.body.append(wrap_el);
		return wrap_el;
	};

	const query_anchor = (id) => {
		if (!wrap_el) {
			return null;
		}
		const safe = window.CSS && CSS.escape ? CSS.escape(id) : id;
		return wrap_el.querySelector(`[${ANCHOR_ATTR}="${safe}"]`);
	};

	const unbind_owner_listeners = (owner) => {
		const state = owner_listeners.get(owner);
		if (!state || !state.sync) {
			return;
		}
		(state.targets || []).forEach((target) => {
			target.removeEventListener("scroll", state.sync);
		});
		window.removeEventListener("resize", state.sync);
		owner_listeners.delete(owner);
	};

	const bind_owner_listeners = (owner, host) => {
		unbind_owner_listeners(owner);
		if (!owner) {
			return;
		}
		const sync = () => sync_anchors(owner);
		const targets = [window];
		let node = host;
		while (node && node !== document.documentElement) {
			const style = window.getComputedStyle(node);
			if (/(auto|scroll|overlay)/.test(`${style.overflow}${style.overflowY}${style.overflowX}`)) {
				targets.push(node);
			}
			node = node.parentElement;
		}
		targets.forEach((target) => {
			target.addEventListener("scroll", sync, { passive: true });
		});
		window.addEventListener("resize", sync);
		owner_listeners.set(owner, { targets, sync, host });
	};

	const remove_anchor = (id, owner) => {
		const rec = placed.get(id);
		if (rec && owner && rec.owner && rec.owner !== owner) {
			return;
		}
		const el = (rec && rec.el) || query_anchor(id);
		if (el) {
			el.remove();
		}
		placed.delete(id);
		if (owner && owner_ids.has(owner)) {
			owner_ids.get(owner).delete(id);
		}
	};

	const place_anchor = (id, source, options) => {
		const owner = options && options.owner;
		if (!id || !source) {
			if (id) {
				remove_anchor(id, owner);
			}
			return null;
		}
		const host = source.host || (options && options.host) || null;
		const rect_nodes =
			source.rect_nodes && source.rect_nodes.length
				? source.rect_nodes
				: source.scroll
					? [source.scroll]
					: [];
		const rect = union_client_rect(rect_nodes);
		if (!rect || rect.width < 1 || rect.height < 1) {
			remove_anchor(id, owner);
			return null;
		}
		const wrap = ensure_wrap();
		if (!wrap) {
			return null;
		}
		let el = query_anchor(id);
		if (!el) {
			el = document.createElement("div");
			el.className = ANCHOR_CLASS;
			el.setAttribute(ANCHOR_ATTR, id);
			wrap.append(el);
		}
		el.style.left = `${Math.round(rect.left)}px`;
		el.style.top = `${Math.round(rect.top)}px`;
		el.style.width = `${Math.round(rect.width)}px`;
		el.style.height = `${Math.round(rect.height)}px`;
		el.__dinextTourSource = source.scroll || null;
		el.__dinextTourVisible = [...(source.visible_nodes || rect_nodes)];
		el.__dinextTourHost = host;
		placed.set(id, { el, owner, source: { ...source, host } });
		if (owner) {
			if (!owner_ids.has(owner)) {
				owner_ids.set(owner, new Set());
			}
			owner_ids.get(owner).add(id);
			const prev = owner_listeners.get(owner);
			if (!prev || prev.host !== host) {
				bind_owner_listeners(owner, host);
			}
		}
		return el;
	};

	const sync_anchors = (owner) => {
		const ids = owner ? owner_ids.get(owner) : [...placed.keys()];
		(ids || []).forEach((id) => {
			const rec = placed.get(id);
			if (!rec) {
				return;
			}
			if (owner && rec.owner !== owner) {
				return;
			}
			place_anchor(id, rec.source, { owner: rec.owner, host: rec.source && rec.source.host });
		});
	};

	const disconnect_observer = (owner) => {
		const observer = observers.get(owner);
		if (!observer) {
			return;
		}
		observer.disconnect();
		observers.delete(owner);
	};

	const clear_anchors = (owner) => {
		const ids = owner_ids.get(owner);
		if (ids) {
			[...ids].forEach((id) => remove_anchor(id, owner));
			owner_ids.delete(owner);
		}
		unbind_owner_listeners(owner);
		disconnect_observer(owner);
		ready_owners.delete(owner);
		if (!placed.size && wrap_el) {
			wrap_el.remove();
			wrap_el = null;
		}
	};

	const is_kit_node = (node) => {
		if (!node || !node.classList) {
			return false;
		}
		return node.classList.contains(WRAP_CLASS) || node.classList.contains(ANCHOR_CLASS);
	};

	const split_tour_ids = (value) =>
		String(value || "")
			.split(/\s+/)
			.map((id) => id.trim())
			.filter(Boolean);

	const collect_marked_nodes = (root) => {
		const nodes = [];
		const seen = new Set();
		const scan = (ctx) => {
			if (!ctx || seen.has(ctx)) {
				return;
			}
			seen.add(ctx);
			if (ctx.nodeType === 1 && is_kit_node(ctx)) {
				return;
			}
			if (ctx.querySelectorAll) {
				ctx.querySelectorAll(`[${ANCHOR_ATTR}]`).forEach((el) => {
					if (!is_kit_node(el)) {
						nodes.push(el);
					}
				});
				ctx.querySelectorAll("*").forEach((el) => {
					if (el.shadowRoot) {
						scan(el.shadowRoot);
					}
				});
			}
			if (ctx.shadowRoot) {
				scan(ctx.shadowRoot);
			}
		};
		scan(root);
		return nodes;
	};

	const observe_host = (root) => {
		if (!root || !root.getRootNode) {
			return null;
		}
		const tree = root.getRootNode();
		return tree && tree.host ? tree.host : null;
	};

	const refresh_observed = (root) => {
		if (!root || root.isConnected === false) {
			clear_anchors(root);
			return;
		}
		const host = observe_host(root);
		const seen = new Set();
		collect_marked_nodes(root).forEach((node) => {
			const source = {
				scroll: node,
				rect_nodes: [node],
				visible_nodes: [node],
				host,
			};
			split_tour_ids(node.getAttribute(ANCHOR_ATTR)).forEach((id) => {
				seen.add(id);
				place_anchor(id, source, { owner: root, host });
			});
		});
		const owned = owner_ids.get(root);
		if (owned) {
			[...owned].forEach((id) => {
				if (!seen.has(id)) {
					remove_anchor(id, root);
				}
			});
		}
		if (seen.size) {
			ready_owners.add(root);
		}
	};

	const observe = (root) => {
		if (!root) {
			return;
		}
		refresh_observed(root);
		if (typeof MutationObserver !== "function" || observers.has(root)) {
			return;
		}
		const mo = new MutationObserver(() => refresh_observed(root));
		const opts = {
			subtree: true,
			childList: true,
			attributes: true,
			attributeFilter: [ANCHOR_ATTR],
		};
		try {
			mo.observe(root, opts);
		} catch (error) {
			return;
		}
		if (root.shadowRoot) {
			mo.observe(root.shadowRoot, opts);
		}
		observers.set(root, mo);
	};

	const apply_stage_cutout = () => {
		const stage = document.getElementById("driver-highlighted-element-stage");
		if (stage) {
			stage.classList.add(STAGE_CUTOUT_CLASS);
		}
		const overlay = document.getElementById("driver-page-overlay");
		if (overlay && overlay.parentElement) {
			overlay.parentElement.removeChild(overlay);
		}
	};

	const clear_stage_cutout = () => {
		const stage = document.getElementById("driver-highlighted-element-stage");
		if (stage) {
			stage.classList.remove(STAGE_CUTOUT_CLASS);
		}
	};

	const collect_scroll_parents = (host) => {
		const targets = [];
		const add = (el) => {
			if (el && targets.indexOf(el) === -1) {
				targets.push(el);
			}
		};
		add(document.documentElement);
		add(document.body);
		let node = host;
		while (node && node !== document.documentElement) {
			const style = window.getComputedStyle(node);
			if (/(auto|scroll|overlay)/.test(`${style.overflow}${style.overflowY}${style.overflowX}`)) {
				add(node);
			}
			node = node.parentElement;
		}
		return targets;
	};

	const is_scroll_exception = (event) => {
		if (!event || event.type !== "keydown") {
			return false;
		}
		const target = event.target;
		if (!target || !target.closest) {
			return false;
		}
		if (target.closest("input, textarea, select, [contenteditable='true']")) {
			return true;
		}
		return Boolean(target.closest(".driver-popover, .frappe-driver, button, a, [role='button']"));
	};

	const prevent_scroll = (event) => {
		if (event.type === "keydown" && !SCROLL_KEYS.has(event.key)) {
			return;
		}
		if (is_scroll_exception(event)) {
			return;
		}
		event.preventDefault();
	};

	const resync_active_highlight = () => {
		const current = active_highlight;
		if (!current) {
			return;
		}
		sync_anchors();
		if (current.driver && current.driver.overlay && current.driver.overlay.refresh) {
			current.driver.overlay.refresh();
		}
		if (has_tour_contract(current.node)) {
			raise(current.node);
		}
		clamp_popover(current.step);
	};

	const unlock_scroll = () => {
		if (!scroll_lock) {
			return;
		}
		(scroll_lock.targets || []).forEach((el, index) => {
			if (el && el.style) {
				el.style.overflow = scroll_lock.overflow[index] || "";
			}
		});
		window.removeEventListener("wheel", scroll_lock.prevent, true);
		window.removeEventListener("touchmove", scroll_lock.prevent, true);
		window.removeEventListener("keydown", scroll_lock.prevent, true);
		(scroll_lock.targets || []).forEach((el) => {
			el.removeEventListener("scroll", scroll_lock.on_scroll);
		});
		window.removeEventListener("scroll", scroll_lock.on_scroll);
		scroll_lock = null;
	};

	const set_lock_overflow = (hidden) => {
		if (!scroll_lock) {
			return;
		}
		(scroll_lock.targets || []).forEach((el, index) => {
			if (!el || !el.style) {
				return;
			}
			el.style.overflow = hidden ? "hidden" : scroll_lock.overflow[index] || "";
		});
	};

	const lock_scroll = (host) => {
		if (scroll_lock) {
			return;
		}
		const targets = collect_scroll_parents(host);
		const overflow = targets.map((el) => (el && el.style && el.style.overflow) || "");
		targets.forEach((el) => {
			if (el && el.style) {
				el.style.overflow = "hidden";
			}
		});
		const on_scroll = resync_active_highlight;
		window.addEventListener("wheel", prevent_scroll, { capture: true, passive: false });
		window.addEventListener("touchmove", prevent_scroll, { capture: true, passive: false });
		window.addEventListener("keydown", prevent_scroll, { capture: true });
		targets.forEach((el) => {
			el.addEventListener("scroll", on_scroll, { passive: true });
		});
		window.addEventListener("scroll", on_scroll, { passive: true });
		scroll_lock = { targets, overflow, prevent: prevent_scroll, on_scroll };
	};

	const clear_raised = (options) => {
		raised_nodes.forEach((node) => {
			if (node && node.classList) {
				node.classList.remove(SOURCE_RAISED_CLASS);
			}
		});
		raised_nodes = [];
		if (raised_host) {
			raised_host.classList.remove(SOURCE_HOST_CLASS);
			raised_host = null;
		}
		if (!(options && options.keep_scroll_lock)) {
			clear_stage_cutout();
			unlock_scroll();
			active_highlight = null;
		}
	};

	const has_tour_contract = (node) => {
		return Boolean(
			node &&
				(node.__dinextTourSource ||
					(Array.isArray(node.__dinextTourVisible) && node.__dinextTourVisible.length) ||
					node.__dinextTourHost)
		);
	};

	const set_stage_background = (el, color) => {
		if (el && el.stage && el.stage.options) {
			el.stage.options.stageBackground = color;
		}
		if (el && el.options) {
			el.options.stageBackground = color;
		}
	};

	const prepare_highlight = (el) => {
		const contract = has_tour_contract(el && el.node);
		pending_landmark = contract;
		if (contract) {
			set_lock_overflow(false);
			const source = el.node.__dinextTourSource;
			if (source && source.scrollIntoView) {
				source.scrollIntoView({ block: "center", inline: "nearest" });
			}
			if (document.body) {
				document.body.offsetHeight;
			}
			sync_anchors();
			set_lock_overflow(true);
			el.isInView = () => true;
			el.bringInView = () => {};
			set_stage_background(el, "transparent");
			const stage = document.getElementById("driver-highlighted-element-stage");
			if (stage) {
				stage.classList.add(STAGE_CUTOUT_CLASS);
			}
			return;
		}
		set_stage_background(el, DEFAULT_STAGE_BACKGROUND);
		clear_stage_cutout();
	};

	const raise = (dummy) => {
		clear_raised({ keep_scroll_lock: true });
		if (!has_tour_contract(dummy)) {
			unlock_scroll();
			return;
		}
		const nodes = dummy.__dinextTourVisible || [];
		nodes.forEach((node) => {
			if (node && node.classList) {
				node.classList.add(SOURCE_RAISED_CLASS);
				raised_nodes.push(node);
			}
		});
		const host = dummy.__dinextTourHost;
		if (host) {
			host.classList.add(SOURCE_HOST_CLASS);
			raised_host = host;
		}
		apply_stage_cutout();
		lock_scroll(host);
	};

	const mark_ready = (owner) => {
		if (owner) {
			ready_owners.add(owner);
		}
	};

	const is_ready = () => ready_owners.size > 0;

	const get_tour_source = (node) => {
		return node && node.__dinextTourSource ? node.__dinextTourSource : null;
	};

	const clamp_popover = (step) => {
		const pop = step && step.popover && step.popover.node;
		if (!pop) {
			return;
		}
		const rect = pop.getBoundingClientRect();
		if (rect.top < 8) {
			pop.style.top = `${Math.max(8, pop.offsetTop + (8 - rect.top))}px`;
		} else if (rect.bottom > window.innerHeight - 8) {
			pop.style.top = `${Math.max(8, pop.offsetTop - (rect.bottom - (window.innerHeight - 8)))}px`;
		}
	};

	const highlight_step = (driver, step) => {
		const node = step && step.node;
		active_highlight = { driver, step, node };
		if (has_tour_contract(node)) {
			raise(node);
			clamp_popover(step);
			return;
		}
		clear_raised();
		clamp_popover(step);
	};

	const patch_driver_hooks = (Tour) => {
		if (!Tour || !Tour.prototype || typeof Tour.prototype.init_driver !== "function") {
			return false;
		}
		if (Tour.prototype.__dinext_ui_tour_patched) {
			return true;
		}
		const original_init_driver = Tour.prototype.init_driver;
		Tour.prototype.init_driver = function () {
			original_init_driver.call(this);
			const driver = this.driver;
			if (!driver || !driver.options) {
				return;
			}
			const previous = driver.options.onHighlighted;
			const previous_started = driver.options.onHighlightStarted;
			const previous_deselected = driver.options.onDeselected;
			const previous_reset = driver.options.onReset;
			driver.options.onHighlightStarted = (el) => {
				prepare_highlight(el);
				if (typeof previous_started === "function") {
					previous_started(el);
				}
			};
			driver.options.onDeselected = (el) => {
				clear_raised({ keep_scroll_lock: pending_landmark });
				if (typeof previous_deselected === "function") {
					previous_deselected(el);
				}
			};
			driver.options.onReset = (el) => {
				pending_landmark = false;
				clear_raised();
				if (typeof previous_reset === "function") {
					previous_reset(el);
				}
			};
			driver.options.onHighlighted = (step) => {
				if (typeof previous === "function") {
					previous(step);
				}
				highlight_step(driver, step);
			};
		};
		Tour.prototype.__dinext_ui_tour_patched = true;
		return true;
	};

	const patch_onboarding_translation = (Tour) => {
		if (!Tour || !Tour.prototype || typeof Tour.prototype.get_step !== "function") {
			return false;
		}
		if (Tour.prototype.__dinext_ui_tour_translated) {
			return true;
		}
		const original = Tour.prototype.get_step;
		Tour.prototype.get_step = function (step_info, on_next) {
			const step = original.call(this, step_info, on_next);
			if (step && step.popover) {
				if (step.popover.title) {
					step.popover.title = __(step.popover.title);
				}
				if (step.popover.description) {
					step.popover.description = __(step.popover.description);
				}
			}
			return step;
		};
		Tour.prototype.__dinext_ui_tour_translated = true;
		return true;
	};

	const find_matching_ui_tour_name = () => {
		const route =
			(window.frappe && frappe.router && frappe.router.current_route) ||
			(window.frappe && frappe.get_route && frappe.get_route()) ||
			[];
		if (!route.length || route[0] === "") {
			return null;
		}
		let path = route;
		if (path[0] === "query-report") {
			path = ["List", path[1], "Report"];
		}
		if (path[0] === "dashboard-view") {
			return null;
		}
		const tours = (frappe.boot && frappe.boot.onboarding_tours) || [];
		const status =
			(frappe.boot && frappe.boot.user && frappe.boot.user.onboarding_status) || {};
		const matching = [];
		tours.forEach((tour) => {
			const tour_route = tour[1];
			if (!tour_route) {
				return;
			}
			const length = Math.min(path.length, tour_route.length);
			if (length >= 1 && path[0] != tour_route[0]) {
				return;
			}
			if (length >= 2 && tour_route[1] != "*" && path[1] != tour_route[1]) {
				return;
			}
			if (
				length >= 3 &&
				["*", "new-*"].indexOf(tour_route[2]) == -1 &&
				path[2] != tour_route[2]
			) {
				return;
			}
			if (status[tour[0]] && status[tour[0]].is_complete) {
				return;
			}
			matching.push(tour[0]);
		});
		if (!matching.length) {
			return null;
		}
		const current = frappe.ui && frappe.ui.currentTourInstance && frappe.ui.currentTourInstance.tour;
		if (current && current.name && matching.includes(current.name)) {
			return current.name;
		}
		if (frappe.ui && frappe.ui.next_form_tour && matching.includes(frappe.ui.next_form_tour)) {
			return frappe.ui.next_form_tour;
		}
		return matching[0];
	};

	const load_tour_selectors = (name) => {
		if (!name) {
			return Promise.resolve([]);
		}
		if (tour_selector_cache.has(name)) {
			return Promise.resolve(tour_selector_cache.get(name));
		}
		if (!(window.frappe && frappe.db && typeof frappe.db.get_doc === "function")) {
			return Promise.resolve([]);
		}
		return frappe.db
			.get_doc("Form Tour", name)
			.then((doc) => {
				const selectors = (doc.steps || [])
					.map((step) => step.element_selector)
					.filter(Boolean);
				tour_selector_cache.set(name, selectors);
				return selectors;
			})
			.catch(() => []);
	};

	const selector_present = (sel) => {
		try {
			const el = document.querySelector(sel);
			if (!el) {
				return false;
			}
			const rect = el.getBoundingClientRect();
			return rect.width > 0 || rect.height > 0;
		} catch (error) {
			return true;
		}
	};

	const is_landmark_selector = (sel) => String(sel || "").includes(ANCHOR_ATTR);

	const wait_for_tour_selectors = (selectors, done) => {
		const list = (selectors || []).filter(Boolean);
		const begun = Date.now();
		const ready = () => {
			const missing = list.filter((sel) => !selector_present(sel));
			if (!missing.length) {
				return true;
			}
			if (missing.every(is_landmark_selector) && is_ready()) {
				return true;
			}
			return Date.now() - begun > WAIT_MS;
		};
		if (ready()) {
			done();
			return;
		}
		const wait = setInterval(() => {
			if (ready()) {
				clearInterval(wait);
				done();
			}
		}, 100);
	};

	const wrap_init_onboarding_tour = () => {
		if (!(window.frappe && frappe.ui && typeof frappe.ui.init_onboarding_tour === "function")) {
			return false;
		}
		if (frappe.ui.__dinext_onboarding_wrapped) {
			return true;
		}
		const original_init = frappe.ui.init_onboarding_tour;
		frappe.ui.init_onboarding_tour = function () {
			const ctx = this;
			const args = arguments;
			const start = () => original_init.apply(ctx, args);
			const name = find_matching_ui_tour_name();
			if (!name) {
				return start();
			}
			load_tour_selectors(name).then((selectors) => wait_for_tour_selectors(selectors, start));
		};
		frappe.ui.__dinext_onboarding_wrapped = true;
		return true;
	};

	let form_watch_bound = false;
	const watch_form_tour = () => {
		if (form_watch_bound) {
			return;
		}
		if (!(window.frappe && frappe.router && typeof frappe.router.on === "function")) {
			return;
		}
		form_watch_bound = true;
		frappe.router.on("change", () => {
			const FormTour = frappe.ui && frappe.ui.form && frappe.ui.form.FormTour;
			if (FormTour) {
				patch_driver_hooks(FormTour);
			}
		});
	};

	const patch = () => {
		wrap_init_onboarding_tour();
		watch_form_tour();
		const OnboardingTour = window.frappe && frappe.ui && frappe.ui.OnboardingTour;
		if (OnboardingTour) {
			patch_driver_hooks(OnboardingTour);
			patch_onboarding_translation(OnboardingTour);
		}
		const FormTour = window.frappe && frappe.ui && frappe.ui.form && frappe.ui.form.FormTour;
		if (FormTour) {
			patch_driver_hooks(FormTour);
		}
		return Boolean(
			frappe.ui &&
				frappe.ui.__dinext_onboarding_wrapped &&
				OnboardingTour &&
				OnboardingTour.prototype &&
				OnboardingTour.prototype.__dinext_ui_tour_patched &&
				OnboardingTour.prototype.__dinext_ui_tour_translated
		);
	};

	dinext_common.ui_tour.place_anchor = place_anchor;
	dinext_common.ui_tour.observe = observe;
	dinext_common.ui_tour.sync_anchors = sync_anchors;
	dinext_common.ui_tour.clear_anchors = clear_anchors;
	dinext_common.ui_tour.raise = raise;
	dinext_common.ui_tour.clear_raised = clear_raised;
	dinext_common.ui_tour.mark_ready = mark_ready;
	dinext_common.ui_tour.is_ready = is_ready;
	dinext_common.ui_tour.get_tour_source = get_tour_source;
	dinext_common.ui_tour.has_tour_contract = has_tour_contract;
	dinext_common.ui_tour.patch = patch;

	const apply = () => patch();
	if (apply()) {
		return;
	}
	if (window.frappe && typeof frappe.require === "function") {
		frappe.require("onboarding_tours.bundle.js", apply);
	}
	const started = Date.now();
	const timer = setInterval(() => {
		if (apply() || Date.now() - started > 15000) {
			clearInterval(timer);
		}
	}, 50);
})();
