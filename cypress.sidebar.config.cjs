const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

// Render the real platform sidebar without a database or a signed-in session.
const frappePath = path.resolve(__dirname, process.env.DINEXT_FRAPPE_PATH || "../frappe");
const platformRequire = createRequire(path.join(frappePath, "package.json"));

function assets() {
	const sass = platformRequire("sass");
	const esbuild = platformRequire("esbuild");
	const bundle = (relativePath) =>
		esbuild.buildSync({
			entryPoints: [path.join(frappePath, relativePath)],
			bundle: true,
			write: false,
			format: "iife",
			logLevel: "error",
		}).outputFiles[0].text;
	return {
		deskCss: sass.renderSync({
			file: path.join(frappePath, "frappe/public/scss/desk.bundle.scss"),
			includePaths: [frappePath, path.join(frappePath, "node_modules")],
			importer: (name) =>
				name.startsWith("~")
					? { file: path.join(frappePath, "node_modules", name.slice(1)) }
					: null,
			quietDeps: true,
			logger: { warn() {}, debug() {} },
		}).css.toString(),
		sidebarCss: fs.readFileSync(
			path.join(__dirname, "dinext_common/public/css/workspace_sidebar_hover.css"),
			"utf8"
		),
		jquery: fs.readFileSync(platformRequire.resolve("jquery/dist/jquery.js"), "utf8"),
		utils: bundle("frappe/public/js/frappe/utils/utils.js"),
		workspace: bundle("frappe/public/js/frappe/views/workspace/workspace.js"),
	};
}

module.exports = {
	includeShadowDom: true,
	video: false,
	viewportWidth: 1440,
	viewportHeight: 900,
	reporter: "junit",
	reporterOptions: { mochaFile: "cypress/results/workspace-sidebar-[hash].xml" },
	e2e: {
		baseUrl: "http://localhost:8000",
		specPattern: "cypress/integration/workspace_sidebar_controls.js",
		supportFile: false,
		setupNodeEvents(on) {
			let platformAssets;
			on("task", { sidebarAssets: () => (platformAssets ||= assets()) });
		},
	},
};
