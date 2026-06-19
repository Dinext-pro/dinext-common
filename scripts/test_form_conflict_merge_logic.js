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
		"__",
		`${code}\nreturn { FormDiff, bump_sync_generation, is_sync_stale };`
	);
	return fn(sandbox.window, {}, (value) => value);
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

// getdoc vs client.get: null keys on server must not count as a change
const getdoc_ident = [{ name: "id1", type: "Номер SD заказчика", code: "843173", idx: 1 }];
const client_ident = [
	{ name: "id1", type: "Номер SD заказчика", code: "843173", idx: 1, auto_repeat: null },
];
assert(FormDiff.equal(getdoc_ident, client_ident), "identification: null field equals missing key");

const getdoc_est = [
	{
		name: "est1",
		project_role: "Консультант",
		grade: 12,
		status: "Согласовано",
		category: "Трудоемкость, ч/ч (по умолчанию)",
		category1: "Трудоемкость, ч/ч",
	},
];
const client_est = [
	{
		name: "est1",
		project_role: "Консультант",
		grade: 12,
		status: "Согласовано",
		category: "Трудоемкость, ч/ч (по умолчанию)",
		category1: "Трудоемкость, ч/ч",
		task: null,
		executor: null,
		type: null,
	},
];
assert(FormDiff.equal(getdoc_est, client_est), "estimations: null fields equal missing keys");

assert(FormDiff.equal(0, 0), "zero is a real value");
assert(FormDiff.equal(false, false), "false is a real value");
assert(!FormDiff.equal({ name: "r1", grade: 0 }, { name: "r1" }), "zero must not collapse to absent");

// analyze: observer form unchanged, server has client.get null extras -> not server_only
const observer_frm = {
	doc: {
		identification: getdoc_ident,
		estimations: getdoc_est,
	},
	fields_dict: {
		identification: { df: { fieldtype: "Table", label: "Identification" } },
		estimations: { df: { fieldtype: "Table", label: "Estimations" } },
	},
};
const observer_server = {
	identification: client_ident,
	estimations: client_est,
};
const observer_state = {
	fields: ["identification", "estimations"],
	initial_values: FormDiff.snapshot(observer_frm.doc, ["identification", "estimations"]),
	initial_raw_values: {
		identification: getdoc_ident,
		estimations: getdoc_est,
	},
	local_seed_fields: {},
	cfg: { conflict_policy: "server_wins" },
};
const observer_analysis = FormDiff.analyze(observer_frm, observer_server, observer_state);
assert(!observer_analysis.server_only.includes("identification"), "identification not server_only for null shape");
assert(!observer_analysis.server_only.includes("estimations"), "estimations not server_only for null shape");
assert(observer_analysis.server_only.length === 0, "no false server_only from null shape");

