describe("Workflow request retention", () => {
	const helper = "dinext_common.tests.workflow_request_receipt_ui";
	const doctype = "Workflow Request Receipt";
	let fixture;

	after(() => {
		if (!fixture) return;
		cy.login();
		cy.openDesk();
		cy.call(`${helper}.restore`, fixture);
	});

	it("applies the saved Log Settings period to finished requests", () => {
		cy.login();
		cy.openDesk("/app/log-settings/Log%20Settings");
		cy.call(`${helper}.seed`).then((response) => {
			fixture = response.body.message;
		});
		cy.window().its("cur_frm.doc.logs_to_clear").should((rows) => {
			expect(rows.filter((row) => row.ref_doctype === doctype)).to.have.length(1);
		});
		cy.window().then((win) => {
			const frm = win.cur_frm;
			const row = frm.doc.logs_to_clear.find((item) => item.ref_doctype === doctype);
			return Cypress.Promise.resolve(win.frappe.model.set_value(row.doctype, row.name, "days", 5))
				.then(() => frm.save());
		});
		cy.reload();
		cy.window().its("cur_frm.doc.logs_to_clear").should((rows) => {
			expect(rows.find((row) => row.ref_doctype === doctype).days).to.equal(5);
		});
		cy.then(() => cy.call(`${helper}.cleanup_receipts`, { samples: fixture.samples }))
			.its("body.message")
			.should("deep.equal", { old: false, recent: true, running: true });
	});
});
