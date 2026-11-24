describe("Initial Dinext workspace configuration", () => {
	let fixture;
	before(() => cy.task("workspaceDefaultsSeed").then((value) => { fixture = value; }));
	after(() => cy.task("workspaceDefaultsCleanup"));
	beforeEach(() => {
		cy.session("workspace-defaults-user", () => {
			cy.request({
				method: "POST", url: "/api/method/login", log: false,
				body: { usr: fixture.user, pwd: fixture.password },
			});
		}, {
			cacheAcrossSpecs: false,
			validate: () => cy.request("/api/method/frappe.auth.get_logged_user")
				.its("body.message").should("eq", fixture.user),
		});
	});

	function theme(name) {
		cy.window().then((win) => {
			win.document.documentElement.setAttribute("data-theme-mode", name);
			win.frappe.ui.set_theme(name);
		});
		cy.get("html").should("have.attr", "data-theme", name);
	}

	it("shows the approved saved configuration in the real settings form in both themes", () => {
		cy.visit("/app/dinext-workspace-settings/Dinext");
		cy.window().its("cur_frm.doc.name").should("eq", "Dinext");
		for (const name of ["light", "dark"]) {
			theme(name);
			cy.get('[data-fieldname="show_frequent_pages"] input').should("be.checked");
			cy.get('[data-fieldname="show_recent_pages"] input').should("be.checked");
			cy.get('[data-fieldname="items"] .grid-body .grid-row').should("have.length", 10);
			cy.get('[data-fieldname="doctype_items"] .grid-body .grid-row').should("have.length", 4);
			cy.window().then((win) => {
				expect(win.cur_frm.doc.sections.map((row) => [row.list_limit, row.card_columns]))
					.to.deep.equal([[5, 3], [8, 4]]);
			});
		}
		cy.screenshot("workspace-defaults-settings-dark");
	});

	it("renders ten accessible cards with the approved section dimensions across a live theme change", () => {
		cy.visit("/app/dinext");
		cy.get(".dinext-workspace-hub__card").should("have.length", 10);
		for (const name of ["light", "dark"]) {
			theme(name);
			cy.get(".dinext-workspace-hub__card").should("be.visible").and("have.length", 10);
			for (const [section, columns] of [["My Work", "3"], ["Project Management", "4"]]) {
				cy.get(`[data-dinext-section="${section}"] .dinext-workspace-hub__cards`).should(($cards) => {
					expect($cards[0].style.getPropertyValue("--dinext-hub-card-columns")).to.eq(columns);
				});
			}
			cy.get('[data-dinext-section="My Work"] .dinext-workspace-hub__card-title')
				.should(($titles) => {
					expect([...$titles].map((node) => node.textContent)).to.deep.equal([
						"My Tasks", "My Timesheets", "Development", "My Board", "Goals",
					]);
				});
			cy.get('[data-dinext-section="Project Management"] .dinext-workspace-hub__card-title')
				.should(($titles) => {
					expect([...$titles].map((node) => node.textContent)).to.deep.equal([
						"My Projects", "Project Portfolio", "Project Scoring", "Task Burndown",
					]);
				});
		}
		cy.get(".dinext-workspace-hub__card").each(($card) => {
			const href = $card.attr("href");
			expect(href).to.be.a("string").and.not.eq("");
			if (!href.startsWith("https://")) cy.request(href).its("status").should("eq", 200);
		});
		cy.screenshot("workspace-defaults-hub-dark");
		cy.contains(".dinext-workspace-hub__card", "Goals").click();
		cy.location("pathname").should("match", /\/app\/goals$/);
	});
});
