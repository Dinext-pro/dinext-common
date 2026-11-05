describe("My Approvals workspace", () => {
	it("renders eight values and five charts and opens the personal queue", () => {
		cy.login();
		cy.openDesk(`/app/${encodeURIComponent("мои-согласования")}`);

		cy.get(".number-widget-box").should(($cards) => {
			expect($cards).to.have.length(8);
			$cards.each((_, card) => {
				const value = card.querySelector(".number");
				expect(value?.textContent.trim(), "rendered card value").to.be.ok;
			});
		});
		cy.get(".dashboard-widget-box").should(($charts) => {
			expect($charts).to.have.length(5);
			$charts.each((_, chart) => {
				const $body = Cypress.$(chart).find(".widget-body");
				const chartRendered = $body.find("svg").length > 0;
				const empty = $body.find(".chart-loading-state:visible").text().trim();
				expect(chartRendered || /^(No Data|Нет данных)$/i.test(empty), "rendered chart").to.be.true;
			});
		});

		if (Cypress.env("workspaceTiming")) {
			cy.window().then((win) => cy.task("workspaceTiming", Math.round(win.performance.now())));
		}
		cy.contains(".number-widget-box", /My open approvals|Мои активные согласования/)
			.find(".number")
			.click();
		cy.location("pathname").should((path) => {
			expect(decodeURIComponent(path)).to.eq("/app/query-report/My Approvals");
		});
		cy.noPermissionDialog();
	});
});
