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
		cy.get("#brand-cube").should("exist");
		cy.get(".welcome-help-link").should("have.attr", "href", "https://docs.dinext.ru");
		cy.document().then((doc) => {
			expect(doc.documentElement.scrollWidth).to.eq(doc.documentElement.clientWidth);
			const action = doc.querySelector(".welcome-primary");
			const art = doc.querySelector(".welcome-art");
			expect(
				action.compareDocumentPosition(art) &
					doc.defaultView.Node.DOCUMENT_POSITION_FOLLOWING
			).to.be.greaterThan(0);
		});
	});

	it("shows the complete composition at common viewport sizes", () => {
		for (const [width, height] of [
			[1440, 900],
			[2048, 1000],
			[390, 844],
		]) {
			cy.viewport(width, height);
			cy.visit("/");
			cy.get("#brand-cube").should(($canvas) => {
				const canvas = $canvas[0];
				expect(canvas.width).to.be.greaterThan(0);
				const pixels = canvas
					.getContext("2d")
					.getImageData(0, 0, canvas.width, canvas.height).data;
				expect(pixels.some((value, index) => index % 4 === 3 && value > 0)).to.eq(true);
			});
			cy.document().then((doc) => {
				expect(doc.documentElement.scrollWidth).to.eq(doc.documentElement.clientWidth);
				expect(doc.documentElement.scrollHeight).to.be.at.most(height + 1);
			});
		}
	});

	it("keeps the standard login and recovery under an accessible header", () => {
		cy.visit("/login#login");
		cy.get("body > nav.navbar .navbar-brand img").should("have.attr", "alt", "Dinext");
		cy.get('body > nav.navbar a[href="https://docs.dinext.ru"]').should("be.visible");
		cy.get('body > nav.navbar a[href="/homepage"]').should("be.visible");
		cy.get("#login_email").should("exist");
		cy.get("#login_password").should("exist");
		cy.get('a[href="#forgot"]').first().click();
		cy.location("hash").should("eq", "#forgot");
		cy.get(".for-forgot").should("be.visible");
		cy.visit("/login#login");
		cy.get('a[href="#login-with-email-link"]').should("exist");
		cy.viewport(390, 844);
		cy.visit("/login#login");
		cy.get('body > nav.navbar a[href="/homepage"]').should("be.visible");
		cy.get("body > nav.navbar .navbar-toggler").should("not.be.visible");
		cy.get('body > nav.navbar a[href="/homepage"]').click();
		cy.location("pathname").should("eq", "/homepage");
	});
});
