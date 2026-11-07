Cypress.removeAllListeners("uncaught:exception");
Cypress.on("window:before:load", (win) => {
	win.addEventListener("unhandledrejection", (event) => {
		throw event.reason;
	});
});
const api = "dinext_common.tests.workflow_style_ui";
const formPath = () =>
	`/app/workflow-style-fixture/${encodeURIComponent(Cypress.env("style").name)}`;
const tokens = {
	primary: "--text-on-blue",
	info: "--text-on-light-blue",
	success: "--text-on-green",
	warning: "--text-on-orange",
	danger: "--text-on-red",
	inverse: "--text-color",
};
const darkTokens = {
	primary: "--blue-300",
	info: "--blue-300",
	success: "--green-300",
	warning: "--orange-300",
	danger: "--red-300",
	inverse: "--text-color",
};

function checkColor(label, style) {
	cy.contains(".page-container:visible .dinext-workflow-transition", label)
		.should("be.visible")
		.and("have.attr", "data-workflow-style", style)
		.should(($label) => {
			expect($label.closest(".disabled")).to.have.length(0);
		})
		.then(($label) => {
			const element = $label[0];
			const doc = element.ownerDocument;
			const probe = doc.createElement("span");
			const palette = doc.documentElement.dataset.theme === "dark" ? darkTokens : tokens;
			probe.style.color = `var(${palette[style] || "--text-color"})`;
			doc.body.appendChild(probe);
			const actual = doc.defaultView.getComputedStyle(element).color;
			expect(actual).to.eq(doc.defaultView.getComputedStyle(probe).color);
			probe.remove();
			const icon = element.querySelector("svg.icon");
			if (icon) {
				expect(doc.defaultView.getComputedStyle(icon).stroke).to.eq(actual);
				expect(doc.defaultView.getComputedStyle(icon.querySelector("use")).fill).to.eq(
					actual
				);
			}
		});
}

function theme(value) {
	cy.window().then((win) => {
		win.document.documentElement.dataset.theme = value;
	});
}

context("Workflow destination styles", { viewportWidth: 1280, viewportHeight: 720 }, () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${api}.seed_workflow_styles`).then((res) => {
			Cypress.env("style", res.body.message);
		});
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${api}.cleanup_workflow_styles`);
	});

	it("Document form actions", () => {
		cy.login();
		cy.visit(formPath());
		cy.get(".page-container:visible .actions-btn-group > button").click();
		for (const style of Object.keys(tokens))
			checkColor(
				style === "success"
					? "Style approve"
					: style === "danger"
					? "Style reject"
					: `Style ${style[0].toUpperCase()}${style.slice(1)}`,
				style
			);
		cy.contains(".dinext-workflow-transition", "Style approve").find("svg").should("exist");
		cy.screenshot("workflow-form-light");
		cy.visit(`/app/workflow-task/${encodeURIComponent(Cypress.env("style").task)}`);
		cy.get(
			'.page-container:visible .inner-group-button[data-label="Workflow"] > button'
		).click();
		checkColor("Style approve", "success");
		checkColor("Style reject", "danger");
	});

	it("List View actions", () => {
		cy.login();
		cy.visit("/app/workflow-style-fixture");
		cy.get(".list-row-checkbox").first().check({ force: true });
		cy.get(".page-container:visible .actions-btn-group > button").click();
		checkColor("Style approve", "success");
		checkColor("Style reject", "danger");
		cy.screenshot("workflow-list-light");
	});

	it("keeps standard list actions available while looking up the checked documents", () => {
		cy.login();
		cy.intercept(
			"POST",
			"**/api/method/dinext_common.workflow_approval.api.get_common_list_transitions",
			(request) => {
				request.continue((response) => response.setDelay(1000));
			}
		).as("commonListTransitions");
		cy.visit("/app/workflow-style-fixture");
		cy.get(".list-row-checkbox").first().check({ force: true });
		const group = ".page-container:visible .actions-btn-group";
		cy.get(`${group} > button`).click();
		cy.get(`${group} .dinext-workflow-menu-status`).should("be.visible");
		cy.get(`${group} .dropdown-item:visible`).should("have.length.greaterThan", 0);
		cy.get(`${group} .dinext-workflow-transition`).should("not.exist");
		cy.wait("@commonListTransitions");
		checkColor("Style approve", "success");
		checkColor("Style reject", "danger");
		cy.get(`${group} > button`).click();
		cy.get(`${group} .dinext-workflow-transition`).should("not.exist");
	});

	it("locks the Workflow form until reload and finishes quietly for one document", () => {
		cy.login();
		let requests = 0;
		cy.intercept("POST", "**/api/method/frappe.model.workflow.apply_workflow", (request) => {
			requests += 1;
			request.reply({ delay: 800, body: { message: { status: "Completed" } } });
		}).as("styleVote");
		cy.visit(formPath());
		cy.get(".page-container:visible .actions-btn-group > button").click();
		const action = ".page-container:visible .actions-btn-group .dinext-workflow-transition";
		cy.contains(action, "Style approve").click();
		cy.get('.page-container:visible[aria-busy="true"]').should("have.prop", "inert", true);
		cy.window().then((win) => {
			const event = new win.KeyboardEvent("keydown", {
				key: "s",
				ctrlKey: true,
				bubbles: true,
				cancelable: true,
			});
			expect(win.document.dispatchEvent(event), "Ctrl+S is blocked").to.eq(false);
			expect(win.frappe.cur_progress == null).to.eq(true);
		});
		cy.wait("@styleVote");
		cy.get('.page-container:visible[aria-busy="true"], #freeze').should("not.exist");
		cy.get(".modal:visible").should("not.exist");
		cy.get(".page-container:visible .actions-btn-group > button").should("be.visible");
		cy.then(() => expect(requests).to.eq(1));
	});

	it("Neutral fallback and action name independence", () => {
		cy.login();
		cy.visit(formPath());
		cy.get(".page-container:visible .actions-btn-group > button").click();
		checkColor("Style neutral", "");
		cy.call(`${api}.set_workflow_style`, {
			state: Cypress.env("style").states.Success,
			style: "Warning",
		});
		cy.reload();
		cy.get(".page-container:visible .actions-btn-group > button").click();
		checkColor("Style approve", "warning");
		cy.call(`${api}.set_workflow_style`, {
			state: Cypress.env("style").states.Success,
			style: "Success",
		});
	});

	it("Runtime theme switch", () => {
		cy.login();
		cy.visit(formPath());
		cy.get(".page-container:visible .actions-btn-group > button").click();
		theme("light");
		checkColor("Style approve", "success");
		checkColor("Style reject", "danger");
		theme("dark");
		checkColor("Style approve", "success");
		checkColor("Style reject", "danger");
		cy.screenshot("workflow-form-dark");
		cy.visit("/app/workflow-style-fixture");
		cy.get(".list-row-checkbox").first().check({ force: true });
		cy.get(".page-container:visible .actions-btn-group > button").click();
		theme("dark");
		checkColor("Style approve", "success");
		checkColor("Style reject", "danger");
		cy.screenshot("workflow-list-dark");
		theme("light");
		checkColor("Style approve", "success");
	});
});
