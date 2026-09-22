const method = "dinext_common.tests.ui_test_helpers";

const load = () => Cypress.env("wf");

const asUser = (email) => {
	const fixture = load();
	cy.login(email, fixture.password);
	cy.openDesk("/app");
};

const activate = (workflow) => cy.call(`${method}.activate_issue_workflow`, { name: workflow });

context("parallel workflow role split", () => {
	before(() => {
		cy.login("wf.approver2@example.com", "Wf-Test-2026!");
		cy.openDesk("/app");
		cy.call(`${method}.seed_parallel_workflow_cypress`).then((res) => {
			Cypress.env("wf", res.body.message);
		});
	});

	after(() => {
		cy.login("wf.approver2@example.com", "Wf-Test-2026!");
		cy.openDesk("/app");
		cy.call(`${method}.cleanup_parallel_workflow_cypress`);
	});

	it("Two reject actions in one state", () => {
		const fixture = load();
		expect(fixture.duplicate_rejected).to.eq(true);
		expect(fixture.duplicate_message).to.include("unique");
		expect(fixture.split_labels).to.deep.eq(["Cypress Split", "Cypress Split"]);
	});

	it("One role votes by name", () => {
		const fixture = load();
		asUser(fixture.approver);
		activate(fixture.split_workflow);
		cy.call("dinext_common.workflow_approval.api.apply_workflow", {
			doc: { doctype: "Issue", name: fixture.split_one },
			action: fixture.split_action,
			request_id: `cy-split-name-${Date.now()}`,
		}).then((res) => {
			expect(res.body.message.transitioned).to.eq(true);
		});
		cy.call("frappe.client.get_value", {
			doctype: "Issue",
			filters: fixture.split_one,
			fieldname: "status",
		})
			.its("body.message.status")
			.should("eq", "Replied");
	});

	it("Both roles require a UUID", () => {
		const fixture = load();
		asUser(fixture.approver_b);
		activate(fixture.split_workflow);
		cy.call(
			"dinext_common.workflow_approval.api.apply_workflow",
			{
				doc: { doctype: "Issue", name: fixture.split_both },
				action: fixture.split_action,
				request_id: `cy-split-ambiguous-${Date.now()}`,
			},
			{ failOnStatusCode: false }
		).then((res) => {
			expect(res.status).to.be.oneOf([400, 403, 417]);
			expect(JSON.stringify(res.body)).to.include("transition UUID");
		});
		cy.call("frappe.client.get_value", {
			doctype: "Issue",
			filters: fixture.split_both,
			fieldname: "status",
		})
			.its("body.message.status")
			.should("eq", "Open");
	});

	it("Both roles vote by UUID", () => {
		const fixture = load();
		asUser(fixture.approver_b);
		activate(fixture.split_workflow);
		cy.visit(`/app/issue/${fixture.split_buttons}`);
		cy.contains(
			".dropdown-item, .actions-btn-group, button, a",
			`Cypress Split (_Cypress WF Approver → Replied)`
		).should("exist");
		cy.contains(
			".dropdown-item, .actions-btn-group, button, a",
			`Cypress Split (_Cypress WF Approver B → Closed)`
		).should("exist");
		cy.intercept("POST", "**/api/method/frappe.model.workflow.apply_workflow").as("splitVote");
		cy.contains(
			".dropdown-item, .actions-btn-group, button, a",
			`Cypress Split (_Cypress WF Approver B → Closed)`
		).click({ force: true });
		cy.wait("@splitVote").then(({ request }) => {
			const body = typeof request.body === "string" ? request.body : JSON.stringify(request.body);
			expect(body).to.include(fixture.split_uuid_b);
		});
		cy.call("dinext_common.workflow_approval.api.apply_workflow", {
			doc: { doctype: "Issue", name: fixture.split_both },
			action: fixture.split_action,
			transition_uuid: fixture.split_uuid_b,
			request_id: `cy-split-uuid-${Date.now()}`,
		}).then((res) => {
			expect(res.body.message.transitioned).to.eq(true);
		});
		cy.call("frappe.client.get_value", {
			doctype: "Issue",
			filters: fixture.split_both,
			fieldname: "status",
		})
			.its("body.message.status")
			.should("eq", "Closed");
	});
});
