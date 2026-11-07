module.exports = {
	includeShadowDom: true,
	defaultCommandTimeout: 120000,
	pageLoadTimeout: 120000,
	requestTimeout: 180000,
	responseTimeout: 180000,
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
		setupNodeEvents(on, config) {
			const { execFileSync } = require("node:child_process");
			const path = require("node:path");
			const site = process.env.FRAPPE_SITE || "localhost";
			const run = (method, args = []) => {
				const output = execFileSync("bench", ["--site", site, "execute", method, ...args], {
					cwd: path.resolve(__dirname, "../.."), encoding: "utf8", timeout: 120000,
				});
				return JSON.parse(output.trim().split("\n").at(-1));
			};
			const runFixture = (method, module = "approval_workspace_ui") => {
				const url = run("frappe.utils.get_site_url", ["--args", JSON.stringify([site])]);
				if (new URL(url).origin !== new URL(config.baseUrl).origin) {
					throw new Error("The Cypress base URL must match the local fixture site.");
				}
				return run(`dinext_common.tests.${module}.${method}`);
			};
			on("task", {
                emailProfileSeed: () => runFixture("seed", "workflow_email_ui"),
                emailProfileCleanup: () => runFixture("cleanup", "workflow_email_ui"),
				approvalWorkspaceSeed: () => runFixture("seed"),
				approvalWorkspaceCleanup: () => runFixture("cleanup"),
			});
			return config;
		},
		baseUrl: "http://localhost:8000",
		specPattern: "cypress/integration/**/*.js",
		supportFile: "cypress/support/e2e.js",
		testIsolation: true,
	},
};
