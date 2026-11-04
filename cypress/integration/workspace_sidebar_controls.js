const duplicate = ".desk-sidebar .duplicate-page";
const section = ".desk-sidebar .standard-sidebar-section";
const parentItem = '.desk-sidebar [item-name="Dinext"]';

function route(value) {
	cy.window().then((win) => {
		win.document.body.dataset.route = value === "Workspaces" ? "Workspaces/Dinext" : value;
		// The live sidebar is moved into the active page container by Dinext.
		const page = win.document.createElement("div");
		page.dataset.pageRoute = value;
		page.appendChild(win.document.querySelector(".layout-main"));
		win.document.querySelector("[data-page-route]").replaceWith(page);
	});
}

function theme(value) {
	cy.document().then((doc) => { doc.documentElement.dataset.theme = value; });
}

function render() {
	cy.task("sidebarAssets").then((assets) => {
		cy.intercept("GET", "/__sidebar_acceptance", {
			headers: { "content-type": "text/html" },
			body: "<!doctype html><html><head></head><body></body></html>",
		});
		cy.visit("/__sidebar_acceptance");
		cy.window().then((win) => {
			win.__ = (value) => value;
			win.frappe = {
				standard_pages: {}, views: {}, utils: {},
				router: { slug: (value) => value.toLowerCase().replace(/ /g, "-") },
				provide(name) {
					let target = win;
					for (const part of name.split(".")) target = target[part] ||= {};
				},
			};
			win.eval(assets.jquery);
			win.eval(assets.utils);
			// Icons are decorative; item, action and expansion builders are unmodified.
			win.frappe.utils.icon = (name) => `<svg class="icon"><use href="#${name}"></use></svg>`;
			win.eval(assets.workspace);
			const doc = win.document;
			const style = doc.createElement("style");
			style.textContent = assets.deskCss + "\n" + assets.sidebarCss;
			doc.head.appendChild(style);
			doc.body.className = "dinext-ws-sidebar-collapsed dinext-ws-sidebar-hover-open";
			doc.body.dataset.route = "Workspaces/Dinext";
			doc.body.innerHTML = `<div data-page-route="Workspaces"><div class="row layout-main">
				<div class="layout-side-section dinext-ws-rail-section">
				<div class="list-sidebar overlay-sidebar"><div class="desk-sidebar">
				<div class="standard-sidebar-section"></div></div></div></div>
				<div class="layout-main-section-wrapper">Page content</div></div></div>`;
			const workspace = Object.create(win.frappe.views.Workspace.prototype);
			const item = { title: "Dinext", public: 1, is_editable: false, selected: true };
			const child = { title: "Development", parent_page: "Dinext", public: 1, is_hidden: 0 };
			Object.assign(workspace, {
				indicator_colors: ["green"], current_page: { name: "Dinext" },
				public_pages: [item, child], private_pages: [], is_read_only: true,
				duplicate_page: cy.stub().as("duplicateWorkspace"),
			});
			const $item = workspace.sidebar_item_container(item);
			const $control = $item.find(".sidebar-item-control");
			workspace.add_sidebar_actions(item, $control);
			workspace.add_drop_icon(item, $control, $item);
			$item.find(".sidebar-child-item").addClass("hidden").append("Child workspace");
			win.$(section).append($item);
		});
	});
}

describe("Workspace sidebar controls", () => {
	beforeEach(render);

	it("hides duplication on desktop List, Form, report and Page in both themes", () => {
		for (const width of [992, 1440]) {
			cy.viewport(width, 900);
			for (const value of ["List/Task/List", "Form/Task/EXAMPLE", "query-report/Example", "custom-page"]) {
				route(value);
				for (const mode of ["light", "dark"]) {
					theme(mode);
					cy.get(duplicate).should("exist").and("not.be.visible");
					cy.get(`${parentItem} .item-anchor`).should("be.visible").and("have.attr", "href", "/app/dinext");
					cy.get(`${parentItem} .drop-icon`).should("be.visible").click();
					cy.get(`${parentItem} .sidebar-child-item`).should("not.have.class", "hidden");
					cy.get(`${parentItem} .drop-icon`).click();
				}
			}
		}
	});

	it("keeps native visibility across a Workspace to Task list round trip", () => {
		cy.get(duplicate).should("not.be.visible");
		cy.get(section).invoke("addClass", "show-control");
		cy.get(duplicate).should("be.visible");
		route("List/Task/List");
		cy.get(duplicate).should("not.be.visible");
		cy.document().then((doc) => doc.body.classList.remove("dinext-ws-sidebar-hover-open"));
		cy.get(duplicate).should("not.be.visible");
		cy.document().then((doc) => doc.body.classList.add("dinext-ws-sidebar-hover-open"));
		route("Workspaces");
		cy.get(duplicate).should("be.visible");
		cy.get(section).invoke("removeClass", "show-control");
		cy.get(duplicate).should("not.be.visible");
	});

	it("preserves the workspace customization duplication action", () => {
		cy.get(section).invoke("addClass", "show-control");
		for (const mode of ["light", "dark"]) {
			theme(mode);
			cy.get(duplicate).should("be.visible").click();
		}
		cy.get("@duplicateWorkspace").should("have.been.calledTwice");
	});

	it("leaves native mobile behavior outside the desktop suppression", () => {
		cy.viewport(991, 900);
		cy.get(".overlay-sidebar").invoke("addClass", "opened");
		cy.get(section).invoke("addClass", "show-control");
		cy.get(duplicate).should("be.visible");
		route("List/Task/List");
		cy.get(duplicate).should("be.visible");
		cy.viewport(390, 844);
		cy.get(duplicate).should("be.visible");
	});
});
