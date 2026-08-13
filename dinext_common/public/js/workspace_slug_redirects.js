/**
 * ISS-2026-02952: Workspace titles renamed RU→EN. Old desk URLs
 * (e.g. /app/мои-задачи) and localStorage.current_page still use RU.
 * Redirect ASAP so reload does not stick on Not Found.
 */
(() => {
	const SLUG_REDIRECTS = {
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
		"Мои проекты": "My Projects",
		"Мои задачи": "My Tasks",
		"Мои Таймшиты": "My Timesheets",
		"Моя доска": "My Board",
		"Фин. Контроль": "Financial Control",
		Аналитика: "Analytics",
		"Скоринг проектов": "Project Scoring",
		Разработки: "Development",
	};

	function normalize_slug(value) {
		if (value == null) return "";
		let s = String(value);
		try {
			s = decodeURIComponent(s);
		} catch (e) {
			/* ignore */
		}
		return s.trim().toLowerCase().replace(/\s+/g, "-");
	}

	function fix_local_storage() {
		try {
			const cur = localStorage.getItem("current_page");
			if (cur && TITLE_REDIRECTS[cur]) {
				localStorage.setItem("current_page", TITLE_REDIRECTS[cur]);
			}
		} catch (e) {
			/* ignore */
		}
	}

	function redirect_from_location() {
		const parts = (location.pathname || "").split("/").filter(Boolean);
		// /app/<slug> or /app/Workspaces/<slug>
		if (parts[0] !== "app" || parts.length < 2) return false;

		let slug_part = parts[1];
		let rebuild_prefix = "/app/";
		if (slug_part.toLowerCase() === "workspaces" && parts[2]) {
			slug_part = parts[2];
			rebuild_prefix = "/app/workspaces/";
		}

		const target = SLUG_REDIRECTS[normalize_slug(slug_part)];
		if (!target) return false;

		const search = location.search || "";
		const hash = location.hash || "";
		location.replace(rebuild_prefix + target + search + hash);
		return true;
	}

	function redirect_via_router() {
		if (!window.frappe || !frappe.get_route || !frappe.set_route) return false;
		const route = frappe.get_route() || [];
		if (!route.length) return false;

		let slug_idx = -1;
		if (String(route[0]).toLowerCase() === "workspaces" && route[1]) {
			slug_idx = 1;
		} else if (route.length === 1) {
			slug_idx = 0;
		} else {
			return false;
		}

		const target = SLUG_REDIRECTS[normalize_slug(route[slug_idx])];
		if (!target) return false;

		const next = route.slice();
		next[slug_idx] = target;
		frappe.set_route(next);
		return true;
	}

	fix_local_storage();

	// Hard navigation first — works even before desk router paints Not Found
	if (redirect_from_location()) {
		return;
	}

	const soft = () => {
		fix_local_storage();
		redirect_via_router();
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", soft);
	} else {
		soft();
	}

	$(document).on("app_ready", soft);
	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on("change", soft);
	}
})();
