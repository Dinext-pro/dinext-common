const registry = (window.__dinext_form_conflict_merge_registry =
	window.__dinext_form_conflict_merge_registry || {});

function get_state(frm) {
	const key = `${frm.doctype}::${frm.docname}`;
	registry[key] = registry[key] || {};
	return registry[key];
}

function is_child_table(df) {
	return df && (df.fieldtype === "Table" || df.fieldtype === "Table MultiSelect");
}

function is_child_table_included(df, cfg) {
	if (!is_child_table(df)) return true;
	if (cfg.include_child_tables === true) return true;
	if (Array.isArray(cfg.include_child_tables)) return cfg.include_child_tables.includes(df.fieldname);
	return false;
}

function is_mergeable_field(df) {
	if (!df || !df.fieldname) return false;
	if (SYSTEM_FIELDS.includes(df.fieldname)) return false;
	if (["Section Break", "Column Break", "Tab Break"].includes(df.fieldtype)) return false;
	if (["HTML", "Button", "Fold"].includes(df.fieldtype)) return false;
	return true;
}

function is_supported_field(df, cfg) {
	return is_mergeable_field(df) && is_child_table_included(df, cfg);
}

function unique_fields(fields) {
	return Array.from(new Set((fields || []).filter(Boolean)));
}

function get_fields(frm, cfg) {
	const meta_fields = frm.meta.fields || [];
	const fields_by_name = {};
	meta_fields.forEach((df) => {
		if (df && df.fieldname) fields_by_name[df.fieldname] = df;
	});

	const base_fields =
		cfg.fields && cfg.fields.length
			? cfg.fields.filter((fieldname) => is_mergeable_field(fields_by_name[fieldname]))
			: meta_fields.filter((df) => is_supported_field(df, cfg)).map((df) => df.fieldname);

	const included_fields = (cfg.include_fields || []).filter((fieldname) =>
		is_mergeable_field(fields_by_name[fieldname])
	);
	const excluded_fields = new Set(cfg.exclude_fields || []);

	return unique_fields(base_fields.concat(included_fields)).filter((fieldname) => !excluded_fields.has(fieldname));
}

function import_pending_local_seeds(frm, state) {
	const pending = frm.__dinext_fcm_local_seeds || {};
	Object.keys(pending).forEach((fieldname) => {
		mark_local_seed(frm, fieldname, pending[fieldname]);
	});
}

function clear_local_seed(frm, fieldname) {
	const state = get_state(frm);
	if (state.local_seed_fields) delete state.local_seed_fields[fieldname];
	if (frm.__dinext_fcm_local_seeds) delete frm.__dinext_fcm_local_seeds[fieldname];
}

function clear_local_seeds(frm) {
	const state = get_state(frm);
	state.local_seed_fields = {};
	frm.__dinext_fcm_local_seeds = {};
}

function mark_local_seed(frm, fieldname, opts) {
	if (!frm || !fieldname) return;
	opts = opts || {};

	const seed = Object.assign(
		{
			preserve_when_server_empty: true,
			initial_value: null,
			local_value: normalize_value(frm.doc ? frm.doc[fieldname] : null),
		},
		opts
	);

	frm.__dinext_fcm_local_seeds = frm.__dinext_fcm_local_seeds || {};
	frm.__dinext_fcm_local_seeds[fieldname] = seed;

	const state = get_state(frm);
	state.local_seed_fields = state.local_seed_fields || {};
	state.local_seed_fields[fieldname] = seed;
	if (state.initial_values) {
		state.initial_values[fieldname] = normalize_value(seed.initial_value);
	}
}

function refresh_initial(frm) {
	const state = get_state(frm);
	if (!state.installed) return;
	state.initial_values = snapshot(frm.doc, state.fields);
	Object.keys(state.local_seed_fields || {}).forEach((fieldname) => {
		const seed = state.local_seed_fields[fieldname];
		if (seed && seed.preserve_when_server_empty && !is_empty_value(frm.doc[fieldname])) {
			state.initial_values[fieldname] = normalize_value(seed.initial_value);
		}
	});
	state.initial_modified = frm.doc.modified;
	state.server_changed = false;
	state.server_modified = null;
	state.server_modified_by = null;
	clear_highlights(frm, state);
	if (frm.dashboard) frm.dashboard.clear_headline();
}

const FormMergeState = {
	clear_local_seed,
	clear_local_seeds,
	get_fields,
	get_state,
	import_pending_local_seeds,
	mark_local_seed,
	refresh_initial,
};
