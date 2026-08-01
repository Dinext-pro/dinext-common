import { equal, normalize_value, snapshot } from "./diff.js";
import { get_state } from "./state.js";
import { is_startup_warmup_active } from "./startup.js";
import { is_child_table_field } from "./applier.js";

export const FCM_LOG_PREFIX = "[FCM]";

export const FCM_LOG_LEVELS = {
	info: "info",
	warn: "warn",
};

export function is_fcm_debug_enabled(state) {
	if (window.__dinext_fcm_debug) return true;
	try {
		if (window.localStorage && window.localStorage.getItem("dinext_fcm_debug") === "1") return true;
	} catch (e) {
		// ignore private mode / blocked storage
	}
	return Boolean(state && state.cfg && state.cfg.debug_log);
}

export function fcm_doc_label(frm) {
	if (!frm || !frm.doctype) return "?";
	return `${frm.doctype}/${frm.docname || "new"}`;
}

export function count_child_table_rows(value) {
	const rows = Array.isArray(value) ? value : [];
	return {
		total: rows.length,
		persisted: rows.filter((row) => row && !row.__islocal && !row.__deleted).length,
		islocal: rows.filter((row) => row && row.__islocal).length,
		deleted: rows.filter((row) => row && row.__deleted).length,
	};
}

export function child_table_row_keys(value, limit) {
	if (!Array.isArray(value)) return [];
	return value.slice(0, limit || 40).map((row, index) => ({
		key: (row && (row.name || row.idx)) || `row-${index}`,
		name: row && row.name,
		idx: row && row.idx,
		__islocal: Boolean(row && row.__islocal),
		__deleted: Boolean(row && row.__deleted),
	}));
}

export function diff_child_table_rows(left, right) {
	const left_rows = Array.isArray(left) ? left : [];
	const right_rows = Array.isArray(right) ? right : [];

	const key_of = (row, index) => String((row && (row.name || row.idx)) || `row-${index}`);
	const left_map = {};
	const right_map = {};

	left_rows.forEach((row, index) => {
		left_map[key_of(row, index)] = row;
	});
	right_rows.forEach((row, index) => {
		right_map[key_of(row, index)] = row;
	});

	const removed = Object.keys(left_map).filter((key) => !right_map[key]);
	const added = Object.keys(right_map).filter((key) => !left_map[key]);
	const changed = Object.keys(left_map).filter((key) => {
		if (!right_map[key]) return false;
		return !equal(left_map[key], right_map[key]);
	});

	return { removed, added, changed };
}

export function diff_child_table_snapshots(initial, local, server) {
	const out = {
		raw: {
			initial: count_child_table_rows(initial),
			local: count_child_table_rows(local),
			server: count_child_table_rows(server),
		},
		normalized_equal: {
			initial_local: equal(initial, local),
			initial_server: equal(initial, server),
			local_server: equal(local, server),
		},
		normalized_diff: {
			initial_vs_local: diff_child_table_rows(normalize_value(initial), normalize_value(local)),
			initial_vs_server: diff_child_table_rows(normalize_value(initial), normalize_value(server)),
			local_vs_server: diff_child_table_rows(normalize_value(local), normalize_value(server)),
		},
		keys: {
			initial: child_table_row_keys(initial),
			local: child_table_row_keys(local),
			server: child_table_row_keys(server),
		},
	};
	return out;
}

export function explain_field_classification(fieldname, initial, local, server) {
	const local_changed = !equal(local, initial);
	const server_changed = !equal(server, initial);
	const local_server_equal = equal(local, server);

	if (!local_changed && !server_changed) return "unchanged";
	if (!local_changed && server_changed) return "server_only";
	if (local_changed && !server_changed) return "local_only";
	if (local_changed && server_changed && !local_server_equal) return "conflict";
	if (local_changed && server_changed && local_server_equal) return "both_changed_same_value";
	return "unknown";
}

export function summarize_field_value(value) {
	if (value === undefined) return { kind: "undefined" };
	if (value === null) return { kind: "null" };
	if (Array.isArray(value)) {
		const counts = count_child_table_rows(value);
		return {
			kind: "child_table",
			rows: value.length,
			...counts,
			names: value.slice(0, 12).map((row) => (row && row.name) || null),
			keys: child_table_row_keys(value, 12),
			hash: JSON.stringify(normalize_value(value)).length,
			preview: JSON.stringify(normalize_value(value)).slice(0, 240),
		};
	}
	if (typeof value === "string") {
		return { kind: "string", length: value.length, preview: value.slice(0, 160) };
	}
	return { kind: typeof value, preview: JSON.stringify(value).slice(0, 160) };
}

