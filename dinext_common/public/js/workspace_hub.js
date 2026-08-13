frappe.provide("dinext_common.workspace_hub");

const DINEXT_WORKSPACE_HUB_CSS = "/assets/dinext_common/css/workspace_hub.css";

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

const make_record_link = (item) => {
	const link = document.createElement("a");
	link.className = "dinext-workspace-hub__chip dinext-workspace-hub__record";
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
		button.className = "dinext-workspace-hub__chip dinext-workspace-hub__create-btn";
		const label_text = __(action.label || action.doctype);
		button.title = label_text;
		const icon = make_icon("add", "xs");
		if (icon) {
			icon.className = "dinext-workspace-hub__create-btn-icon";
			button.append(icon);
		}
		const label = document.createElement("span");
		label.className = "dinext-workspace-hub__chip-label";
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
	if (lists.show_recently_opened) {
		list_nodes.push(make_list("Recently Opened", lists.recent || []));
	}
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

const render = (hub, payload) => {
	hub.replaceChildren();
	for (const section of payload.sections || []) {
		const group = document.createElement("section");
		group.className = "dinext-workspace-hub__section";
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
	if (!hub.childElementCount) {
		const empty = document.createElement("p");
		empty.textContent = __("No available directions.");
		hub.append(empty);
	}
};

const ensure_styles = (root_element) => {
	if (root_element.querySelector("link[data-dinext-workspace-hub]")) {
		return;
	}
	const link = document.createElement("link");
	link.rel = "stylesheet";
	link.setAttribute("data-dinext-workspace-hub", "1");
	const version =
		(window.frappe && frappe.boot && frappe.boot.versions && frappe.boot.versions.dinext_common) ||
		"fill-width";
	link.href = `${DINEXT_WORKSPACE_HUB_CSS}?v=${encodeURIComponent(version)}`;
	root_element.append(link);
};

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
	frappe
		.call({
			method: "dinext_common.workspace_hub.get_workspace_hub",
			args: { settings_name: name },
		})
		.then(({ message }) => render(hub, message || { sections: [] }))
		.catch(() => render(hub, { sections: [] }));
};
