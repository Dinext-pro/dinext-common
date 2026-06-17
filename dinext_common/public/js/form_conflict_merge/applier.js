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

function apply_child_table(frm, server_doc, fieldname) {
	const field = frm.fields_dict && frm.fields_dict[fieldname];
	const child_doctype = field && field.df && field.df.options;
	const rows = clone_raw_value(server_doc[fieldname] || []);
	const before_rows = clone_raw_value(frm.doc[fieldname] || []);
	const state = get_state(frm);

	remove_child_rows_from_locals(frm.doc[fieldname]);
	frm.doc[fieldname] = [];

	rows.forEach((row, index) => {
		row.doctype = row.doctype || child_doctype;
		row.parent = frm.docname;
		row.parentfield = fieldname;
		row.parenttype = frm.doctype;
		row.idx = row.idx || index + 1;

		if (row.doctype && row.name) {
			locals[row.doctype] = locals[row.doctype] || {};
			locals[row.doctype][row.name] = row;
		}

		frm.doc[fieldname].push(row);
	});

	const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
	if (local_doc) local_doc[fieldname] = frm.doc[fieldname];
	frm.refresh_field(fieldname);

	fcm_debug(
		state,
		"apply_child_table",
		{
			doc: fcm_doc_label(frm),
			fieldname,
			child_doctype,
			before: summarize_field_value(before_rows),
			after: summarize_field_value(frm.doc[fieldname]),
			server: summarize_field_value(server_doc[fieldname]),
			child_table_diff: diff_child_table_snapshots(before_rows, frm.doc[fieldname], server_doc[fieldname]),
		},
		FCM_LOG_LEVELS.warn
	);
}

function apply_field(frm, server_doc, fieldname) {
	if (is_child_table_field(frm, fieldname)) {
		apply_child_table(frm, server_doc, fieldname);
		return;
	}

	frm.doc[fieldname] = clone_raw_value(server_doc[fieldname]);
	const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
	if (local_doc) local_doc[fieldname] = frm.doc[fieldname];
	frm.refresh_field(fieldname);
}

function apply_modified(frm, server_doc) {
	if (!server_doc || !server_doc.modified) return;
	frm.doc.modified = server_doc.modified;
	const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
	if (local_doc) local_doc.modified = server_doc.modified;
}

function update_initial_value(state, server_doc, fieldname) {
	state.initial_values[fieldname] = normalize_value(server_doc[fieldname]);
}

function sync_matching_server_values(frm, server_doc, state) {
	const local = snapshot(frm.doc, state.fields);
	const server = snapshot(server_doc, state.fields);
	const synced_fields = [];

	state.fields.forEach((fieldname) => {
		if (equal(local[fieldname], server[fieldname])) {
			state.initial_values[fieldname] = server[fieldname];
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
	remove_child_rows_from_locals,
	sync_matching_server_values,
	update_initial_value,
};
