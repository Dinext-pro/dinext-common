Cypress.removeAllListeners("uncaught:exception");
const helper = "dinext_common.tests.required_pending_ui";
const bannerApi = "dinext_common.workflow_approval.api.get_form_approval_banner";
const banner = ".form-message.blue.dinext-pending-approvers";
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
	cy.get(banner).should("have.length", 1).and("not.contain", fixture.viewer_name);
	cy.get(".form-dashboard .dinext-pending-approvers").should("not.exist");
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

	it("hides the headline when only the current user is pending", () => {
		cy.intercept("POST", `**/api/method/${bannerApi}`, (req) => {
			req.continue((res) => {
				res.body.message.pending_approvers = res.body.message.pending_approvers
					.filter((row) => row.approver === fixture.viewer);
			});
		}).as("onlySelf");
		cy.window().then((win) => win.cur_frm.reload_doc());
		cy.wait("@onlySelf");
		assertEmpty();
	});

	it("keeps pending approvers beside rebuild information", () => {
		cy.intercept("POST", `**/api/method/${bannerApi}`, (req) => {
			req.continue((res) => {
				res.body.message.rounds = [{
					round_id: "cypress-pending-conflict",
					round_status: "Conflicted",
					reference_name: fixture.issue,
					source_title: fixture.issue,
					can_reset: false,
				}];
			});
		}).as("withRebuild");
		cy.window().then((win) => win.cur_frm.reload_doc());
		cy.wait("@withRebuild");
		assertNames();
		cy.get(".dinext-rebuild-summary").should("have.length", 1).and("be.visible");
	});

	it("updates only its own message, escapes names and wraps a long name", () => {
		assertNames();
		cy.window().then((win) => {
			win.cur_frm.dashboard.add_comment("Other form message", "yellow", true);
			const unsafe = '<img src=x onerror="window.pendingNameExecuted=true">' + "long".repeat(100);
			win.frappe.dinext.paintPendingApprovers(win.cur_frm, [
				{ approver: "unsafe@example.com", approver_name: unsafe },
				{ approver: "unsafe@example.com", approver_name: unsafe },
			]);
		});
		cy.viewport(360, 800);
		cy.get(banner).should("have.length", 1).and("contain", "<img");
		cy.get(`${banner} img`).should("not.exist");
		cy.get(banner).should(($element) => {
			expect($element[0].scrollWidth).to.be.at.most($element[0].clientWidth + 1);
		});
		cy.window().then((win) => win.cur_frm.script_manager.trigger("refresh"));
		assertNames();
		cy.contains(".form-message.yellow", "Other form message").should("be.visible");
		cy.window().then((win) => {
			expect(win.pendingNameExecuted).to.eq(undefined);
			return win.cur_frm.script_manager.trigger("refresh");
		});
		assertNames();
		cy.contains(".form-message.yellow", "Other form message").should("be.visible");
		cy.viewport(1440, 900);
	});

	it("ignores a delayed response after leaving the document", () => {
		let release;
		let started = false;
		let previousForm;
		const gate = new Promise((resolve) => { release = resolve; });
		cy.intercept({
			method: "POST", url: `**/api/method/${bannerApi}`, times: 1,
		}, (req) => {
			started = true;
			req.continue((res) => {
				res.body.message.pending_approvers = [
					{ approver: "stale@example.com", approver_name: "Stale approver" },
				];
				return gate;
			});
		}).as("staleBanner");
		cy.window().then((win) => {
			previousForm = win.cur_frm;
			void win.cur_frm.script_manager.trigger("refresh");
		});
		cy.wrap(null).should(() => expect(started).to.eq(true));
		cy.window().then((win) => { void win.frappe.set_route("List", "Issue", "List"); });
		cy.window().should((win) => expect(win.frappe.get_route_str()).to.match(/^List\/Issue/));
		cy.then(release);
		cy.wait("@staleBanner");
		cy.then(() => {
			expect(previousForm.layout.message.children(".dinext-pending-approvers").text())
				.not.to.contain("Stale approver");
		});
	});

	it("uses the shared Russian and English headline", () => {
		for (const language of ["ru", "en"]) {
			cy.call("frappe.client.set_value", {
				doctype: "User", name: fixture.viewer, fieldname: "language", value: language,
			});
			cy.reload();
			assertNames();
			cy.get(banner).should("contain",
				language === "ru" ? "Ожидается действие от:" : "Action expected from:");
		}
	});
});
