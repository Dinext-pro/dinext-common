import { SYSTEM_FIELDS } from "./config.js";

export function is_absent_normalized_value(value) {
	if (value === undefined || value === null) return true;
	if (value === "") return true;
	return false;
}

export function normalize_child(row) {
	const out = {};
	Object.keys(row || {})
		.sort()
		.forEach((key) => {
			if (SYSTEM_FIELDS.includes(key)) return;
			const value = row[key];
			if (is_absent_normalized_value(value)) return;
			out[key] = value;
		});
	return out;
}

export function normalize_child_table_rows(value) {
	if (!Array.isArray(value)) return null;

	return value
		.filter((row) => row && !row.__islocal)
		.slice()
		.sort((left, right) =>
			String(left.name || left.idx || "").localeCompare(String(right.name || right.idx || ""))
		)
		.map((row) => normalize_child(row));
}

export function normalize_value(value) {
	if (value === undefined) return null;
	if (Array.isArray(value)) return normalize_child_table_rows(value);
	if (value && typeof value === "object") return JSON.parse(JSON.stringify(value));
	return value;
}

export function is_empty_value(value) {
	if (value === undefined || value === null || value === "") return true;
	if (typeof value !== "string") return false;

	const stripped = value
		.replace(/<[^>]*>/g, "")
		.replace(/&nbsp;/g, " ")
		.trim();
	return !stripped;
}

export function snapshot(doc, fields) {
	const out = {};
	fields.forEach((fieldname) => {
		out[fieldname] = normalize_value(doc ? doc[fieldname] : null);
	});
	return out;
}

export function equal(left, right) {
	return JSON.stringify(normalize_value(left)) === JSON.stringify(normalize_value(right));
}

export function clone_raw_value(value) {
	if (value === undefined) return null;
	if (value && typeof value === "object") return JSON.parse(JSON.stringify(value));
	return value;
}

export function is_child_table_fieldname(frm, fieldname) {
	const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
	const df = field && field.df;
	return df && (df.fieldtype === "Table" || df.fieldtype === "Table MultiSelect");
}

export function child_row_key(row, index) {
	if (row && row.name && !row.__islocal) return `name:${row.name}`;
	if (row && row.__islocal) return `__islocal:${row.idx || index}`;
	return `idx:${index}`;
}

export function build_child_row_map(rows) {
	const map = {};
	(rows || []).forEach((row, index) => {
		if (!row) return;
		map[child_row_key(row, index)] = row;
	});
	return map;
}

export function row_equal(left_row, right_row) {
	return equal(left_row, right_row);
}

export function classify_child_row_fields(initial_row, local_row, server_row) {
	const normalized_keys = new Set([
		...Object.keys(normalize_child(initial_row || {})),
		...Object.keys(normalize_child(local_row || {})),
		...Object.keys(normalize_child(server_row || {})),
	]);
	[initial_row, local_row, server_row].forEach((row) => {
		Object.keys(row || {}).forEach((key) => {
			if (!SYSTEM_FIELDS.includes(key)) normalized_keys.add(key);
		});
	});

	const initial_norm = normalize_child(initial_row || {});
	const local_norm = normalize_child(local_row || {});
	const server_norm = normalize_child(server_row || {});

	const server_only_fields = [];
	const local_only_fields = [];
	const conflict_fields = [];

	normalized_keys.forEach((fieldname) => {
		const initial_value = initial_norm[fieldname];
		const local_value = local_norm[fieldname];
		const server_value = server_norm[fieldname];
		const local_changed = initial_value !== local_value;
		const server_changed = initial_value !== server_value;

		if (!local_changed && server_changed) {
			server_only_fields.push(fieldname);
			return;
		}
		if (local_changed && !server_changed) {
			local_only_fields.push(fieldname);
			return;
		}
		if (local_changed && server_changed && local_value === server_value) {
			// Форма уже совпала с сервером (realtime / предыдущий apply), baseline устарел.
			server_only_fields.push(fieldname);
			return;
		}
		if (local_changed && server_changed && local_value !== server_value) {
			conflict_fields.push(fieldname);
		}
	});

	return { server_only_fields, local_only_fields, conflict_fields };
}

export function merge_child_row(initial_row, local_row, server_row, policy) {
	const merged = clone_raw_value(local_row || server_row || initial_row || {});
	const { server_only_fields, conflict_fields } = classify_child_row_fields(
		initial_row || {},
		local_row || merged,
		server_row || {}
	);

	server_only_fields.forEach((fieldname) => {
		if (server_row && Object.prototype.hasOwnProperty.call(server_row, fieldname)) {
			merged[fieldname] = clone_raw_value(server_row[fieldname]);
		} else {
			delete merged[fieldname];
		}
	});

	if (policy === "server_wins") {
		conflict_fields.forEach((fieldname) => {
			if (server_row && Object.prototype.hasOwnProperty.call(server_row, fieldname)) {
				merged[fieldname] = clone_raw_value(server_row[fieldname]);
			}
		});
	}

	return merged;
}

export function child_row_ref(row, key) {
	return {
		row_key: key,
		row_name: row && row.name && !row.__islocal ? row.name : null,
		idx: row && row.idx != null ? row.idx : null,
		row: row ? clone_raw_value(row) : null,
	};
}