export function fcm_emit(level, event, entry) {
	const payload = Object.assign({ ts: new Date().toISOString(), event }, entry || {});
	if (level === FCM_LOG_LEVELS.warn) {
		console.warn(FCM_LOG_PREFIX, event, payload);
		return;
	}
	console.info(FCM_LOG_PREFIX, event, payload);
}

export function fcm_debug(state, event, payload, level) {
	if (!is_fcm_debug_enabled(state)) return;
	fcm_emit(level || FCM_LOG_LEVELS.info, event, payload);
}

export function fcm_debug_state_snapshot(state, frm, label) {
	if (!is_fcm_debug_enabled(state)) return;

	const tracked = (state.fields || []).slice(0, 40);
	const initial = state.initial_values || {};
	const local = snapshot(frm.doc, tracked);
	const field_stats = {};

	tracked.forEach((fieldname) => {
		field_stats[fieldname] = {
			initial: summarize_field_value(initial[fieldname]),
			local: summarize_field_value(local[fieldname]),
		};
	});

	fcm_debug(state, label || "state_snapshot", {
		doc: fcm_doc_label(frm),
		modified: {
			frm: frm.doc && frm.doc.modified,
			initial: state.initial_modified,
			server: state.server_modified,
		},
		flags: {
			installed: state.installed,
			startup_baseline_ready: state.startup_baseline_ready,
			startup_warmup_active: is_startup_warmup_active(state),
			startup_user_touched: state.startup_user_touched,
			pollers_ready: state.pollers_ready,
			highlighted_fields: Object.assign({}, state.highlighted_fields || {}),
		},
		tracked_fields: tracked.length,
		fields: field_stats,
	});
}

export function fcm_debug_analysis(state, frm, analysis, extra) {
	if (!is_fcm_debug_enabled(state) || !analysis) return;

	const initial = state.initial_values || {};
	const local = snapshot(frm.doc, state.fields);
	const server = extra && extra.server_snapshot;
	const fields = [
		...new Set([
			...(analysis.server_only || []),
			...(analysis.local_only || []),
			...(analysis.conflicts || []),
			...(analysis.applied_server || []),
			...(analysis.applied_conflicts || []),
		]),
	];

	const details = {};
	fields.forEach((fieldname) => {
		const classification = server
			? explain_field_classification(fieldname, initial[fieldname], local[fieldname], server[fieldname])
			: null;
		const entry = {
			classification,
			local_changed: !equal(local[fieldname], initial[fieldname]),
			server_changed: server ? !equal(server[fieldname], initial[fieldname]) : null,
			equal_local_server: server ? equal(local[fieldname], server[fieldname]) : null,
			local: summarize_field_value(local[fieldname]),
			initial: summarize_field_value(initial[fieldname]),
			server: server ? summarize_field_value(server[fieldname]) : null,
		};
		if (
			Array.isArray(local[fieldname]) ||
			Array.isArray(initial[fieldname]) ||
			(server && Array.isArray(server[fieldname]))
		) {
			entry.child_table_diff = diff_child_table_snapshots(
				initial[fieldname],
				local[fieldname],
				server ? server[fieldname] : null
			);
		}
		details[fieldname] = entry;
	});

	const has_conflicts = (analysis.conflicts || []).length || (analysis.applied_conflicts || []).length;
	const child_table_changes = {};
	Object.keys(analysis.child_table_changes || {}).forEach((fieldname) => {
		const entry = analysis.child_table_changes[fieldname] || {};
		child_table_changes[fieldname] = {
			changed_rows: (entry.changed_rows || []).length,
			added_rows: (entry.added_rows || []).length,
			removed_rows: (entry.removed_rows || []).length,
			has_server_apply: entry.has_server_apply,
			has_conflicts: entry.has_conflicts,
		};
	});
	fcm_debug(
		state,
		"analyze",
		Object.assign(
			{
				doc: fcm_doc_label(frm),
				summary: {
					server_only: analysis.server_only || [],
					local_only: analysis.local_only || [],
					conflicts: analysis.conflicts || [],
					applied_server: analysis.applied_server || [],
					applied_conflicts: analysis.applied_conflicts || [],
					remaining_local: analysis.remaining_local || [],
					modified_changed: analysis.modified_changed,
					child_table_changes,
				},
				fields: details,
			},
			extra || {}
		),
		has_conflicts ? FCM_LOG_LEVELS.warn : FCM_LOG_LEVELS.info
	);
}

