function normalize_child(row) {
	const out = {};
	Object.keys(row || {})
		.sort()
		.forEach((key) => {
			if (SYSTEM_FIELDS.includes(key)) return;
			out[key] = row[key];
		});
	return out;
}

function normalize_value(value) {
	if (value === undefined) return null;
	if (Array.isArray(value)) return value.map((row) => normalize_child(row));
	if (value && typeof value === "object") return JSON.parse(JSON.stringify(value));
	return value;
}

function is_empty_value(value) {
	if (value === undefined || value === null || value === "") return true;
	if (typeof value !== "string") return false;

	const stripped = value
		.replace(/<[^>]*>/g, "")
		.replace(/&nbsp;/g, " ")
		.trim();
	return !stripped;
}

function snapshot(doc, fields) {
	const out = {};
	fields.forEach((fieldname) => {
		out[fieldname] = normalize_value(doc ? doc[fieldname] : null);
	});
	return out;
}

function equal(left, right) {
	return JSON.stringify(normalize_value(left)) === JSON.stringify(normalize_value(right));
}

function clone_raw_value(value) {
	if (value === undefined) return null;
	if (value && typeof value === "object") return JSON.parse(JSON.stringify(value));
	return value;
}

function should_preserve_local_seed(state, fieldname, local_value, server_value) {
	const seed = state.local_seed_fields && state.local_seed_fields[fieldname];
	if (!seed || !seed.preserve_when_server_empty) return false;

	if (!is_empty_value(server_value)) {
		delete state.local_seed_fields[fieldname];
		return false;
	}

	return !is_empty_value(local_value);
}

function analyze(frm, server_doc, state) {
	const initial = state.initial_values || {};
	const local = snapshot(frm.doc, state.fields);
	const server = snapshot(server_doc, state.fields);
	const server_only = [];
	const local_only = [];
	const conflicts = [];

	state.fields.forEach((fieldname) => {
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

	return { server_only, local_only, conflicts };
}

function get_remaining_local_changes(frm, state) {
	const local = snapshot(frm.doc, state.fields);
	const initial = state.initial_values || {};

	return state.fields.filter((fieldname) => !equal(local[fieldname], initial[fieldname]));
}

const FormDiff = {
	analyze,
	clone_raw_value,
	equal,
	get_remaining_local_changes,
	is_empty_value,
	normalize_child,
	normalize_value,
	should_preserve_local_seed,
	snapshot,
};