export function analyze_child_table_merge(initial_rows, local_rows, server_rows, policy) {
	const initial_map = build_child_row_map(initial_rows);
	const local_map = build_child_row_map(local_rows);
	const server_map = build_child_row_map(server_rows);

	let has_server_apply = false;
	let has_conflicts = false;
	let has_local_only = false;
	const changed_rows = [];
	const added_rows = [];
	const removed_rows = [];

	const persisted_keys = new Set();
	Object.keys(initial_map).forEach((key) => {
		if (!key.startsWith("__islocal:")) persisted_keys.add(key);
	});
	Object.keys(local_map).forEach((key) => {
		if (!key.startsWith("__islocal:")) persisted_keys.add(key);
	});
	Object.keys(server_map).forEach((key) => {
		if (!key.startsWith("__islocal:")) persisted_keys.add(key);
	});

	persisted_keys.forEach((key) => {
		const initial_row = initial_map[key] || {};
		const local_row = local_map[key];
		const server_row = server_map[key];

		if (!server_row && initial_map[key]) {
			if (local_row && !row_equal(initial_map[key], local_row)) {
				has_server_apply = true;
				if (policy !== "server_wins") has_conflicts = true;
			} else {
				has_server_apply = true;
			}
			removed_rows.push(child_row_ref(initial_map[key], key));
			return;
		}

		if (!local_row && server_row) {
			const initial_row = initial_map[key] || {};
			if (!row_equal(initial_row, server_row)) has_server_apply = true;
			if (initial_map[key]) {
				const classification = classify_child_row_fields(initial_row, server_row, server_row);
				if (classification.server_only_fields.length || classification.conflict_fields.length) {
					changed_rows.push(
						Object.assign(child_row_ref(server_row, key), {
							server_fields: classification.server_only_fields.slice(),
							conflict_fields: classification.conflict_fields.slice(),
						})
					);
				}
			}
			return;
		}

		if (!local_row || !server_row) return;

		const classification = classify_child_row_fields(initial_map[key] || {}, local_row, server_row);
		if (classification.server_only_fields.length) has_server_apply = true;
		if (classification.local_only_fields.length) has_local_only = true;
		if (classification.conflict_fields.length) {
			has_server_apply = true;
			has_conflicts = true;
		}

		if (classification.server_only_fields.length || classification.conflict_fields.length) {
			changed_rows.push(
				Object.assign(child_row_ref(server_row || local_row, key), {
					server_fields: classification.server_only_fields.slice(),
					conflict_fields: classification.conflict_fields.slice(),
				})
			);
		}
	});

	Object.keys(server_map).forEach((key) => {
		if (key.startsWith("__islocal:")) return;
		if (!initial_map[key] && server_map[key]) {
			has_server_apply = true;
			added_rows.push(child_row_ref(server_map[key], key));
		}
	});

	Object.keys(local_map).forEach((key) => {
		if (key.startsWith("__islocal:") && local_map[key]) has_local_only = true;
	});

	return { has_server_apply, has_conflicts, has_local_only, changed_rows, added_rows, removed_rows };
}

export function should_preserve_local_seed(state, fieldname, local_value, server_value) {
	const seed = state.local_seed_fields && state.local_seed_fields[fieldname];
	if (!seed || !seed.preserve_when_server_empty) return false;

	if (!is_empty_value(server_value)) {
		delete state.local_seed_fields[fieldname];
		return false;
	}

	return !is_empty_value(local_value);
}

export function analyze(frm, server_doc, state) {
	const initial = state.initial_values || {};
	const local = snapshot(frm.doc, state.fields);
	const server = snapshot(server_doc, state.fields);
	const server_only = [];
	const local_only = [];
	const conflicts = [];
	const child_table_changes = {};

	state.fields.forEach((fieldname) => {
		if (frm && is_child_table_fieldname(frm, fieldname)) {
			const initial_rows =
				(state.initial_raw_values && state.initial_raw_values[fieldname]) || frm.doc[fieldname] || [];
			const child_analysis = analyze_child_table_merge(
				initial_rows,
				frm.doc[fieldname] || [],
				server_doc[fieldname] || [],
				state.cfg.conflict_policy
			);
			child_table_changes[fieldname] = child_analysis;

			if (child_analysis.has_conflicts) {
				conflicts.push(fieldname);
			} else if (child_analysis.has_server_apply) {
				server_only.push(fieldname);
			} else if (child_analysis.has_local_only) {
				local_only.push(fieldname);
			}
			return;
		}

		const local_changed = !equal(local[fieldname], initial[fieldname]);
		const server_changed = !equal(server[fieldname], initial[fieldname]);

		if (should_preserve_local_seed(state, fieldname, local[fieldname], server[fieldname])) {
			local_only.push(fieldname);
			return;
		}

		if (!local_changed && server_changed) {
			server_only.push(fieldname);
			return;
		}

		if (local_changed && !server_changed) {
			local_only.push(fieldname);
			return;
		}

		if (local_changed && server_changed && !equal(local[fieldname], server[fieldname])) {
			conflicts.push(fieldname);
		}
	});

	return { server_only, local_only, conflicts, child_table_changes };
}

export function get_remaining_local_changes(frm, state) {
	const local = snapshot(frm.doc, state.fields);
	const initial = state.initial_values || {};

	return state.fields.filter((fieldname) => !equal(local[fieldname], initial[fieldname]));
}

export const FormDiff = {
	analyze,
	analyze_child_table_merge,
	build_child_row_map,
	child_row_key,
	child_row_ref,
	classify_child_row_fields,
	clone_raw_value,
	equal,
	get_remaining_local_changes,
	is_absent_normalized_value,
	is_child_table_fieldname,
	is_empty_value,
	merge_child_row,
	normalize_child,
	normalize_child_table_rows,
	normalize_value,
	row_equal,
	should_preserve_local_seed,
	snapshot,
};
