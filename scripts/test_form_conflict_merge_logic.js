/* eslint-disable no-eval */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "dinext_common", "public", "js", "form_conflict_merge");

function loadModule(sources) {
	const code = sources.map((file) => fs.readFileSync(path.join(root, file), "utf8")).join("\n");
	const sandbox = { window: {} };
	sandbox.window = sandbox;
	const fn = new Function(
		"window",
		"frappe",
		`${code}\nreturn { FormDiff, bump_sync_generation, is_sync_stale };`
	);
	return fn(sandbox.window, {});
}

const { FormDiff, bump_sync_generation, is_sync_stale } = loadModule(["config.js", "diff.js", "state.js"]);

let passed = 0;
let failed = 0;

function assert(condition, message) {
	if (!condition) {
		failed += 1;
		console.error("FAIL:", message);
		return;
	}
	passed += 1;
}

// normalize child table: ignore __islocal, stable sort
const rowsA = [
	{ name: "b", grade: 2, __islocal: 1, idx: 2 },
	{ name: "a", grade: 1, idx: 1 },
];
const rowsB = [{ name: "a", grade: 1, idx: 1 }];
assert(FormDiff.equal(rowsA, rowsB) === true, "__islocal rows are ignored in child table compare");

const rowsC = [{ name: "a", grade: 1, idx: 1 }];
assert(FormDiff.equal(rowsA, rowsC), "normalized snapshot ignores __islocal rows");

// analyze: server_only when only server changed
const frm = { doc: { description: "initial", subject: "same" } };
const server_doc = { description: "server text", subject: "same" };
const state = {
	fields: ["description", "subject"],
	initial_values: { description: "initial", subject: "same" },
	local_seed_fields: {},
};
const analysis = FormDiff.analyze(frm, server_doc, state);
assert(analysis.server_only.includes("description"), "description is server_only");
assert(!analysis.conflicts.includes("description"), "description is not conflict");
assert(!analysis.server_only.includes("subject"), "unchanged subject not server_only");

// analyze: conflict when both changed differently
state.initial_values = { description: "initial", subject: "initial" };
frm.doc.description = "local";
frm.doc.subject = "local";
server_doc.description = "server";
server_doc.subject = "server";
const conflictAnalysis = FormDiff.analyze(frm, server_doc, state);
assert(conflictAnalysis.conflicts.includes("description"), "both changed -> conflict");
assert(conflictAnalysis.conflicts.includes("subject"), "both changed subject -> conflict");

// sync generation stale guard
const syncState = { doc_key: "Issue::ISS-001", sync_generation: 1 };
const frmOk = { doctype: "Issue", docname: "ISS-001", doc: {}, is_new: () => false };
assert(is_sync_stale(syncState, 1, frmOk) === false, "matching generation is fresh");
bump_sync_generation(syncState);
assert(is_sync_stale(syncState, 1, frmOk) === true, "old generation is stale after bump");
assert(is_sync_stale(syncState, 2, frmOk) === false, "current generation matches");

const frmOther = { doctype: "Issue", docname: "ISS-002", doc: {}, is_new: () => false };
assert(is_sync_stale(syncState, 2, frmOther) === true, "different docname is stale");

console.log(`\nFormConflictMerge logic tests: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
