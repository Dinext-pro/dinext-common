const path = require("node:path");
const { execFileSync } = require("node:child_process");

module.exports = {
	includeShadowDom: true,
	video: false,
	viewportWidth: 1440,
	viewportHeight: 1000,
	defaultCommandTimeout: 60000,
	pageLoadTimeout: 120000,
	reporter: "junit",
	reporterOptions: { mochaFile: "cypress/results/workspace-defaults-[hash].xml" },
	e2e: {
		baseUrl: "http://localhost:8011",
		specPattern: "cypress/integration/workspace_install_defaults.js",
		supportFile: false,
		setupNodeEvents(on) {
			const run = (method) => {
				const site = process.env.FRAPPE_SITE;
				if (!site) throw new Error("FRAPPE_SITE must identify the isolated acceptance site");
				const output = execFileSync("bench", [
					"--site", site, "execute", `dinext_common.tests.workspace_defaults_ui.${method}`,
				], { cwd: path.resolve(__dirname, "../.."), encoding: "utf8", timeout: 120000 });
				return method === "seed" ? JSON.parse(output.trim().split("\n").at(-1)) : null;
			};
			on("task", {
				workspaceDefaultsSeed: () => run("seed"),
				workspaceDefaultsCleanup: () => run("cleanup"),
			});
		},
	},
};
