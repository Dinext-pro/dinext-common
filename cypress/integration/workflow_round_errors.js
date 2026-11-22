const helper = "dinext_common.tests.workflow_scenario_ui";
let fixture;
let blocked;

describe("next Workflow round without eligible approvers", () => {
	before(() => {
		cy.login();
		cy.openDesk();
		cy.call(`${helper}.seed`, {}).its("body.message").then(data => { fixture = data; });
		cy.call(`${helper}.block_successor_round`, {}).its("body.message").then(data => { blocked = data; });
	});

	after(() => {
		cy.login();
		cy.openDesk();
		cy.call(`${helper}.cleanup`, {});
	});

	it("reports the blocked transition and unlocks the document at its previous state", () => {
		cy.then(() => {
			cy.login(fixture.user, fixture.password);
			cy.openDesk(`/app/cypress-scenario-source/${fixture.documents.a_form}`);
		});
		cy.intercept("POST", "**/api/method/frappe.model.workflow.apply_workflow").as("blockedVote");
		cy.contains(".actions-btn-group .dropdown-item", "Approve").click({ force: true });
		cy.wait("@blockedVote").its("response.body.workflow_error").should(details => {
			expect(details.code).to.equal("no_eligible_approvers");
			expect(details.workflow).to.equal(fixture.workflows[0]);
			expect(details.state).to.equal(blocked.blocked_state);
			expect(details.transitions[0]).to.include({ action: blocked.action, role: blocked.role });
		});
		cy.get(".modal:visible").should("have.length", 1).and("contain", "No eligible approvers");
		cy.get(".modal:visible").should("contain", "Scenario Done A").and("contain", "Reject");
		cy.get(".modal:visible .modal-header .btn-modal-close").click();
		cy.window().should(win => {
			expect(win.cur_frm.doc[fixture.state_fields[0]]).to.equal("Scenario Waiting A");
			expect(win.cur_frm.page.wrapper[0].inert).to.equal(false);
			expect(win.frappe.dom.freeze_count).to.equal(0);
		});
		cy.contains(".actions-btn-group .dropdown-item", "Approve").should("exist");
	});

	it("keeps independent documents and identifies the blocked item in a bulk action", () => {
		cy.then(() => {
			cy.login(fixture.user, fixture.password);
			cy.openDesk("/app/cypress-scenario-source");
		});
		cy.window().should(win => expect(win.cur_list?.filter_area?.set).to.be.a("function"));
		cy.window().then(async win => {
			const names = [fixture.documents.a_list, fixture.documents.b_list];
			await win.cur_list.filter_area.clear(false);
			await win.cur_list.filter_area.set([[fixture.doctype, "name", "in", names]]);
			win.cur_list.last_args = null;
			await win.cur_list.refresh();
		});
		cy.then(() => {
			for (const name of [fixture.documents.a_list, fixture.documents.b_list]) {
				cy.get(`.list-row-checkbox[data-name="${name}"]`).check({ force: true });
			}
		});
		cy.get(".page-container:visible .actions-btn-group button:visible").first().click();
		cy.contains(".dinext-list-workflow-item", "Approve").should("be.visible").click();
		cy.get(".modal:visible textarea[data-fieldname='comment']").type("Bulk action with one blocked item").blur();
		cy.intercept("POST", "**/api/method/frappe.model.workflow.bulk_workflow_approval").as("blockedBulk");
		cy.get(".modal:visible .btn-primary").click();
		cy.wait("@blockedBulk").its("response.body.message").should(outcome => {
			expect(outcome.succeeded).to.have.length(1);
			expect(outcome.succeeded[0].name).to.equal(fixture.documents.b_list);
			expect(outcome.failed).to.have.length(1);
			expect(outcome.failed[0].name).to.equal(fixture.documents.a_list);
			expect(outcome.failed[0].workflow_error.code).to.equal("no_eligible_approvers");
		});
		cy.get(".modal:visible").should("have.length", 1).and("contain", "No eligible approvers");
		cy.get(".modal:visible").should("contain", "Scenario Done A").and("contain", "Reject");
		cy.window().should(win => {
			expect(win.cur_list.page.wrapper[0].inert).to.equal(false);
			expect(win.frappe.dom.freeze_count).to.equal(0);
		});
	});
});
