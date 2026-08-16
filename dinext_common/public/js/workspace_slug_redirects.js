/**
 * ISS-2026-02952: map legacy RU workspace slugs/titles ↔ EN after rename.
 * Redirect only after boot, and only into a workspace that exists
 * (slug of name or title). Blind pre-boot location.replace breaks
 * sites that still have RU Workspace docs (demodev).
 */
(() => {
	const SLUG_REDIRECTS = {
		home: "dinext",
		"мои-проекты": "my-projects",
		"мои-задачи": "my-tasks",
		"мои-таймшиты": "my-timesheets",
		"моя-доска": "my-board",
		"фин-контроль": "financial-control",
		"фин.-контроль": "financial-control",
		аналитика: "analytics",
		"скоринг-проектов": "project-scoring",
		разработки: "development",
	};

	const TITLE_REDIRECTS = {
		Home: "Dinext",
		"Мои проекты": "My Projects",
		"Мои задачи": "My Tasks",
		"Мои Таймшиты": "My Timesheets",
		"Моя доска": "My Board",
		"Фин. Контроль": "Financial Control",
		Аналитика: "Analytics",
		"Скоринг проектов": "Project Scoring",
		Разработки: "Development",
	};

	const EN_TO_RU_SLUG = {};
	Object.keys(SLUG_REDIRECTS).forEach((ru) => {
		EN_TO_RU_SLUG[SLUG_REDIRECTS[ru]] = ru;
	});

	const EN_TO_RU_TITLE = {};
	Object.keys(TITLE_REDIRECTS).forEach((ru) => {
		EN_TO_RU_TITLE[TITLE_REDIRECTS[ru]] = ru;
	});

	function frappe_slug(name) {
		if (name == null) return "";
		if (window.frappe && frappe.router && typeof frappe.router.slug === "function") {
			return frappe.router.slug(String(name));
		}
		return String(name).toLowerCase().replace(/ /g, "-");
	}

	function normalize_slug(value) {
		if (value == null) return "";
		let s = String(value);
		try {
			s = decodeURIComponent(s);
		} catch (e) {
			/* ignore */
		}
		return frappe_slug(s.trim());
	}

	function boot_ready() {
		return !!(
			window.frappe &&
			frappe.boot &&
			(frappe.boot.allowed_workspaces || frappe.workspaces)
		);
	}

	function workspace_slugs() {
		const slugs = new Set();
		const pages = (frappe.boot && frappe.boot.allowed_workspaces) || [];
		pages.forEach((page) => {
			if (page && page.name) slugs.add(frappe_slug(page.name));
			if (page && page.title) slugs.add(frappe_slug(page.title));
		});
		if (frappe.workspaces) {
			Object.keys(frappe.workspaces).forEach((slug) => slugs.add(slug));
		}
		return slugs;
	}

	function workspace_titles() {
		const titles = new Set();
		const pages = (frappe.boot && frappe.boot.allowed_workspaces) || [];
		pages.forEach((page) => {
			if (page && page.title) titles.add(page.title);
			if (page && page.name) titles.add(page.name);
		});
		return titles;
	}

	function slug_exists(slug) {
		if (!slug) return false;
		return workspace_slugs().has(normalize_slug(slug));
	}

	function resolve_slug(from_slug) {
		const current = normalize_slug(from_slug);
		if (!current) return null;

		const en = SLUG_REDIRECTS[current];
		if (en && slug_exists(en) && en !== current) {
			return en;
		}

		if (EN_TO_RU_SLUG[current] && !slug_exists(current)) {
			const ru = EN_TO_RU_SLUG[current];
			if (slug_exists(ru) && ru !== current) {
				return ru;
			}
		}

		return null;
	}

	function fix_local_storage() {
		if (!boot_ready()) return;
		try {
			const cur = localStorage.getItem("current_page");
			if (!cur) return;
			const titles = workspace_titles();
			const en = TITLE_REDIRECTS[cur];
			if (en && titles.has(en)) {
				localStorage.setItem("current_page", en);
				return;
			}
			const ru = EN_TO_RU_TITLE[cur];
			if (ru && !titles.has(cur) && titles.has(ru)) {
				localStorage.setItem("current_page", ru);
			}
		} catch (e) {
			/* ignore */
		}
	}

	function current_path_slug() {
		const parts = (location.pathname || "").split("/").filter(Boolean);
		if (parts[0] !== "app" || parts.length < 2) return null;
		if (String(parts[1]).toLowerCase() === "private") return null;
		if (String(parts[1]).toLowerCase() === "workspaces" && parts[2]) {
			if (String(parts[2]).toLowerCase() === "private") return null;
			return parts[2];
		}
		return parts[1];
	}

	function current_route_slug() {
		if (!window.frappe || !frappe.get_route) return current_path_slug();
		const route = frappe.get_route() || [];
		if (!route.length) return current_path_slug();
		if (String(route[0]).toLowerCase() === "private") return null;
		if (String(route[0]).toLowerCase() === "workspaces") {
			if (route[1] && String(route[1]).toLowerCase() === "private") return null;
			return route[1] || current_path_slug();
		}
		if (route.length === 1) return route[0];
		return current_path_slug();
	}

	function apply_route(target_slug) {
		if (!target_slug || !window.frappe || !frappe.set_route) return false;
		const now = normalize_slug(current_route_slug());
		if (now === normalize_slug(target_slug)) return false;
		frappe.set_route(target_slug);
		return true;
	}

	function sync() {
		if (!boot_ready()) return;
		fix_local_storage();
		const from = current_route_slug();
		const target = resolve_slug(from);
		if (target) apply_route(target);
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", sync);
	} else {
		sync();
	}

	$(document).on("app_ready", sync);
	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on("change", sync);
	}
})();
