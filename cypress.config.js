const { defineConfig } = require(
	process.env.DINEXT_CYPRESS_MODULE || "../frappe/node_modules/cypress"
);

module.exports = defineConfig({
	includeShadowDom: true,
	defaultCommandTimeout: 10000,
	pageLoadTimeout: 30000,
	viewportWidth: 1440,
	viewportHeight: 900,
	video: false,
	e2e: {
		baseUrl: "http://localhost:8000",
		specPattern: "cypress/integration/**/*.js",
		supportFile: "cypress/support/e2e.js",
		testIsolation: true,
	},
});
