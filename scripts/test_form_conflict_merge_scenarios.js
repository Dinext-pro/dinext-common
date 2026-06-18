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
		`${code}\nreturn { FormDiff, merge_child_row, analyze_child_table_merge, analyze };`
	);
	return fn(sandbox.window, {}, (value) => value);
}

const { FormDiff, merge_child_row, analyze_child_table_merge, analyze } = loadModule(["config.js", "diff.js"]);

const ROW1 = { name: "atuj9u090i", grade: 10, status: "В оценке / на доработке", idx: 1 };
const ROW2 = { name: "7h7ao3jv1t", grade: 4, status: "На согласовании", idx: 2 };
const BASE = [ROW1, ROW2];

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

function merge_table(initial, local, server, policy) {
	const result = analyze_child_table_merge(initial, local, server, policy || "server_wins");
	const merged = [];
	const initial_map = FormDiff.build_child_row_map(initial);
	const local_map = FormDiff.build_child_row_map(local);
	const server_map = FormDiff.build_child_row_map(server);
	const processed = new Set();

	(server || []).forEach((server_row, index) => {
		if (!server_row || server_row.__islocal) return;
		const key = FormDiff.child_row_key(server_row, index);
		processed.add(key);
		const local_row = local_map[key];
		const initial_row = initial_map[key] || {};
		if (local_row) merged.push(merge_child_row(initial_row, local_row, server_row, policy || "server_wins"));
		else merged.push(FormDiff.clone_raw_value(server_row));
	});

	Object.keys(server_map).forEach((key) => {
		if (key.startsWith("__islocal:") || processed.has(key)) return;
		merged.push(FormDiff.clone_raw_value(server_map[key]));
	});

	Object.keys(local_map).forEach((key) => {
		if (key.startsWith("__islocal:")) return;
		if (server_map[key]) return;
		const local_row = local_map[key];
		const initial_row = initial_map[key] || {};
		if ((policy || "server_wins") !== "server_wins" && local_row && !FormDiff.row_equal(initial_row, local_row)) {
			merged.push(FormDiff.clone_raw_value(local_row));
		}
	});

	(local || []).forEach((local_row) => {
		if (local_row && local_row.__islocal) merged.push(FormDiff.clone_raw_value(local_row));
	});

	return { result, merged };
}

// T4: local row1 grade 11, server row2 status closed -> preserve local row1, apply server row2
{
	const local = [{ ...ROW1, grade: 11 }, ROW2];
	const server = [ROW1, { ...ROW2, status: "Согласовано" }];
	const { result, merged } = merge_table(BASE, local, server);
	assert(result.has_server_apply && !result.has_conflicts, "T4 classified as server apply without table conflict");
	assert(merged[0].grade === 11, "T4 keeps local-only row1 grade");
	assert(merged[1].status === "Согласовано", "T4 applies server row2 status");
	assert(result.changed_rows.length === 1 && result.changed_rows[0].row_name === ROW2.name, "T4 tracks row2 only");
}

// T5: same row conflict grade local 11 vs server 99 -> server_wins 99
{
	const local = [{ ...ROW1, grade: 11 }, ROW2];
	const server = [{ ...ROW1, grade: 99 }, ROW2];
	const { result, merged } = merge_table(BASE, local, server);
	assert(result.has_conflicts, "T5 has row conflict");
	const merged_row1 = merged.find((row) => row.name === ROW1.name);
	assert(merged_row1.grade === 99, "T5 server_wins overwrites grade to 99");
}

// T6: local edit row2 grade 5, server deletes row2 -> row removed
{
	const local = [ROW1, { ...ROW2, grade: 5 }];
	const server = [ROW1];
	const { result, merged } = merge_table(BASE, local, server);
	assert(result.removed_rows.length === 1 && result.removed_rows[0].row_name === ROW2.name, "T6 detects removed row2");
	assert(merged.length === 1 && merged[0].name === ROW1.name, "T6 merge removes row2 despite local edit");
}

// T7: server adds row3
{
	const server = [...BASE, { name: "row3", grade: 7, status: "На согласовании", idx: 3 }];
	const { result, merged } = merge_table(BASE, BASE, server);
	assert(result.added_rows.length === 1, "T7 added row detected");
	assert(merged.length === 3, "T7 merge includes added row");
}

// T8: server removes row2 without local edits
{
	const server = [ROW1];
	const { result, merged } = merge_table(BASE, BASE, server);
	assert(result.removed_rows.length === 1, "T8 removed row detected");
	assert(merged.length === 1, "T8 merge keeps only row1");
}

// T9: local unsaved new row preserved when server unchanged
{
	const local_new = [...BASE, { __islocal: 1, grade: 1, status: "Draft", idx: 3, doctype: "Issue Estimations" }];
	const { result, merged } = merge_table(BASE, local_new, BASE);
	assert(!result.has_server_apply, "T9 no server apply when server unchanged");
	assert(merged.length === 3, "T9 preserves local __islocal row");
}

// T10: local edit row2 + server delete row2 with stale baseline missing row2 in initial
{
	const initial = [ROW1];
	const local = [ROW1, { ...ROW2, grade: 5 }];
	const server = [ROW1];
	const { result, merged } = merge_table(initial, local, server);
	assert(merged.length === 1, "T10 removes row2 even if initial baseline stale");
}

// Scalar conflict via analyze()
{
	const frm = { doc: { subject: "LOCAL" }, fields_dict: {} };
	const state = {
		fields: ["subject"],
		initial_values: { subject: "baseline" },
		initial_raw_values: {},
		local_seed_fields: {},
		cfg: { conflict_policy: "server_wins" },
	};
	const analysis = analyze(frm, { subject: "SERVER" }, state);
	assert(analysis.conflicts.includes("subject"), "scalar conflict detected");
}

console.log(`\nFormConflictMerge scenario tests: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
