module.exports = {
	adminPassword: "admin",
	defaultCommandTimeout: 120000,
	pageLoadTimeout: 120000,
	requestTimeout: 180000,
	video: false,
	viewportHeight: 960,
	viewportWidth: 1400,
	retries: {
		runMode: 0,
		openMode: 0,
	},
	e2e: {
		setupNodeEvents() {},
		baseUrl: "http://127.0.0.1:8000",
		specPattern: "cypress/integration/**/*.js",
		supportFile: "cypress/support/e2e.js",
		includeShadowDom: true,
		testIsolation: false,
	},
};
