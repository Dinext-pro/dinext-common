const fixtureMethod = "dinext_common.tests.workflow_delegation_ui";
const voteMethod = "dinext_common.workflow_approval.api.vote";

describe("Delegated Workflow decision audit", () => {
	const marker = "wf-audit-" + Cypress._.times(12, () => Cypress._.random(0, 35).toString(36)).join("");
	let fixture;

	before(() => {
		cy.login();
		cy.openDesk();
		cy.call(fixtureMethod + ".seed", { marker }).its("body.message").then((data) => {
			fixture = data;
		});
	});

	after(() => {
		if (!fixture) return;
		cy.login();
		cy.openDesk();
		cy.call(fixtureMethod + ".cleanup", { marker });
	});

	it("shows the deputy and effective approver on the task, timeline and history report", () => {
		cy.login(fixture.deputy, fixture.password);
		cy.openDesk();
		cy.call("frappe.core.doctype.user.user.impersonate", {
			user: fixture.approver,
			reason: "Synthetic Workflow audit",
		});
		cy.request("/api/method/frappe.auth.get_logged_user").its("body.message").should("eq", fixture.approver);

		cy.openDesk("/app/workflow-task/" + encodeURIComponent(fixture.task));
		cy.window().should((win) => {
			expect(win.cur_frm?.doc?.name).to.eq(fixture.task);
			expect(win.cur_frm.doc.approver).to.eq(fixture.approver);
		});
		cy.intercept("POST", "**/api/method/" + voteMethod).as("delegatedVote");
		const workflowGroup = ".page-container:visible .inner-group-button[data-label='Workflow']";
		cy.get(workflowGroup + " > button").click();
		cy.contains(workflowGroup + " .dropdown-item", fixture.action).click();
		cy.wait("@delegatedVote").then(({ response }) => {
			expect(response.statusCode).to.eq(200);
			expect(response.body.message.transitioned).to.eq(true);
		});
		cy.window().should((win) => {
			const task = win.cur_frm.doc;
			expect(task.status).to.eq("Completed");
			expect(task.performed_by).to.eq(fixture.deputy);
			expect(task.performed_as).to.eq(fixture.approver);
		});
		for (const [field, labels] of [
			["performed_by", [fixture.deputy, fixture.deputy_label]],
			["performed_as", [fixture.approver, fixture.approver_label]],
		]) {
			cy.get("[data-fieldname='" + field + "']:visible").first().scrollIntoView()
				.should("be.visible").and(($field) => {
					expect(labels.some((label) => $field.text().includes(label))).to.eq(true);
				});
		}
		cy.screenshot("workflow-delegation-task", { capture: "viewport" });

		cy.openDesk("/app/issue/" + encodeURIComponent(fixture.issue));
		const auditText = new RegExp(fixture.deputy_label + "[\\s\\S]*on behalf of[\\s\\S]*" + fixture.approver_label);
		cy.contains(".timeline-item", auditText).scrollIntoView().should("be.visible");
		cy.screenshot("workflow-delegation-timeline", { capture: "viewport" });

		cy.openDesk("/app/query-report/My%20Approval%20History?ignore_prepared_report=1");
		cy.window().should((win) => {
			const report = win.frappe.query_report;
			expect(report.report_name).to.eq("My Approval History");
			expect(report.get_filter("workflow")).to.exist;
		});
		cy.window().then((win) => win.frappe.query_report.set_filter_value("workflow", fixture.workflow));
		cy.window().should((win) => {
			const report = win.frappe.query_report;
			expect(report.data).to.have.length(1);
			expect(report.data[0]).to.include({
				name: fixture.task, performed_by: fixture.deputy, performed_as: fixture.approver,
			});
			expect(report.datatable.datamanager.getColumns().map((column) => column.id))
				.to.include.members(["performed_by", "performed_as"]);
		});
		for (const label of [fixture.deputy, fixture.approver]) {
			cy.contains(".dt-scrollable .dt-cell", label).scrollIntoView().should("be.visible");
		}
		cy.screenshot("workflow-delegation-history", { capture: "viewport" });
	});
});
