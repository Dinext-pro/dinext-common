const method = "dinext_common.tests.ui_test_helpers";

const load = () => Cypress.env("waDesk");

const workflowActionRequests = (calls) =>
	calls.filter((call) => {
		const body = call.request.body;
		const raw = typeof body === "string" ? body : JSON.stringify(body || {});
		return raw.includes("Workflow Action");
	});

context("workflow action desk", () => {
	before(() => {
		cy.login("wf.approver2@example.com", "Wf-Test-2026!");
		cy.openDesk("/app");
		cy.call(`${method}.seed_workflow_action_desk`, {}, { timeout: 120000 }).then((res) => {
			Cypress.env("waDesk", res.body.message);
		});
	});

	after(() => {
		cy.login("wf.approver2@example.com", "Wf-Test-2026!");
		cy.openDesk("/app");
		cy.call(`${method}.cleanup_workflow_action_desk`, {}, { timeout: 120000 });
	});

	it("System Manager sees the list and the form", () => {
		const fixture = load();
		cy.login(fixture.manager, fixture.password);
		cy.openDesk("/app/workflow-action");
		cy.get(".list-row-container", { timeout: 20000 }).should("contain", fixture.issue);
		cy.visit(`/app/workflow-action/${fixture.action}`);
		cy.get("[data-fieldname='status']", { timeout: 20000 }).should("be.visible");
		cy.location("pathname").should("include", "/workflow-action/");
	});

	it("Another user sees an empty list", () => {
		const fixture = load();
		cy.login(fixture.approver, fixture.password);
		cy.intercept("POST", "/api/method/frappe.desk.reportview.get").as("reportview");
		cy.openDesk("/app/workflow-action");
		cy.get(".no-result", { timeout: 20000 }).should("be.visible");
		cy.get(".list-row-container").should("not.exist");
		cy.get("@reportview.all").then((calls) => {
			expect(workflowActionRequests(calls)).to.have.length(0);
		});
	});

	it("Another user opening the card lands on the source", () => {
		const fixture = load();
		cy.login(fixture.approver, fixture.password);
		cy.openDesk(`/app/workflow-action/${fixture.action}`);
		cy.location("pathname", { timeout: 20000 }).should("eq", `/app/issue/${fixture.issue}`);
		cy.get(".form-dashboard", { timeout: 20000 }).should("exist");
	});

	it("Missing source does not show the card", () => {
		const fixture = load();
		cy.login(fixture.approver, fixture.password);
		cy.openDesk(`/app/workflow-action/${fixture.blank_action}`);
		cy.location("pathname", { timeout: 20000 }).should(
			"include",
			`/workflow-action/${fixture.blank_action}`
		);
		cy.get("[data-fieldname='status']").should("not.be.visible");
	});
});