// analyze: server_only when only server changed
const frm = { doc: { description: "initial", subject: "same" }, fields_dict: {} };
const server_doc = { description: "server text", subject: "same" };
const state = {
	fields: ["description", "subject"],
	initial_values: { description: "initial", subject: "same" },
	initial_raw_values: {},
	local_seed_fields: {},
	cfg: { conflict_policy: "server_wins" },
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

// child table: local row A + server row B -> server_only, not whole-table conflict
const initial_est = [
	{ name: "row-a", grade: 10, status: "Open", idx: 1 },
	{ name: "row-b", grade: 20, status: "Open", idx: 2 },
];
const local_est = [
	{ name: "row-a", grade: 11, status: "Open", idx: 1 },
	{ name: "row-b", grade: 20, status: "Open", idx: 2 },
];
const server_est = [
	{ name: "row-a", grade: 10, status: "Open", idx: 1 },
	{ name: "row-b", grade: 20, status: "Closed", idx: 2 },
];
const child_merge = FormDiff.analyze_child_table_merge(initial_est, local_est, server_est, "server_wins");
assert(child_merge.has_server_apply, "child table has server apply when another row changed");
assert(!child_merge.has_conflicts, "different rows changed -> no table-level conflict");
assert(child_merge.changed_rows.length === 1, "one changed row detected");
assert(child_merge.changed_rows[0].row_name === "row-b", "changed row is row-b");
assert(child_merge.changed_rows[0].server_fields.includes("status"), "row-b status is server field");
assert(!child_merge.changed_rows.some((row) => row.row_name === "row-a"), "unchanged row-a not in changed_rows");

const child_frm = {
	doc: { estimations: local_est },
	fields_dict: { estimations: { df: { fieldtype: "Table", label: "Estimations" } } },
};
const child_state = {
	fields: ["estimations"],
	initial_values: { estimations: FormDiff.normalize_value(initial_est) },
	initial_raw_values: { estimations: initial_est },
	local_seed_fields: {},
	cfg: { conflict_policy: "server_wins" },
};
const child_analysis = FormDiff.analyze(child_frm, { estimations: server_est }, child_state);
assert(child_analysis.server_only.includes("estimations"), "child table classified as server_only");
assert(!child_analysis.conflicts.includes("estimations"), "child table not whole-table conflict");
assert(child_analysis.child_table_changes.estimations.changed_rows.length === 1, "analyze exposes changed_rows");

const merged_a = FormDiff.merge_child_row(
	initial_est[0],
	local_est[0],
	server_est[0],
	"server_wins"
);
assert(merged_a.grade === 11, "merge preserves local-only row field when server row unchanged");

const merged_b = FormDiff.merge_child_row(
	initial_est[1],
	local_est[1],
	server_est[1],
	"server_wins"
);
assert(merged_b.status === "Closed", "merge applies server-only row field");
assert(merged_b.grade === 20, "merge keeps unchanged row field");

// child table conflict on same row field
const local_conflict = [
	{ name: "row-a", grade: 11, status: "Open", idx: 1 },
];
const server_conflict = [{ name: "row-a", grade: 99, status: "Open", idx: 1 }];
const row_conflict = FormDiff.analyze_child_table_merge(initial_est.slice(0, 1), local_conflict, server_conflict, "server_wins");
assert(row_conflict.has_conflicts, "same row field changed on both sides -> conflict");

const merged_conflict = FormDiff.merge_child_row(
	initial_est[0],
	local_conflict[0],
	server_conflict[0],
	"server_wins"
);
assert(merged_conflict.grade === 99, "server_wins overwrites conflicting row field");
assert(row_conflict.changed_rows.length === 1, "conflict row tracked");
assert(row_conflict.changed_rows[0].conflict_fields.includes("grade"), "conflict field listed");

const added_server_est = [
	...initial_est,
	{ name: "row-c", grade: 3, status: "Open", idx: 3 },
];
const added_merge = FormDiff.analyze_child_table_merge(initial_est, local_est, added_server_est, "server_wins");
assert(added_merge.added_rows.length === 1, "added row detected");
assert(added_merge.added_rows[0].row_name === "row-c", "added row name captured");

const removed_server_est = [initial_est[0]];
const removed_merge = FormDiff.analyze_child_table_merge(initial_est, local_est, removed_server_est, "server_wins");
assert(removed_merge.removed_rows.length === 1, "removed row detected");
assert(removed_merge.removed_rows[0].row_name === "row-b", "removed row-b captured");

// local already matches server while initial baseline is stale (realtime / early apply)
const synced_local_est = [
	{ name: "row-a", grade: 11, status: "Open", idx: 1 },
	{ name: "row-b", grade: 20, status: "Closed", idx: 2 },
];
const synced_server_est = [
	{ name: "row-a", grade: 11, status: "Open", idx: 1 },
	{ name: "row-b", grade: 20, status: "Closed", idx: 2 },
];
const synced_merge = FormDiff.analyze_child_table_merge(initial_est, synced_local_est, synced_server_est, "server_wins");
assert(synced_merge.has_server_apply, "stale baseline with synced local/server still has server apply");
assert(synced_merge.changed_rows.length === 2, "both changed rows tracked when local already equals server");
assert(
	synced_merge.changed_rows.every((row) => (row.server_fields || []).length > 0),
	"stale baseline rows expose server_fields for highlight"
);

// server row missing locally but present in initial baseline
const missing_local_est = [{ name: "row-a", grade: 10, status: "Open", idx: 1 }];
const restored_server_est = [
	{ name: "row-a", grade: 10, status: "Open", idx: 1 },
	{ name: "row-b", grade: 20, status: "Closed", idx: 2 },
];
const missing_local_merge = FormDiff.analyze_child_table_merge(
	initial_est,
	missing_local_est,
	restored_server_est,
	"server_wins"
);
assert(missing_local_merge.has_server_apply, "missing local row with server row triggers apply");
assert(missing_local_merge.changed_rows.length === 1, "missing local row tracked in changed_rows");
assert(missing_local_merge.changed_rows[0].row_name === "row-b", "restored row-b tracked");

// sync generation stale guard
const syncState = { doc_key: "Issue::ISS-001", sync_generation: 1 };
const frmOk = { doctype: "Issue", docname: "ISS-001", doc: {}, is_new: () => false };
assert(is_sync_stale(syncState, 1, frmOk) === false, "matching generation is fresh");
bump_sync_generation(syncState);
assert(is_sync_stale(syncState, 1, frmOk) === true, "old generation is stale after bump");
assert(is_sync_stale(syncState, 2, frmOk) === false, "current generation matches");

const frmOther = { doctype: "Issue", docname: "ISS-002", doc: {}, is_new: () => false };
assert(is_sync_stale(syncState, 2, frmOther) === true, "different docname is stale");

// form resync field detection
const resyncMod = loadModule(["config.js", "diff.js", "state.js", "form_resync.js"]);
const mockWorkflow = {
	get_state_fieldname(doctype) {
		return doctype === "Task" ? "workflow_state" : null;
	},
};
const resyncFn = new Function(
	"window",
	"frappe",
	`${fs.readFileSync(path.join(root, "config.js"), "utf8")}\n${fs.readFileSync(path.join(root, "diff.js"), "utf8")}\n${fs.readFileSync(path.join(root, "form_resync.js"), "utf8")}\nreturn { detect_form_control_changes, get_form_resync_fieldnames };`
);
const { detect_form_control_changes, get_form_resync_fieldnames } = resyncFn(
	{},
	{ workflow: mockWorkflow }
);
const resyncCfg = { form_resync_on_server_apply: true, form_resync_fields: [] };
const resyncFrm = { doctype: "Task", docname: "TASK-1", doc: { docstatus: 0, workflow_state: "Open" } };
assert(
	get_form_resync_fieldnames(resyncFrm, resyncCfg).includes("workflow_state"),
	"workflow state field auto-detected"
);
assert(get_form_resync_fieldnames(resyncFrm, resyncCfg).includes("docstatus"), "docstatus always included");
const wfChanges = detect_form_control_changes(
	resyncFrm,
	{ docstatus: 0, workflow_state: "Отложено" },
	{ cfg: resyncCfg }
);
assert(wfChanges.includes("workflow_state"), "workflow_state change detected for resync");
assert(!wfChanges.includes("docstatus"), "unchanged docstatus not flagged");

console.log(`\nFormConflictMerge logic tests: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
