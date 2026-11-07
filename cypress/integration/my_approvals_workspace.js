describe("My Approvals workspace", () => {
	let fixture;

	before(() => {
		cy.task("approvalWorkspaceSeed").then((data) => { fixture = data; });
	});

	after(() => {
		cy.task("approvalWorkspaceCleanup");
	});

	function card(label, count) {
		return cy.contains(".number-widget-box", label).should(($card) => {
			expect($card.find(".number").text().trim()).to.eq(String(count));
		});
	}

	function reportSources(names) {
		cy.window().should((win) => {
			expect(win.frappe.query_report.data.map((row) => row.reference_name)).to.have.members(
				names.map((name) => fixture.prefix + name)
			);
		});
	}

	it("opens the legacy route for an English approver with the app module blocked", () => {
		cy.login(fixture.approver, fixture.password);
		cy.openDesk(`/app/${encodeURIComponent("мои-согласования")}`);
		cy.location("pathname").should("eq", "/app/my-approvals");
		cy.contains(".ce-header", "My Approvals").should("be.visible");
		cy.get(".number-widget-box").should("have.length", 4);
		cy.get(".dashboard-widget-box").should("have.length", 1);
		cy.contains(".ce-header", "Approval Control").should("not.exist");
		cy.contains(".shortcut-widget-box", "Approval Monitoring").should("be.visible");
		card("New Approvals Today", 1).find(".widget-body").click();
		reportSources(["Today"]);
		cy.openDesk("/app/my-approvals");
		card("Awaiting My Decision", 2).find(".widget-body").click();
		reportSources(["Earlier", "Today"]);
		cy.noPermissionDialog();
	});

	it("keeps the decision date and source filters when drilling into history", () => {
		cy.login(fixture.approver, fixture.password);
		cy.openDesk("/app/my-approvals");
		card("Automatic Decisions in the Last 30 Days", 1).find(".widget-body").click();
		reportSources(["Automatic"]);
		cy.openDesk("/app/my-approvals");
		card("My Decisions in the Last 30 Days", 3).find(".widget-body").click();
		reportSources(["Manual", "Automatic", "Archived"]);
		cy.contains(".dt-cell", fixture.prefix + "Archived")
			.find("a")
			.should("not.exist");
	});

	it("renders translated control widgets for a monitor in both themes", () => {
		cy.login(fixture.monitor, fixture.password);
		cy.openDesk("/app/my-approvals");
		cy.contains(".ce-header", "Мои согласования").should("be.visible");
		cy.contains(".ce-header", "Контроль").should("be.visible");
		for (const theme of ["dark", "light"]) {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			cy.get(".number-widget-box").should(($cards) => {
				expect($cards).to.have.length(8);
				$cards.each((_, card) => {
					expect(Cypress.$(card).find(".number").text().trim(), "rendered card value").to.be.ok;
				});
			});
			cy.get(".dashboard-widget-box").should(($charts) => {
				expect($charts).to.have.length(5);
				$charts.each((_, chart) => {
					const $body = Cypress.$(chart).find(".widget-body");
					const rendered = $body.find("svg").length > 0;
					const empty = $body.find(".chart-loading-state:visible").text().trim();
					expect(rendered || /^(No Data|Нет данных)$/i.test(empty), "rendered chart").to.be.true;
				});
			});
			card("Открытые раунды", 2).should("be.visible");
		}
		card("Открытые раунды", 2).find(".widget-body").click();
		cy.window().should((win) => {
			expect(win.frappe.get_route()).to.deep.eq(["query-report", "Approval Monitoring"]);
			expect(win.frappe.query_report.get_filter_value("round_status")).to.eq("Open");
		});
		cy.noPermissionDialog();
	});
});
