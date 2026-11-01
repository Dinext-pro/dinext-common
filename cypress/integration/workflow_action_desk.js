const method = "dinext_common.tests.ui_test_helpers";

const load = () => Cypress.env("waDesk");

const workflowDocumentRequests = (calls, doctype) =>
	calls.filter((call) => {
		const body = call.request.body;
		const raw = typeof body === "string" ? body : JSON.stringify(body || {});
		return raw.includes(doctype) || raw.includes(encodeURIComponent(doctype));
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
			expect(workflowDocumentRequests(calls, "Workflow Action")).to.have.length(0);
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

	it("System Manager sees the task list and form", () => {
		const fixture = load();
		cy.login(fixture.manager, fixture.password);
		cy.openDesk("/app/workflow-task");
		cy.get(".list-row-container", { timeout: 20000 }).should("contain", fixture.task);
		cy.window().then((win) => {
			const link = win.frappe.listview_settings["Workflow Task"].get_form_link;
			expect(link({ reference_doctype: "Issue", reference_name: fixture.issue })).to.include(
				`/app/issue/${fixture.issue}`
			);
		});
		cy.visit(`/app/workflow-task/${fixture.task}`);
		cy.get("[data-fieldname='status']", { timeout: 20000 }).should("be.visible");
		cy.location("pathname").should("include", "/workflow-task/");
		cy.contains(":visible", "Open source document").should("be.visible");
		["dark", "light"].forEach((theme) => {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			cy.get("[data-fieldname='status']").should("be.visible");
		});
	});

	it("Another user sees an empty task list without requests", () => {
		const fixture = load();
		cy.login(fixture.approver, fixture.password);
		cy.intercept("POST", "/api/method/frappe.desk.reportview.get").as("taskRows");
		cy.intercept("POST", "/api/method/frappe.desk.reportview.get_count").as("taskCount");
		cy.openDesk("/app/workflow-task");
		cy.get(".no-result", { timeout: 20000 }).should("be.visible");
		cy.get(".list-row-container").should("not.exist");
		["dark", "light"].forEach((theme) => {
			cy.window().then((win) => {
				win.frappe.ui.set_theme(theme);
				return win.cur_list.refresh();
			});
			cy.get(".no-result").should("be.visible");
			cy.get(".list-row-container").should("not.exist");
		});
		cy.get("@taskRows.all").then((calls) => {
			expect(workflowDocumentRequests(calls, "Workflow Task")).to.have.length(0);
		});
		cy.get("@taskCount.all").then((calls) => {
			expect(workflowDocumentRequests(calls, "Workflow Task")).to.have.length(0);
		});
	});

	it("Another user opening a task lands on the source", () => {
		const fixture = load();
		cy.login(fixture.approver, fixture.password);
		cy.openDesk(`/app/workflow-task/${fixture.task}`);
		cy.location("pathname", { timeout: 20000 }).should("eq", `/app/issue/${fixture.issue}`);
		cy.get(".form-dashboard", { timeout: 20000 }).should("exist");
	});

	it("Task without a live source does not show fields", () => {
		const fixture = load();
		cy.login(fixture.approver, fixture.password);
		[fixture.deleted_task, fixture.missing_task].forEach((task) => {
			cy.openDesk(`/app/workflow-task/${task}`);
			cy.location("pathname", { timeout: 20000 }).should(
				"include",
				`/workflow-task/${task}`
			);
			["dark", "light"].forEach((theme) => {
				cy.window().then((win) => win.frappe.ui.set_theme(theme));
				cy.get("[data-fieldname='status']").should("not.be.visible");
				cy.get(".custom-actions:visible button").should("not.exist");
			});
		});
	});
});
