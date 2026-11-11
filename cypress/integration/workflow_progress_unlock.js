context("Workflow progress releases Desk interaction", () => {
	let fixture;
	before(() => {
		if (Cypress.env("workflowScenariosPrivate"))
			cy.task("scenarioProgressSeed").then(value => { fixture = value; });
	});
	after(() => {
		if (fixture) cy.task("scenarioProgressCleanup");
	});
	beforeEach(() => {
		cy.login(fixture?.user, fixture?.password);
		cy.openDesk("/app");
		cy.get("#freeze").should("not.exist");
		cy.window().should((win) => expect(win.frappe.dom.freeze_count).to.eq(0));
	});

	it("releases the real dialog, freeze layer and keyboard after a completed batch", () => {
		cy.window().then(async (win) => {
			const page = { wrapper: win.$(".page-container:visible") };
			const baseline = win.frappe.dom.freeze_count;
			for (let attempt = 0; attempt < 2; attempt += 1) {
				let called = false;
				await win.frappe.dinext.runWorkflowOperation(page, async (updateProgress) => {
					called = true;
					updateProgress(1, 2);
					await new Promise((resolve) => win.setTimeout(resolve, attempt ? 400 : 0));
					updateProgress(2, 2);
				}, { count: 2, title: "Workflow completion test", requestId: `unlock-${attempt}` });
				expect(called, "a subsequent workflow operation can run").to.eq(true);
				expect(page.wrapper[0].inert, "page accepts interaction").to.eq(false);
				expect(win.frappe.dom.freeze_count, "freeze count restored").to.eq(baseline);
				expect(win.frappe.cur_progress == null, "progress cleared").to.eq(true);
				expect(win.$(".modal-backdrop").length, "modal and freeze layers removed").to.eq(0);
				expect(win.document.body.classList.contains("modal-open")).to.eq(false);
				const save = new win.KeyboardEvent("keydown", {
					key: "F24", bubbles: true, cancelable: true,
				});
				page.wrapper[0].dispatchEvent(save);
				expect(save.defaultPrevented, "workflow keyboard lock removed").to.eq(false);
			}
		});
	});

	it("releases the progress dialog when a batch request fails", () => {
		cy.window().then(async (win) => {
			const page = { wrapper: win.$(".page-container:visible") };
			let error;
			try {
				await win.frappe.dinext.runWorkflowOperation(page, async () => {
					throw new Error("Workflow request failed");
				}, { count: 2, title: "Workflow failure test", requestId: "unlock-failure" });
			} catch (caught) {
				error = caught;
			}
			expect(error.message).to.eq("Workflow request failed");
			expect(page.wrapper[0].inert).to.eq(false);
			expect(win.frappe.dom.freeze_count).to.eq(0);
			expect(win.$(".modal-backdrop").length).to.eq(0);
			expect(win.document.body.classList.contains("modal-open")).to.eq(false);
		});
	});
});