export function fcm_debug_local_drift(state, frm, label) {
	if (!is_fcm_debug_enabled(state) || !state.initial_values) return;

	const initial = state.initial_values;
	const local = snapshot(frm.doc, state.fields);
	const drifted = (state.fields || []).filter((fieldname) => !equal(local[fieldname], initial[fieldname]));
	const details = {};

	drifted.forEach((fieldname) => {
		const entry = {
			initial: summarize_field_value(initial[fieldname]),
			local: summarize_field_value(local[fieldname]),
		};
		if (Array.isArray(local[fieldname]) || Array.isArray(initial[fieldname])) {
			entry.child_table_diff = diff_child_table_snapshots(initial[fieldname], local[fieldname], null);
		}
		details[fieldname] = entry;
	});

	fcm_debug(
		state,
		label || "local_drift",
		{
			doc: fcm_doc_label(frm),
			drifted,
			count: drifted.length,
			fields: details,
		},
		drifted.length ? FCM_LOG_LEVELS.warn : FCM_LOG_LEVELS.info
	);
}

export function fcm_debug_child_tables(state, frm, label, server_doc, extra) {
	if (!is_fcm_debug_enabled(state) || !frm || !frm.doc) return;

	const child_fields = (state.fields || []).filter((fieldname) => is_child_table_field(frm, fieldname));
	if (!child_fields.length) return;

	const initial = state.initial_values || {};
	const local = snapshot(frm.doc, state.fields);
	const server = server_doc ? snapshot(server_doc, state.fields) : null;
	const tables = {};

	child_fields.forEach((fieldname) => {
		tables[fieldname] = {
			classification: server
				? explain_field_classification(fieldname, initial[fieldname], local[fieldname], server[fieldname])
				: null,
			raw_frm: summarize_field_value(frm.doc[fieldname]),
			initial: summarize_field_value(initial[fieldname]),
			local: summarize_field_value(local[fieldname]),
			server: server ? summarize_field_value(server[fieldname]) : null,
			child_table_diff: diff_child_table_snapshots(
				initial[fieldname],
				local[fieldname],
				server ? server[fieldname] : null
			),
		};
	});

	fcm_debug(
		state,
		label || "child_tables",
		Object.assign(
			{
				doc: fcm_doc_label(frm),
				tables,
			},
			extra || {}
		),
		FCM_LOG_LEVELS.warn
	);
}

export function dump_debug_state(frm) {
	frm = frm || cur_frm;
	if (!frm || !frm.doc) return null;

	const state = get_state(frm);
	const payload = {
		doc: fcm_doc_label(frm),
		cfg: state.cfg,
		fields: state.fields,
		initial_modified: state.initial_modified,
		highlighted_fields: Object.assign({}, state.highlighted_fields || {}),
		flags: {
			startup_baseline_ready: state.startup_baseline_ready,
			startup_warmup_active: is_startup_warmup_active(state),
			startup_user_touched: state.startup_user_touched,
			pollers_ready: state.pollers_ready,
		},
	};

	fcm_debug_state_snapshot(state, frm, "dump_debug_state");
	fcm_debug_local_drift(state, frm, "dump_debug_state_drift");
	fcm_debug_child_tables(state, frm, "dump_debug_state_child_tables");
	fcm_emit(FCM_LOG_LEVELS.warn, "dump_debug_state", payload);
	return payload;
}

export const FormMergeDebug = {
	child_table_row_keys,
	count_child_table_rows,
	diff_child_table_rows,
	diff_child_table_snapshots,
	dump_debug_state,
	explain_field_classification,
	fcm_debug,
	fcm_debug_analysis,
	fcm_debug_child_tables,
	fcm_debug_local_drift,
	fcm_debug_state_snapshot,
	is_fcm_debug_enabled,
	summarize_field_value,
};
