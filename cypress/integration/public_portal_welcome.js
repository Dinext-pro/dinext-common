describe("Public portal welcome", () => {
	it("opens the existing sign-in form from the primary action", () => {
		cy.visit("/");
		cy.get("#home-page h1").should("contain", "Добро пожаловать");
		cy.get(".welcome-primary")
			.should("be.visible")
			.and("have.attr", "href", "/login#login")
			.click();
		cy.location("pathname").should("eq", "/login");
		cy.location("hash").should("eq", "#login");
		cy.get('input[type="password"]').should("exist");
	});

	it("keeps documentation and the main site available before sign-in", () => {
		cy.visit("/");
		cy.get(".welcome-nav-docs")
			.should("be.visible")
			.and("have.attr", "href", "https://docs.dinext.ru");
		cy.get(".welcome-help-link")
			.should("be.visible")
			.and("have.attr", "href", "https://docs.dinext.ru");
		cy.get(".welcome-footer a").should("have.attr", "href", "https://dinext.ru");
	});

	it("fits a narrow screen with the sign-in action before decoration", () => {
		cy.viewport(320, 800);
		cy.visit("/");
		cy.get(".welcome-primary").should("be.visible");
		cy.get(".welcome-art").should("have.attr", "aria-hidden", "true");
		cy.get(".welcome-help-link").should("have.attr", "href", "https://docs.dinext.ru");
		cy.document().then((doc) => {
			expect(doc.documentElement.scrollWidth).to.eq(doc.documentElement.clientWidth);
			const action = doc.querySelector(".welcome-primary");
			const art = doc.querySelector(".welcome-art");
			expect(action.compareDocumentPosition(art) & doc.defaultView.Node.DOCUMENT_POSITION_FOLLOWING).to.be.greaterThan(0);
		});
	});
});
