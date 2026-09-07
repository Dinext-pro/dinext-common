frappe.provide("dinext_common.workspace_hub");

const DINEXT_WORKSPACE_HUB_CSS = "/assets/dinext_common/css/workspace_hub.css";
const DINEXT_WORKSPACE_HUB_ASSETS = "tour-kit-1";
const DINEXT_TOUR_SETTINGS = "Dinext";
const DINEXT_TOUR_IDS = ["personal-lists", "directions", "help"];
const PAGE_SKIP = new Set(["setup-wizard", "social", "recorder"]);
const mounted_hubs = new Set();
const hub_mounted_at = new WeakMap();
const hub_load_tokens = new WeakMap();
const hub_render_tokens = new WeakMap();
let router_refresh_bound = false;

const resolve_sprite = (icon_name) => {
	if (icon_name.startsWith("es-")) {
		return "/assets/frappe/icons/espresso/icons.svg";
	}
	return "/assets/frappe/icons/timeless/icons.svg";
};

const is_font_icon = (icon_name) => {
	const name = String(icon_name || "").trim();
	return /^(fa |fa-|octicon |octicon-|glyphicon |glyphicon-|icon-)/.test(name);
};

const make_icon = (icon_name, size = "sm") => {
	if (!icon_name) {
		return null;
	}

	const name = String(icon_name).trim();
	if (!name) {
		return null;
	}

	if (is_font_icon(name)) {
		const wrap = document.createElement("span");
		wrap.className = "dinext-workspace-hub__type-icon";
		const el = document.createElement("i");
		el.className = name;
		el.setAttribute("aria-hidden", "true");
		wrap.append(el);
		return wrap;
	}

	if (!frappe.utils || !frappe.utils.icon) {
		return null;
	}

	const wrap = document.createElement("span");
	wrap.className = "dinext-workspace-hub__type-icon";
	wrap.innerHTML = frappe.utils.icon(name, size);

	const use = wrap.querySelector("use");
	if (!use) {
		return wrap;
	}

	const ref = use.getAttribute("href") || use.getAttribute("xlink:href") || "";
	if (ref.startsWith("#")) {
		const href = `${resolve_sprite(name)}${ref}`;
		use.setAttribute("href", href);
		use.setAttribute("xlink:href", href);
	}

	return wrap;
};

