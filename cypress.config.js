const { defineConfig } = require(
	process.env.DINEXT_CYPRESS_MODULE || "../frappe/node_modules/cypress"
);

module.exports = defineConfig({
	includeShadowDom: true,
	defaultCommandTimeout: 120000,
	pageLoadTimeout: 120000,
	requestTimeout: 180000,
	viewportWidth: 1440,
	viewportHeight: 900,
	video: false,
	retries: {
		runMode: 0,
		openMode: 0,
	},
	env: {
		adminPassword: "admin",
	},
	e2e: {
		baseUrl: "http://localhost:8000",
		specPattern: "cypress/integration/**/*.js",
		supportFile: "cypress/support/e2e.js",
		testIsolation: true,
	},
});
