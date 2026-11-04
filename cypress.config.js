const sidebarTests = require("./cypress.sidebar.config.cjs");

module.exports = {
	includeShadowDom: true,
	defaultCommandTimeout: 10000,
	pageLoadTimeout: 30000,
	viewportWidth: 1440,
	viewportHeight: 900,
	video: false,
	e2e: {
		setupNodeEvents: sidebarTests.e2e.setupNodeEvents,
		baseUrl: "http://localhost:8000",
		specPattern: "cypress/integration/**/*.js",
		supportFile: "cypress/support/e2e.js",
		testIsolation: true,
	},
};