const navigate_route = (route, event) => {
	if (!route) {
		return;
	}
	if (event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1) {
		return;
	}
	event.preventDefault();
	if (/^https?:\/\//i.test(route)) {
		window.open(route, "_blank", "noopener");
		return;
	}
	const path = route.replace(/^\/app\//, "").replace(/^\//, "");
	const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
	if (parts.length) {
		frappe.set_route(...parts);
	}
};

const make_card = (item) => {
	const link = document.createElement("a");
	link.className = "dinext-workspace-hub__card";
	link.href = item.route;
	link.addEventListener("click", (event) => navigate_route(item.route, event));

	const icon = make_icon(item.icon, "md");
	if (icon) {
		icon.className = "dinext-workspace-hub__card-icon";
		link.append(icon);
	}

	const body = document.createElement("div");
	body.className = "dinext-workspace-hub__card-body";
	const title = document.createElement("div");
	title.className = "dinext-workspace-hub__card-title";
	title.textContent = __(item.label);
	body.append(title);
	if (item.description) {
		const description = document.createElement("div");
		description.className = "dinext-workspace-hub__card-description";
		description.textContent = __(item.description);
		body.append(description);
	}
	link.append(body);
	return link;
};

const make_type_badge = (item) => {
	const badge = document.createElement("span");
	badge.className = "dinext-workspace-hub__type-badge";
	const type_label = __(item.type_label || item.doctype || "");
	badge.title = type_label;
	badge.setAttribute("aria-label", type_label);
	const icon = make_icon(item.icon || "file", "xs");
	if (icon) {
		badge.append(icon);
	}
	return badge;
};

const desk_slug = (doctype) => {
	const scrubbed =
		frappe.scrub && typeof frappe.scrub === "function"
			? frappe.scrub(doctype)
			: String(doctype || "")
					.toLowerCase()
					.replace(/ /g, "_");
	return String(scrubbed).replace(/_/g, "-");
};

const as_route_parts = (route) => {
	if (Array.isArray(route)) {
		return route.filter((part) => part !== undefined && part !== null && String(part).length);
	}
	return String(route || "")
		.replace(/^\/app\//, "")
		.split("/")
		.filter(Boolean);
};

const route_key = (parts) => parts.join("/");

const is_useful_page = (parts) => {
	if (!parts.length || PAGE_SKIP.has(parts[0])) {
		return false;
	}
	if (parts[0] === "Form") {
		const name = parts.slice(2).join("/");
		return parts.length >= 3 && !String(name).toLowerCase().startsWith("new-");
	}
	if (["List", "Tree", "Workspaces", "query-report"].includes(parts[0])) {
		return parts.length >= 2;
	}
	return false;
};

const allowed_workspaces = () =>
	(window.frappe && frappe.boot && frappe.boot.allowed_workspaces) || [];

const workspace_slug = (value) => {
	if (window.frappe && frappe.router && frappe.router.slug) {
		return frappe.router.slug(value);
	}
	return desk_slug(value);
};

const workspace_page = (parts) => {
	if (parts[0] !== "Workspaces") {
		return null;
	}
	const title = parts[parts.length - 1];
	const slug = workspace_slug(title);
	return (
		allowed_workspaces().find((page) => {
			const name = (page && page.name) || "";
			const page_title = (page && page.title) || "";
			return (
				name === title ||
				page_title === title ||
				workspace_slug(name) === slug ||
				workspace_slug(page_title) === slug
			);
		}) || null
	);
};

const doctype_icon = (doctype) => {
	const meta = window.frappe && frappe.get_meta && frappe.get_meta(doctype);
	return (meta && meta.icon) || "";
};

const form_title_field = (doctype) => {
	const meta = window.frappe && frappe.get_meta && frappe.get_meta(doctype);
	if (!meta) {
		return "";
	}
	const title_field =
		typeof meta.get_title_field === "function" ? meta.get_title_field() : meta.title_field;
	if (!title_field || title_field === "name") {
		return "";
	}
	if (typeof meta.has_field === "function" && !meta.has_field(title_field)) {
		return "";
	}
	return title_field;
};

const with_doctype = (doctype) =>
	new Promise((resolve) => {
		if (window.frappe && frappe.model && frappe.model.with_doctype) {
			frappe.model.with_doctype(doctype, () => resolve());
			return;
		}
		resolve();
	});

const page_label = (parts) => {
	if (parts[0] === "Form" && parts.length >= 3) {
		return parts.slice(2).join("/");
	}
	if (parts[0] === "List" && parts[1]) {
		return __("{0} List", [__(parts[1])]);
	}
	if (parts[0] === "Tree" && parts[1]) {
		return __("{0} Tree", [__(parts[1])]);
	}
	if (parts[0] === "Workspaces") {
		const page = workspace_page(parts);
		const title = (page && (page.title || page.name)) || parts[parts.length - 1];
		return __(title);
	}
	if (parts[0] === "query-report" && parts[1]) {
		return __("{0} Report", [__(parts[1])]);
	}
	if (window.frappe && frappe.utils && frappe.utils.get_route_label) {
		return frappe.utils.get_route_label(parts.join("/"));
	}
	return parts.join(" / ");
};

const page_href = (parts) => {
	if (parts[0] === "Form" && parts.length >= 3) {
		return `/app/${desk_slug(parts[1])}/${parts.slice(2).join("/")}`;
	}
	if (parts[0] === "Workspaces") {
		const title = parts[parts.length - 1];
		const slug =
			window.frappe && frappe.router && frappe.router.slug
				? frappe.router.slug(title)
				: desk_slug(title);
		if (parts[1] === "private") {
			return `/app/private/${slug}`;
		}
		return `/app/${slug}`;
	}
	if (parts[0] === "List" && parts[1]) {
		return `/app/${desk_slug(parts[1])}`;
	}
	if (parts[0] === "query-report" && parts[1]) {
		return `/app/query-report/${encodeURIComponent(parts[1])}`;
	}
	return `/app/${parts.map((part) => encodeURIComponent(part)).join("/")}`;
};

const page_icon = (parts) => {
	if (parts[0] === "List") {
		return doctype_icon(parts[1]) || "list";
	}
	if (parts[0] === "Form") {
		return doctype_icon(parts[1]) || "file";
	}
	if (parts[0] === "Tree") {
		return "folder-normal";
	}
	if (parts[0] === "Workspaces") {
		const page = workspace_page(parts);
		return (page && page.icon) || "layout";
	}
	if (parts[0] === "query-report") {
		return "table";
	}
	return "file";
};

const make_page_item = (parts) => {
	const item = {
		title: page_label(parts),
		route: page_href(parts),
		icon: page_icon(parts),
		type_label: __(parts[0] || ""),
	};
	if (parts[0] === "Form" && parts.length >= 3) {
		item.doctype = parts[1];
		item.name = parts.slice(2).join("/");
	}
	return item;
};

const unwrap_title_value = (result, field) => {
	if (result == null) {
		return "";
	}
	if (typeof result === "string" || typeof result === "number") {
		return String(result);
	}
	if (result[field]) {
		return String(result[field]);
	}
	const message = result.message;
	if (typeof message === "string" || typeof message === "number") {
		return String(message);
	}
	if (message && message[field]) {
		return String(message[field]);
	}
	return "";
};

const apply_form_titles = (items, doctype, title_field, rows) => {
	const titles = {};
	(rows || []).forEach((row) => {
		if (!row || !row.name) {
			return;
		}
		titles[row.name] = unwrap_title_value(row, title_field) || row.name;
	});
	items.forEach((item) => {
		if (item.doctype === doctype && titles[item.name]) {
			item.title = titles[item.name];
		}
	});
};

const fetch_form_titles = (doctype, names, title_field) => {
	if (window.frappe && frappe.db && frappe.db.get_list) {
		return frappe.db
			.get_list(doctype, {
				filters: { name: ["in", names] },
				fields: ["name", title_field],
				limit: names.length,
			})
			.then((rows) => rows || []);
	}
	if (!window.frappe || !frappe.db || !frappe.db.get_value) {
		return Promise.resolve([]);
	}
	return Promise.all(
		names.map((name) =>
			frappe.db
				.get_value(doctype, name, title_field)
				.then((result) => ({
					name,
					[title_field]: unwrap_title_value(result, title_field),
				}))
				.catch(() => null)
		)
	).then((rows) => rows.filter(Boolean));
};

const enrich_form_titles = (items) => {
	const forms = (items || []).filter((item) => item.doctype && item.name);
	if (!forms.length) {
		return Promise.resolve(items);
	}
	const by_doctype = new Map();
	forms.forEach((item) => {
		const names = by_doctype.get(item.doctype) || [];
		if (!names.includes(item.name)) {
			names.push(item.name);
		}
		by_doctype.set(item.doctype, names);
	});
	const jobs = [...by_doctype.entries()].map(([doctype, names]) =>
		with_doctype(doctype)
			.then(() => {
				const title_field = form_title_field(doctype);
				if (!title_field) {
					return;
				}
				return fetch_form_titles(doctype, names, title_field).then((rows) =>
					apply_form_titles(forms, doctype, title_field, rows)
				);
			})
			.catch(() => {})
	);
	return Promise.all(jobs).then(() => items);
};

const frequent_pages = (limit) => {
	if (limit < 1) {
		return [];
	}
	const links = (window.frappe && frappe.boot && frappe.boot.frequently_visited_links) || [];
	const seen = new Set();
	const out = [];
	links.forEach((link) => {
		const parts = as_route_parts(link && link.route);
		if (!is_useful_page(parts)) {
			return;
		}
		const key = route_key(parts);
		if (seen.has(key) || out.length >= limit) {
			return;
		}
		seen.add(key);
		out.push(make_page_item(parts));
	});
	return out;
};

const current_workspace_key = () => {
	const route =
		(window.frappe && frappe.get_route && frappe.get_route()) ||
		(window.frappe && frappe.router && frappe.router.current_route) ||
		[];
	if (Array.isArray(route) && route[0] === "Workspaces") {
		return route_key(as_route_parts(route));
	}
	return "";
};

const recent_pages = (limit) => {
	if (limit < 1) {
		return [];
	}
	const history = (window.frappe && frappe.route_history) || [];
	const skip_current = current_workspace_key();
	const seen = new Set();
	const out = [];
	for (let i = history.length - 1; i >= 0; i -= 1) {
		const parts = as_route_parts(history[i]);
		if (!is_useful_page(parts)) {
			continue;
		}
		const key = route_key(parts);
		if ((skip_current && key === skip_current) || seen.has(key)) {
			continue;
		}
		seen.add(key);
		out.push(make_page_item(parts));
		if (out.length >= limit) {
			break;
		}
	}
	return out;
};

const make_page_chip = (item) => {
	const link = document.createElement("a");
	link.className = "dinext-workspace-hub__page-chip";
	link.href = item.route;
	const title_text = item.title || item.name || "";
	if (item.doctype) {
		const bits = [__(item.doctype), title_text];
		if (item.name && item.name !== title_text) {
			bits.push(item.name);
		}
		link.title = bits.join(" · ");
	} else {
		link.title = title_text;
	}
	const icon = make_icon(item.icon || "file", "xs");
	if (icon) {
		icon.classList.add("dinext-workspace-hub__page-chip-icon");
		link.append(icon);
	}
	const title = document.createElement("span");
	title.className = "dinext-workspace-hub__page-chip-title";
	title.textContent = title_text;
	link.append(title);
	link.addEventListener("click", (event) => navigate_route(item.route, event));
	return link;
};

const make_page_row = (heading, items) => {
	if (!items || !items.length) {
		return null;
	}

	const wrap = document.createElement("div");
	wrap.className = "dinext-workspace-hub__page-row";
	wrap.append(make_column_heading(heading));
	const chips = document.createElement("div");
	chips.className = "dinext-workspace-hub__page-chips";
	items.forEach((item) => chips.append(make_page_chip(item)));
	wrap.append(chips);
	return wrap;
};

const collect_page_groups = (payload) => {
	const limit = Math.max(1, parseInt(payload.page_list_limit, 10) || 5);
	return {
		recent: payload.show_recent_pages ? recent_pages(limit) : [],
		frequent: payload.show_frequent_pages ? frequent_pages(limit) : [],
	};
};

const make_page_lists_from_groups = (groups) => {
	const wrap = document.createElement("div");
	wrap.className = "dinext-workspace-hub__personal dinext-workspace-hub__pages";
	const rows = document.createElement("div");
	rows.className = "dinext-workspace-hub__page-rows";
	const recent_node = make_page_row("Recent Pages", groups.recent);
	if (recent_node) {
		rows.append(recent_node);
	}
	const frequent_node = make_page_row("Frequent Pages", groups.frequent);
	if (frequent_node) {
		rows.append(frequent_node);
	}
	if (!rows.childElementCount) {
		return null;
	}
	wrap.append(rows);
	return wrap;
};

const make_page_lists = (payload) => {
	if (!payload) {
		return null;
	}
	return make_page_lists_from_groups(collect_page_groups(payload));
};

const paint_page_lists = (payload) => {
	if (!payload) {
		return Promise.resolve(null);
	}
	const groups = collect_page_groups(payload);
	const items = [...groups.recent, ...groups.frequent];
	if (!items.length) {
		return Promise.resolve(null);
	}
	return enrich_form_titles(items).then(() => make_page_lists_from_groups(groups));
};

const make_record_link = (item) => {
	const link = document.createElement("a");
	link.className = "dinext-workspace-hub__record";
	link.href = item.route;
	const title_text = item.title || item.name;
	link.title = title_text;
	link.append(make_type_badge(item));
	const title = document.createElement("span");
	title.className = "dinext-workspace-hub__record-title";
	title.textContent = title_text;
	link.append(title);
	link.addEventListener("click", (event) => navigate_route(item.route, event));
	return link;
};

const make_column_heading = (heading) => {
	const title = document.createElement("div");
	title.className = "dinext-workspace-hub__list-title";
	title.textContent = __(heading);
	return title;
};

const make_list = (heading, items) => {
	if (!items || !items.length) {
		return null;
	}

	const wrap = document.createElement("div");
	wrap.className = "dinext-workspace-hub__list";
	wrap.append(make_column_heading(heading));
	const ul = document.createElement("ul");
	ul.className = "dinext-workspace-hub__list-items";
	items.forEach((item) => {
		const li = document.createElement("li");
		li.append(make_record_link(item));
		ul.append(li);
	});
	wrap.append(ul);
	return wrap;
};

const make_create_bar = (actions) => {
	if (!actions || !actions.length) {
		return null;
	}

	const buttons = document.createElement("div");
	buttons.className = "dinext-workspace-hub__create-buttons";
	actions.forEach((action) => {
		const button = document.createElement("button");
		button.type = "button";
		button.className = "dinext-workspace-hub__create-btn";
		const label_text = __(action.label || action.doctype);
		button.title = label_text;
		const icon = make_icon("add", "xs");
		if (icon) {
			icon.className = "dinext-workspace-hub__create-btn-icon";
			button.append(icon);
		}
		const label = document.createElement("span");
		label.className = "dinext-workspace-hub__create-btn-label";
		label.textContent = label_text;
		button.append(label);
		button.addEventListener("click", (event) => {
			event.preventDefault();
			if (frappe.new_doc) {
				frappe.new_doc(action.doctype);
			} else {
				frappe.set_route("Form", action.doctype, "new");
			}
		});
		buttons.append(button);
	});
	return buttons;
};

const make_section_lists = (lists) => {
	if (!lists) {
		return null;
	}

	const wrap = document.createElement("div");
	wrap.className = "dinext-workspace-hub__personal";

	const create_bar = make_create_bar(lists.create_actions || []);
	if (create_bar) {
		wrap.append(create_bar);
	}

	const groups = document.createElement("div");
	groups.className = "dinext-workspace-hub__lists";

	const list_nodes = [];
	if (lists.show_attention) {
		list_nodes.push(make_list("Needs Attention", lists.attention || []));
	}
	if (lists.show_assigned) {
		list_nodes.push(make_list("Assigned to Me", lists.assigned || []));
	}
	if (lists.show_liked) {
		list_nodes.push(make_list("Liked", lists.liked || []));
	}
	list_nodes.forEach((node) => {
		if (node) {
			groups.append(node);
		}
	});

	if (groups.childElementCount) {
		wrap.append(groups);
	}

	if (!wrap.childElementCount) {
		return null;
	}
	return wrap;
};

const get_shadow_host = (hub) => {
	const root = hub.getRootNode();
	return root && root.host ? root.host : null;
};

const tour_kit = () => window.dinext_common && dinext_common.ui_tour;

const clear_tour_anchors = (hub) => {
	const kit = tour_kit();
	if (kit && typeof kit.clear_anchors === "function") {
		kit.clear_anchors(hub);
	}
};

const tour_source = (scroll, rect_nodes, visible_nodes) => {
	const rects = rect_nodes && rect_nodes.length ? rect_nodes : scroll ? [scroll] : [];
	return {
		scroll,
		rect_nodes: rects,
		visible_nodes: visible_nodes && visible_nodes.length ? visible_nodes : rects,
	};
};

const is_help_section_label = (label) => {
	const value = String(label || "").trim();
	return value === "Help" || value === __("Help");
};

const resolve_tour_sources = (hub) => {
	const sources = {};
	const lists = hub.querySelector(".dinext-workspace-hub__lists");
	if (lists) {
		const titles = [...lists.querySelectorAll(".dinext-workspace-hub__list-title")];
		if (titles.length) {
			sources["personal-lists"] = tour_source(titles[0], titles, titles);
		}
	}
	hub.querySelectorAll(".dinext-workspace-hub__section").forEach((section) => {
		const key = section.getAttribute("data-dinext-section") || "";
		const heading = section.querySelector("h3");
		if (!heading) {
			return;
		}
		if (is_help_section_label(key) || is_help_section_label(heading.textContent)) {
			const card = section.querySelector('a[href^="https://docs.dinext.ru"]');
			const help_node = card || heading;
			sources.help = tour_source(help_node, [help_node], [help_node]);
			return;
		}
		const cards = section.querySelector(".dinext-workspace-hub__cards");
		if (cards && cards.childElementCount && !sources.directions) {
			sources.directions = tour_source(heading, [heading], [heading]);
		}
	});
	return sources;
};

const sync_tour_anchors = (hub, settled) => {
	const kit = tour_kit();
	if (!hub || !hub.isConnected) {
		if (hub) {
			clear_tour_anchors(hub);
		}
		return;
	}
	if (!kit || typeof kit.place_anchor !== "function") {
		return;
	}
	if (hub.getAttribute("data-settings-name") !== DINEXT_TOUR_SETTINGS) {
		clear_tour_anchors(hub);
		return;
	}
	const host = get_shadow_host(hub);
	if (!host || !document.body) {
		clear_tour_anchors(hub);
		return;
	}
	ensure_light_hub_styles(hub);
	const sources = resolve_tour_sources(hub);
	let placed = 0;
	let attempted = 0;
	DINEXT_TOUR_IDS.forEach((id) => {
		const source = sources[id];
		if (source) {
			attempted += 1;
		}
		const el = kit.place_anchor(id, source ? { ...source, host } : null, { owner: hub });
		if (el) {
			placed += 1;
		}
	});
	if (settled && (placed || !attempted) && typeof kit.mark_ready === "function") {
		kit.mark_ready(hub);
	}
};

const sync_mounted_tour_anchors = (hub) => {
	if (hub) {
		sync_tour_anchors(hub);
		return;
	}
	for (const mounted of [...mounted_hubs]) {
		if (!mounted.isConnected) {
			clear_tour_anchors(mounted);
			mounted_hubs.delete(mounted);
			continue;
		}
		sync_tour_anchors(mounted);
	}
};

const schedule_tour_anchors = (hub) => {
	requestAnimationFrame(() => sync_tour_anchors(hub));
};

const render = (hub, payload) => {
	const token = (hub_render_tokens.get(hub) || 0) + 1;
	hub_render_tokens.set(hub, token);
	hub.replaceChildren();
	for (const section of payload.sections || []) {
		const group = document.createElement("section");
		group.className = "dinext-workspace-hub__section";
		group.setAttribute(
			"data-dinext-section",
			is_help_section_label(section.label) ? "Help" : section.label || ""
		);
		const heading = document.createElement("h3");
		heading.textContent = __(section.label);
		group.append(heading);

		const cards = document.createElement("div");
		cards.className = "dinext-workspace-hub__cards";
		const items = section.items || [];
		const columns = Math.max(1, parseInt(section.card_columns, 10) || 4);
		cards.style.setProperty(
			"--dinext-hub-card-columns",
			String(Math.min(columns, Math.max(1, items.length)))
		);
		items.forEach((item) => cards.append(make_card(item)));
		if (cards.childElementCount) {
			group.append(cards);
		}

		const personal = make_section_lists(section.lists);
		if (personal) {
			group.append(personal);
		}

		hub.append(group);
	}
	paint_page_lists(payload)
		.then((pages) => {
			if (hub_render_tokens.get(hub) !== token || !hub.isConnected) {
				return;
			}
			if (pages) {
				hub.prepend(pages);
			}
			if (!hub.childElementCount) {
				const empty = document.createElement("p");
				empty.textContent = __("No available directions.");
				hub.append(empty);
			}
			schedule_tour_anchors(hub);
		})
		.finally(() => {
			schedule_tour_anchors(hub);
		});
};

const hub_stylesheet_href = () => {
	const version =
		(window.frappe && frappe.boot && frappe.boot.versions && frappe.boot.versions.dinext_common) ||
		"dev";
	return `${DINEXT_WORKSPACE_HUB_CSS}?v=${encodeURIComponent(`${version}-${DINEXT_WORKSPACE_HUB_ASSETS}`)}`;
};

const attach_hub_stylesheet = (root, onload) => {
	if (!root) {
		return null;
	}
	const existing = root.querySelector("link[data-dinext-workspace-hub]");
	if (existing) {
		if (onload) {
			if (existing.sheet) {
				onload();
			} else {
				existing.addEventListener("load", onload, { once: true });
			}
		}
		return existing;
	}
	const link = document.createElement("link");
	link.rel = "stylesheet";
	link.setAttribute("data-dinext-workspace-hub", "1");
	link.href = hub_stylesheet_href();
	if (onload) {
		link.addEventListener("load", onload, { once: true });
	}
	root.append(link);
	return link;
};

const ensure_light_hub_styles = (hub) => {
	attach_hub_stylesheet(document.head, () => schedule_tour_anchors(hub));
};

const ensure_styles = (root_element) => {
	attach_hub_stylesheet(root_element);
	attach_hub_stylesheet(document.head);
};

const is_workspace_route = () => {
	const route =
		(window.frappe && frappe.get_route && frappe.get_route()) ||
		(window.frappe && frappe.router && frappe.router.current_route) ||
		[];
	return Array.isArray(route) && route[0] === "Workspaces";
};

const load_hub = (hub, settings_name) => {
	const token = (hub_load_tokens.get(hub) || 0) + 1;
	hub_load_tokens.set(hub, token);
	const name = settings_name || hub.getAttribute("data-settings-name") || "Dinext";
	frappe
		.call({
			method: "dinext_common.workspace_hub.get_workspace_hub",
			args: { settings_name: name },
		})
		.then(({ message }) => {
			const payload = message || { sections: [] };
			if (hub_load_tokens.get(hub) !== token || !hub.isConnected) {
				return;
			}
			render(hub, payload);
		})
		.catch(() => {
			if (hub_load_tokens.get(hub) !== token || !hub.isConnected) {
				return;
			}
			render(hub, { sections: [] });
		});
};

const refresh_connected_hubs = () => {
	for (const hub of [...mounted_hubs]) {
		if (!hub.isConnected) {
			clear_tour_anchors(hub);
			mounted_hubs.delete(hub);
			continue;
		}
		const mounted_ms = Date.now() - (hub_mounted_at.get(hub) || 0);
		if (mounted_ms < 400) {
			continue;
		}
		load_hub(hub, hub.getAttribute("data-settings-name") || "Dinext");
	}
};

const ensure_router_refresh = () => {
	if (router_refresh_bound) {
		return;
	}
	if (!(window.frappe && frappe.router && frappe.router.on)) {
		return;
	}
	router_refresh_bound = true;
	frappe.router.on("change", () => {
		if (!is_workspace_route()) {
			return;
		}
		refresh_connected_hubs();
	});
};

dinext_common.workspace_hub.sync_tour_anchors = sync_mounted_tour_anchors;

dinext_common.workspace_hub.mount = function (root_element, settings_name) {
	if (!root_element) {
		return;
	}
	const hub = root_element.querySelector(".dinext-workspace-hub");
	if (!hub) {
		return;
	}
	ensure_styles(root_element);
	const name = settings_name || hub.getAttribute("data-settings-name") || "Dinext";
	hub.setAttribute("data-settings-name", name);
	mounted_hubs.add(hub);
	hub_mounted_at.set(hub, Date.now());
	ensure_router_refresh();
	load_hub(hub, name);
};
