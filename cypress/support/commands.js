Cypress.Commands.add("login", (email, password) => {
	const sid = Cypress.env("sid");
	if (sid && (!email || email === "Administrator")) {
		return cy.session(
			["ut-sid", sid],
			() => {
				cy.setCookie("sid", sid, { httpOnly: true });
			},
			{
				cacheAcrossSpecs: false,
				validate() {
					cy.request("/api/method/frappe.auth.get_logged_user")
						.its("body.message")
						.should("eq", "Administrator");
				},
			}
		);
	}
	if (!email) {
		email = "Administrator";
	}
	if (!password) {
		password = Cypress.env("adminPassword");
	}
	return cy.session(
		[email, password],
		() => {
			cy.request({
				url: "/api/method/login",
				method: "POST",
				body: { usr: email, pwd: password },
			});
		},
		{
			cacheAcrossSpecs: false,
			validate() {
				cy.request("/api/method/frappe.auth.get_logged_user")
					.its("body.message")
					.should("eq", email);
			},
		}
	);
});

Cypress.Commands.add("call", (method, args, { failOnStatusCode = true, timeout } = {}) => {
	return cy
		.window()
		.its("frappe.csrf_token")
		.then((csrf_token) => {
			const request = {
				url: `/api/method/${method}`,
				method: "POST",
				body: args || {},
				failOnStatusCode,
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					"X-Frappe-CSRF-Token": csrf_token,
				},
			};
			if (timeout) request.timeout = timeout;
			return cy.request(request).then((res) => {
				if (failOnStatusCode) {
					expect(res.status).to.eq(200);
				}
				return res;
			});
		});
});

Cypress.Commands.add("openDesk", (path) => {
	cy.request({ url: path || "/app", timeout: 180000 });
	cy.visit(path || "/app");
	cy.window().its("frappe.csrf_token").should("be.a", "string").and("not.eq", "None");
	cy.window().its("frappe.session.user").should("not.eq", "Guest");
});

Cypress.Commands.add("noPermissionDialog", () => {
	cy.get("body").should(($body) => {
		const text = $body[0].innerText;
		expect(text.includes("Нет разрешения"), "Russian permission error").to.eq(false);
		expect(text.includes("Not permitted"), "permission error").to.eq(false);
		expect(/no permission/i.test(text), "permission error").to.eq(false);
	});
});
