Cypress.removeAllListeners("uncaught:exception");
const helper = "dinext_common.tests.required_pending_ui";
const bannerApi = "dinext_common.workflow_approval.api.get_form_approval_banner";
const banner = ".dinext-pending-approvers";
let fixture;

function setOptional(value) {
	return cy.call(`${helper}.set_required_pending_optional`, {
		doctype: "Issue",
		optional: value,
	});
}
function assertNames() {
	cy.get(banner)
		.should("be.visible")
		.and("contain", fixture.required)
		.and("contain", fixture.mixed)
		.and("not.contain", fixture.optional);
	cy.get(banner).should("contain", fixture.viewer_name);
}
function assertEmpty() {
	cy.get(banner).should("not.exist");
}
function readPending() {
	return cy.call(bannerApi, { doctype: "Issue", name: fixture.issue });
}

function readActions() {
	return cy
		.window()
		.then((win) =>
			cy.call("dinext_common.workflow_approval.api.get_transitions", {
				doc: JSON.stringify(win.cur_frm.doc),
			})
		)
		.then((res) => res.body.message.map((row) => row.action));
}

context("Mandatory target pending actors generic", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed_required_pending_cypress`, {}, { timeout: 180000 }).then((res) => {
			fixture = res.body.message;
		});
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_required_pending_cypress`, {}, { timeout: 180000 });
	});
	beforeEach(() => {
		cy.login(fixture.viewer, fixture.password);
		cy.openDesk("/app");
		setOptional(0);
		cy.openDesk(`/app/issue/${encodeURIComponent(fixture.issue)}`);
		cy.window().should((win) => expect(win.cur_frm?.doc?.name).to.eq(fixture.issue));
	});

	it("shows mandatory-only and mixed actors using personal target states", () => {
		assertNames();
		cy.window().then((win) => win.frappe.ui.set_theme("dark"));
		assertNames();
		cy.window().then((win) => win.frappe.ui.set_theme("light"));
		assertNames();
		cy.screenshot("required-pending-generic", { capture: "viewport" });
	});

	it("clears the pending display when all targets become optional", () => {
		let actions;
		readActions().then((value) => {
			actions = value;
		});
		assertNames();
		setOptional(1);
		cy.window().then((win) => win.cur_frm.reload_doc());
		readPending().then((res) => {
			expect(res.body.message.pending_approvers).to.have.length(0);
			expect(res.body.message.round_status).to.eq("Open");
		});
		assertEmpty();
		readActions().then((value) => expect(value).to.deep.eq(actions));
	});

	it("reflects a changed checkbox on an existing round without rebuilding it", () => {
		let original;
		readPending().then((res) => {
			original = JSON.stringify(res.body.message);
		});
		setOptional(1);
		cy.window().then((win) => win.cur_frm.reload_doc());
		assertEmpty();
		setOptional(0);
		cy.window().then((win) => win.cur_frm.reload_doc());
		assertNames();
		readPending().then((res) => expect(JSON.stringify(res.body.message)).to.eq(original));
	});
});
