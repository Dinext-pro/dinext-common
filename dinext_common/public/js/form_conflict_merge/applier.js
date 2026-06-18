function is_child_table_field(frm, fieldname) {
	const field = frm.fields_dict && frm.fields_dict[fieldname];
	const df = field && field.df;
	return df && (df.fieldtype === "Table" || df.fieldtype === "Table MultiSelect");
}

function remove_child_rows_from_locals(rows) {
	(rows || []).forEach((row) => {
		if (row && row.doctype && row.name && locals[row.doctype]) {
			delete locals[row.doctype][row.name];
		}
	});
}

function write_child_rows_to_form(frm, fieldname, rows, child_doctype) {
	remove_child_rows_from_locals(frm.doc[fieldname]);
	frm.doc[fieldname] = [];

	(rows || []).forEach((row, index) => {
		row.doctype = row.doctype || child_doctype;
		row.parent = frm.docname;
		row.parentfield = fieldname;
		row.parenttype = frm.doctype;
		row.idx = index + 1;

		if (row.doctype && row.name && !row.__islocal) {
			locals[row.doctype] = locals[row.doctype] || {};
			locals[row.doctype][row.name] = row;
		}

		frm.doc[fieldname].push(row);
	});

	const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
	if (local_doc) local_doc[fieldname] = frm.doc[fieldname];
	frm.refresh_field(fieldname);
}

function merge_child_table(frm, server_doc, fieldname, state) {
	const field = frm.fields_dict && frm.fields_dict[fieldname];
	const child_doctype = field && field.df && field.df.options;
	const policy = (state.cfg && state.cfg.conflict_policy) || "server_wins";
	const initial_rows = clone_raw_value((state.initial_raw_values && state.initial_raw_values[fieldname]) || []);
	const local_rows = clone_raw_value(frm.doc[fieldname] || []);
	const server_rows = clone_raw_value(server_doc[fieldname] || []);
	const before_rows = clone_raw_value(local_rows);

	const initial_map = build_child_row_map(initial_rows);
	const local_map = build_child_row_map(local_rows);
	const server_map = build_child_row_map(server_rows);
	const merged_rows = [];
	const processed_server_keys = new Set();

	(server_rows || []).forEach((server_row, index) => {
		if (!server_row || server_row.__islocal) return;
		const key = child_row_key(server_row, index);
		processed_server_keys.add(key);
		const local_row = local_map[key];
		const initial_row = initial_map[key] || {};

		if (local_row) {
			merged_rows.push(merge_child_row(initial_row, local_row, server_row, policy));
			return;
		}

		merged_rows.push(clone_raw_value(server_row));
	});

	Object.keys(server_map).forEach((key) => {
		if (key.startsWith("__islocal:") || processed_server_keys.has(key)) return;
		merged_rows.push(clone_raw_value(server_map[key]));
	});

	Object.keys(local_map).forEach((key) => {
		if (key.startsWith("__islocal:")) return;
		if (server_map[key]) return;
		const local_row = local_map[key];
		const initial_row = initial_map[key] || {};
		if (policy !== "server_wins" && local_row && !row_equal(initial_row, local_row)) {
			merged_rows.push(clone_raw_value(local_row));
		}
	});

	(local_rows || []).forEach((local_row) => {
		if (!local_row || !local_row.__islocal) return;
		merged_rows.push(clone_raw_value(local_row));
	});

	write_child_rows_to_form(frm, fieldname, merged_rows, child_doctype);

	fcm_debug(
		state,
		"apply_child_table",
		{
			doc: fcm_doc_label(frm),
			fieldname,
			child_doctype,
			mode: "merge",
			before: summarize_field_value(before_rows),
			after: summarize_field_value(frm.doc[fieldname]),
			server: summarize_field_value(server_doc[fieldname]),
			child_table_diff: diff_child_table_snapshots(before_rows, frm.doc[fieldname], server_doc[fieldname]),
		},
		FCM_LOG_LEVELS.warn
	);
}

function apply_child_table(frm, server_doc, fieldname, state) {
	merge_child_table(frm, server_doc, fieldname, state);
}

function apply_field(frm, server_doc, fieldname, state) {
	if (is_child_table_field(frm, fieldname)) {
		merge_child_table(frm, server_doc, fieldname, state);
		return;
	}

	frm.doc[fieldname] = clone_raw_value(server_doc[fieldname]);
	const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
	if (local_doc) local_doc[fieldname] = frm.doc[fieldname];
	frm.refresh_field(fieldname);
}

function apply_modified(frm, server_doc) {
	if (!server_doc) return;

	if (server_doc.modified) {
		frm.doc.modified = server_doc.modified;
	}
	if (server_doc.modified_by) {
		frm.doc.modified_by = server_doc.modified_by;
	}

	const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
	if (local_doc) {
		if (server_doc.modified) local_doc.modified = server_doc.modified;
		if (server_doc.modified_by) local_doc.modified_by = server_doc.modified_by;
	}

	if (frm.sidebar && frm.sidebar.refresh) {
		frm.sidebar.refresh();
	}
}

function update_initial_value(state, server_doc, fieldname, frm) {
	if (frm && is_child_table_field(frm, fieldname)) {
		state.initial_values[fieldname] = normalize_value(frm.doc[fieldname]);
		state.initial_raw_values = state.initial_raw_values || {};
		state.initial_raw_values[fieldname] = clone_raw_value(frm.doc[fieldname]);
		return;
	}

	state.initial_values[fieldname] = normalize_value(server_doc[fieldname]);
}

function sync_matching_server_values(frm, server_doc, state) {
	const local = snapshot(frm.doc, state.fields);
	const server = snapshot(server_doc, state.fields);
	const synced_fields = [];

	state.fields.forEach((fieldname) => {
		if (equal(local[fieldname], server[fieldname])) {
			state.initial_values[fieldname] = server[fieldname];
			if (is_child_table_field(frm, fieldname)) {
				state.initial_raw_values = state.initial_raw_values || {};
				state.initial_raw_values[fieldname] = clone_raw_value(frm.doc[fieldname]);
			}
			synced_fields.push(fieldname);
		}
	});

	if (synced_fields.length) {
		fcm_debug(state, "sync_matching_baseline", {
			doc: fcm_doc_label(frm),
			synced_fields,
			child_tables: synced_fields.filter((fieldname) => is_child_table_field(frm, fieldname)),
		});
	}
}

function mark_clean(frm) {
	frm.doc.__unsaved = 0;
	const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
	if (local_doc) local_doc.__unsaved = 0;

	if (frm.beforeUnloadListener) {
		removeEventListener("beforeunload", frm.beforeUnloadListener, { capture: true });
	}

	if (frm.toolbar) {
		frm.toolbar.set_indicator();
		frm.toolbar.show_title_as_dirty();
		frm.toolbar.set_primary_action();
	}
}

const FormValueApplier = {
	apply_child_table,
	apply_field,
	apply_modified,
	is_child_table_field,
	mark_clean,
	merge_child_table,
	remove_child_rows_from_locals,
	sync_matching_server_values,
	update_initial_value,
	write_child_rows_to_form,
};
