const FCM_LOG_PREFIX = "[FCM]";

const FCM_LOG_LEVELS = {
	info: "info",
	warn: "warn",
};

function is_fcm_debug_enabled(state) {
	if (window.__dinext_fcm_debug) return true;
	try {
		if (window.localStorage && window.localStorage.getItem("dinext_fcm_debug") === "1") return true;
	} catch (e) {
		// ignore private mode / blocked storage
	}
	return Boolean(state && state.cfg && state.cfg.debug_log);
}

function fcm_doc_label(frm) {
	if (!frm || !frm.doctype) return "?";
	return `${frm.doctype}/${frm.docname || "new"}`;
}

function summarize_field_value(value) {
	if (value === undefined) return { kind: "undefined" };
	if (value === null) return { kind: "null" };
	if (Array.isArray(value)) {
		return {
			kind: "child_table",
			rows: value.length,
			names: value.slice(0, 8).map((row) => (row && row.name) || null),
			hash: JSON.stringify(normalize_value(value)).length,
			preview: JSON.stringify(normalize_value(value)).slice(0, 240),
		};
	}
	if (typeof value === "string") {
		return { kind: "string", length: value.length, preview: value.slice(0, 160) };
	}
	return { kind: typeof value, preview: JSON.stringify(value).slice(0, 160) };
}

function fcm_emit(level, event, entry) {
	const payload = Object.assign({ ts: new Date().toISOString(), event }, entry || {});
	if (level === FCM_LOG_LEVELS.warn) {
		console.warn(FCM_LOG_PREFIX, event, payload);
		return;
	}
	console.info(FCM_LOG_PREFIX, event, payload);
}

function fcm_debug(state, event, payload, level) {
	if (!is_fcm_debug_enabled(state)) return;
	fcm_emit(level || FCM_LOG_LEVELS.info, event, payload);
}

function fcm_debug_state_snapshot(state, frm, label) {
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

function fcm_debug_analysis(state, frm, analysis, extra) {
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
		details[fieldname] = {
			local_changed: !equal(local[fieldname], initial[fieldname]),
			server_changed: server ? !equal(server[fieldname], initial[fieldname]) : null,
			equal_local_server: server ? equal(local[fieldname], server[fieldname]) : null,
			local: summarize_field_value(local[fieldname]),
			initial: summarize_field_value(initial[fieldname]),
			server: server ? summarize_field_value(server[fieldname]) : null,
		};
	});

	const has_conflicts = (analysis.conflicts || []).length || (analysis.applied_conflicts || []).length;
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
				},
				fields: details,
			},
			extra || {}
		),
		has_conflicts ? FCM_LOG_LEVELS.warn : FCM_LOG_LEVELS.info
	);
}

function fcm_debug_local_drift(state, frm, label) {
	if (!is_fcm_debug_enabled(state) || !state.initial_values) return;

	const initial = state.initial_values;
	const local = snapshot(frm.doc, state.fields);
	const drifted = (state.fields || []).filter((fieldname) => !equal(local[fieldname], initial[fieldname]));
	const details = {};

	drifted.forEach((fieldname) => {
		details[fieldname] = {
			initial: summarize_field_value(initial[fieldname]),
			local: summarize_field_value(local[fieldname]),
		};
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

function dump_debug_state(frm) {
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
	fcm_emit(FCM_LOG_LEVELS.warn, "dump_debug_state", payload);
	return payload;
}

const FormMergeDebug = {
	dump_debug_state,
	fcm_debug,
	fcm_debug_analysis,
	fcm_debug_local_drift,
	fcm_debug_state_snapshot,
	is_fcm_debug_enabled,
	summarize_field_value,
};
