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
