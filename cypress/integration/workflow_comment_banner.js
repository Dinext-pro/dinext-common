Cypress.removeAllListeners("uncaught:exception");
const helper = "dinext_common.tests.required_pending_ui";
const api = "dinext_common.workflow_approval.api.get_workflow_comments";
const banner = ".form-message.orange.dinext-workflow-comments";
let fixture;

function setComments(mode) {
	cy.call(`${helper}.set_workflow_comments_cypress`, { mode });
	cy.window().then((win) => win.cur_frm.reload_doc());
}

context("Required Workflow comments on document forms", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed_required_pending_cypress`, {}, { timeout: 180000 })
			.then((res) => { fixture = res.body.message; });
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_required_pending_cypress`, {}, { timeout: 180000 });
	});
	beforeEach(() => {
		cy.login(fixture.viewer, fixture.password);
		cy.openDesk("/app");
		cy.call(`${helper}.set_workflow_comments_cypress`, { mode: "empty" });
		cy.openDesk(`/app/issue/${encodeURIComponent(fixture.issue)}`);
		cy.get(".dinext-pending-approvers").should("be.visible");
	});

	it("shows a required personal comment before the round has transitioned", () => {
		setComments("single");
		cy.get(banner).should("be.visible").and("contain", fixture.required).and("contain", "Correct the dates");
		cy.window().should((win) => expect(win.cur_frm.doc.status).to.eq("Open"));
		cy.get(".dinext-pending-approvers").should("be.visible");
	});

	it("includes all authors even after another action without a comment", () => {
		setComments("mixed");
		cy.get(banner).should("contain", fixture.required).and("contain", fixture.mixed)
			.and("contain", "Correct the dates").and("contain", "Attach the details");
		cy.get(`${banner} .dinext-workflow-comment-row`).should("have.length", 2);
	});

	it("includes a comment authored by the current user", () => {
		setComments("self");
		cy.get(banner).should("contain", fixture.viewer_name).and("contain", "Correct the dates");
	});

	it("clears obsolete comments when a later round has actions without required comments", () => {
		setComments("multiple");
		cy.get(banner).should("be.visible");
		setComments("later");
		cy.get(banner).should("not.exist");
		cy.get(".dinext-pending-approvers").should("be.visible");
	});

	it("escapes text, wraps in both themes and preserves other messages on refresh", () => {
		setComments("unsafe");
		cy.get(banner).should("contain", "<img");
		cy.viewport(420, 800);
		cy.window().then((win) => {
			win.cur_frm.dashboard.add_comment("Other orange message", "orange", true);
			void win.cur_frm.script_manager.trigger("refresh");
		});
		for (const theme of ["dark", "light"]) {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			cy.window().then((win) => win.frappe.after_ajax());
			cy.get(banner).should("have.length", 1).and("be.visible").and("contain", "First line");
			cy.get(`${banner} img`).should("not.exist");
			cy.get(banner).should(($el) => expect($el[0].scrollWidth).to.be.at.most($el[0].clientWidth + 1));
			cy.get(banner).scrollIntoView().screenshot(`workflow-comment-${theme}`);
			cy.get(banner).should("be.visible");
		}
		cy.contains(".form-message.orange", "Other orange message").should("be.visible");
		cy.window().should((win) => expect(win.commentExecuted).to.eq(undefined));
		cy.viewport(1440, 900);
	});

	it("discards a delayed comment response after navigating away", () => {
		let release;
		let started = false;
		let form;
		const gate = new Promise((resolve) => { release = resolve; });
		cy.intercept({ method: "POST", url: `**/api/method/${api}`, times: 1 }, (req) => {
			started = true;
			req.continue((res) => {
				res.body.message = [{ author: "old", author_name: "Old author", comment: "Stale comment" }];
				return gate;
			});
		}).as("lateComments");
		cy.window().then((win) => {
			form = win.cur_frm;
			void win.frappe.dinext.refreshWorkflowComments(form);
		});
		cy.wrap(null).should(() => expect(started).to.eq(true));
		cy.window().then((win) => { void win.frappe.set_route("List", "Issue", "List"); });
		cy.window().should((win) => expect(win.frappe.get_route_str()).to.match(/^List\/Issue/));
		cy.then(release);
		cy.wait("@lateComments");
		cy.then(() => expect(form.layout.message.children(".dinext-workflow-comments").text()).not.to.contain("Stale comment"));
	});
});
