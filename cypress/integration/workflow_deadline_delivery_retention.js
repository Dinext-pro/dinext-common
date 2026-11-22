describe("Workflow deadline delivery retention", () => {
	it("shows the default seven-day retention in Log Settings", () => {
		cy.login();
		cy.openDesk("/app/log-settings/Log%20Settings");
		cy.window().its("cur_frm.doc.logs_to_clear").should((rows) => {
			const entries = rows.filter((row) => row.ref_doctype === "Workflow Deadline Delivery");
			expect(entries).to.have.length(1);
			expect(entries[0].days).to.equal(7);
		});
	});
});
