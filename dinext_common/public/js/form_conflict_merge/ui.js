import {
	CHILD_CELL_CONFLICT_CLASS,
	CHILD_CELL_SERVER_CLASS,
	CHILD_ROW_ADDED_CLASS,
	CHILD_TABLE_REMOVED_CLASS,
	CONFLICT_HIGHLIGHT_CLASS,
	HIGHLIGHT_STYLE_ID,
	SERVER_HIGHLIGHT_CLASS,
} from "./config.js";
import { fcm_debug, fcm_doc_label, FCM_LOG_LEVELS } from "./debug.js";
import { is_child_table_field } from "./applier.js";

export function ensure_highlight_styles() {
	if (document.getElementById(HIGHLIGHT_STYLE_ID)) return;

	const style = document.createElement("style");
	style.id = HIGHLIGHT_STYLE_ID;
	style.textContent = `
		.${SERVER_HIGHLIGHT_CLASS} .control-input,
		.${SERVER_HIGHLIGHT_CLASS} .form-control,
		.${SERVER_HIGHLIGHT_CLASS} .ql-editor,
		.${SERVER_HIGHLIGHT_CLASS} .grid-body {
			outline: 2px solid #f0ad4e !important;
			outline-offset: 2px;
			border-radius: 4px;
		}
		.${CONFLICT_HIGHLIGHT_CLASS} .control-input,
		.${CONFLICT_HIGHLIGHT_CLASS} .form-control,
		.${CONFLICT_HIGHLIGHT_CLASS} .ql-editor,
		.${CONFLICT_HIGHLIGHT_CLASS} .grid-body {
			outline: 2px solid #d9534f !important;
			outline-offset: 2px;
			border-radius: 4px;
		}
		.${CHILD_CELL_SERVER_CLASS} {
			outline: 2px solid #f0ad4e !important;
			outline-offset: -1px;
			border-radius: 3px;
		}
		.${CHILD_CELL_SERVER_CLASS} .control-input,
		.${CHILD_CELL_SERVER_CLASS} .form-control,
		.${CHILD_CELL_SERVER_CLASS} .static-area,
		.${CHILD_CELL_SERVER_CLASS} .field-area {
			outline: none !important;
		}
		.${CHILD_CELL_CONFLICT_CLASS} {
			outline: 2px solid #d9534f !important;
			outline-offset: -1px;
			border-radius: 3px;
		}
		.${CHILD_CELL_CONFLICT_CLASS} .control-input,
		.${CHILD_CELL_CONFLICT_CLASS} .form-control,
		.${CHILD_CELL_CONFLICT_CLASS} .static-area,
		.${CHILD_CELL_CONFLICT_CLASS} .field-area {
			outline: none !important;
		}
		.${CHILD_ROW_ADDED_CLASS} {
			outline: 2px solid #f0ad4e !important;
			outline-offset: -2px;
			border-radius: 4px;
		}
		.${CHILD_TABLE_REMOVED_CLASS} .form-grid,
		.${CHILD_TABLE_REMOVED_CLASS} .grid-body {
			border-bottom: 2px solid #f0ad4e !important;
		}
	`;
	document.head.appendChild(style);
}

export function get_field_wrapper(frm, fieldname) {
	const field = frm.fields_dict && frm.fields_dict[fieldname];
	return field && field.$wrapper;
}

export function get_field_label(frm, fieldname) {
	const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
	const df = field && field.df;
	if (df && df.label) return __(df.label);
	return fieldname;
}

export function format_field_labels(frm, fieldnames) {
	return (fieldnames || []).map((fieldname) => get_field_label(frm, fieldname));
}

export function get_alert_duration(cfg, indicator) {
	const base = Number((cfg && cfg.alert_duration_seconds) || 7);
	if (indicator === "red") {
		return Number((cfg && cfg.conflict_alert_duration_seconds) || base * 2);
	}
	return base;
}

export function resolve_user_full_name(user) {
	if (!user) return "";
	if (frappe.user && frappe.user.full_name) {
		return frappe.user.full_name(user) || user;
	}
	if (frappe.boot && frappe.boot.user_info && frappe.boot.user_info[user]) {
		return frappe.boot.user_info[user].fullname || user;
	}
	return user;
}

export function format_modifier_prefix(modified_by) {
	if (!modified_by) return "";
	const current_user = frappe.session && frappe.session.user;
	if (!current_user || modified_by === current_user) return "";
	return `${resolve_user_full_name(modified_by)} изменил документ на сервере. `;
}

export function show_fcm_alert(cfg, message, indicator) {
	frappe.show_alert({ message, indicator }, get_alert_duration(cfg, indicator));
}

export function get_child_table_grid(frm, fieldname) {
	const field = frm.fields_dict && frm.fields_dict[fieldname];
	return field && field.grid;
}

export function child_table_has_highlight_targets(child_analysis) {
	if (!child_analysis) return false;
	return Boolean(
		(child_analysis.changed_rows && child_analysis.changed_rows.length) ||
			(child_analysis.added_rows && child_analysis.added_rows.length) ||
			(child_analysis.removed_rows && child_analysis.removed_rows.length)
	);
}

export function get_child_row_label(frm, fieldname, row) {
	if (!row) return "";
	const grid = get_child_table_grid(frm, fieldname);
	const docfields = (grid && grid.docfields) || [];
	for (let index = 0; index < docfields.length; index += 1) {
		const df = docfields[index];
		if (!df || !df.in_list_view) continue;
		const value = row[df.fieldname];
		if (value !== undefined && value !== null && value !== "") return String(value);
	}
	if (row.idx != null) return `#${row.idx}`;
	return "";
}

export function find_grid_row_element(grid, row_ref) {
	if (!grid || !row_ref) return null;

	if (row_ref.row_name && grid.wrapper) {
		const $by_name = grid.wrapper.find(`.grid-row[data-name="${row_ref.row_name}"]`);
		if ($by_name.length) return $by_name.first();
	}

	if (row_ref.idx != null && grid.wrapper) {
		const $by_idx = grid.wrapper.find(`.grid-row[data-idx="${row_ref.idx}"]`);
		if ($by_idx.length) return $by_idx.first();
	}

	if (grid.grid_rows) {
		for (let index = 0; index < grid.grid_rows.length; index += 1) {
			const grid_row = grid.grid_rows[index];
			const doc = grid_row && grid_row.doc;
			if (!doc) continue;
			if (row_ref.row_name && doc.name === row_ref.row_name) return grid_row.row;
			if (row_ref.idx != null && doc.idx === row_ref.idx) return grid_row.row;
		}
	}

	return null;
}

export function clear_child_table_removed_highlight(frm, fieldname) {
	const $wrapper = get_field_wrapper(frm, fieldname);
	if ($wrapper) $wrapper.removeClass(CHILD_TABLE_REMOVED_CLASS);
}

export function clear_child_table_highlights(frm, state, fieldname) {
	const grid = get_child_table_grid(frm, fieldname);
	if (grid && grid.wrapper) {
		grid.wrapper
			.find(
				`.${CHILD_CELL_SERVER_CLASS}, .${CHILD_CELL_CONFLICT_CLASS}, .${CHILD_ROW_ADDED_CLASS}`
			)
			.removeClass(`${CHILD_CELL_SERVER_CLASS} ${CHILD_CELL_CONFLICT_CLASS} ${CHILD_ROW_ADDED_CLASS}`)
			.off(".dinext_fcm_clear_child_highlight");
		grid.wrapper.off(".dinext_fcm_clear_child_highlight");
		clear_child_table_removed_highlight(frm, fieldname);
	}

	if (state && state.highlighted_child_tables) {
		delete state.highlighted_child_tables[fieldname];
	}

	fcm_debug(state, "highlight_child_clear", {
		doc: fcm_doc_label(frm),
		fieldname,
	});
}

export function bind_clear_child_highlight_on_edit(frm, state, fieldname, grid) {
	if (!grid || !grid.wrapper) return;
	grid.wrapper.off(".dinext_fcm_clear_child_highlight");
	grid.wrapper.on(
		"focusin.dinext_fcm_clear_child_highlight input.dinext_fcm_clear_child_highlight change.dinext_fcm_clear_child_highlight keydown.dinext_fcm_clear_child_highlight",
		() => clear_child_table_highlights(frm, state, fieldname)
	);
}

export function highlight_grid_cell($row, child_fieldname, kind) {
	if (!$row || !$row.length || !child_fieldname) return;
	const highlight_class = kind === "conflict" ? CHILD_CELL_CONFLICT_CLASS : CHILD_CELL_SERVER_CLASS;
	const $cell = $row.find(`.grid-static-col[data-fieldname="${child_fieldname}"]`).first();
	if (!$cell.length) return;
	$cell.removeClass(`${CHILD_CELL_SERVER_CLASS} ${CHILD_CELL_CONFLICT_CLASS}`);
	$cell.addClass(highlight_class);
}

export function highlight_child_table_removed_border(frm, fieldname) {
	const $wrapper = get_field_wrapper(frm, fieldname);
	if (!$wrapper) return;
	$wrapper.addClass(CHILD_TABLE_REMOVED_CLASS);
}

export function highlight_child_table_changes(frm, state, fieldname, child_analysis, attempt) {
	if (!state.cfg.highlight_server_changes) return;
	if (!child_table_has_highlight_targets(child_analysis)) return;

	const grid = get_child_table_grid(frm, fieldname);
	if (!grid) {
		fcm_debug(
			state,
			"highlight_child_table_grid_missing",
			{
				doc: fcm_doc_label(frm),
				fieldname,
				attempt: attempt || 0,
			},
			FCM_LOG_LEVELS.warn
		);
		return false;
	}

	clear_child_table_highlights(frm, state, fieldname);

	let cell_count = 0;
	let row_count = 0;
	let missing_rows = 0;

	(child_analysis.changed_rows || []).forEach((row_ref) => {
		const $row = find_grid_row_element(grid, row_ref);
		if (!$row || !$row.length) {
			missing_rows += 1;
			return;
		}
		(row_ref.conflict_fields || []).forEach((child_fieldname) => {
			highlight_grid_cell($row, child_fieldname, "conflict");
			cell_count += 1;
		});
		(row_ref.server_fields || []).forEach((child_fieldname) => {
			highlight_grid_cell($row, child_fieldname, "server");
			cell_count += 1;
		});
	});

	(child_analysis.added_rows || []).forEach((row_ref) => {
		const $row = find_grid_row_element(grid, row_ref);
		if (!$row || !$row.length) {
			missing_rows += 1;
			return;
		}
		$row.addClass(CHILD_ROW_ADDED_CLASS);
		row_count += 1;
	});

	if (child_analysis.removed_rows && child_analysis.removed_rows.length) {
		highlight_child_table_removed_border(frm, fieldname);
	}

	bind_clear_child_highlight_on_edit(frm, state, fieldname, grid);

	state.highlighted_child_tables = state.highlighted_child_tables || {};
	state.highlighted_child_tables[fieldname] = {
		changed_rows: (child_analysis.changed_rows || []).length,
		added_rows: (child_analysis.added_rows || []).length,
		removed_rows: (child_analysis.removed_rows || []).length,
	};

	fcm_debug(state, "highlight_child_table", {
		doc: fcm_doc_label(frm),
		fieldname,
		cell_count,
		row_count,
		missing_rows,
		removed_rows: (child_analysis.removed_rows || []).length,
		attempt: attempt || 0,
	});

	return missing_rows === 0;
}

export function schedule_child_table_highlights(frm, state, fieldname, child_analysis) {
	const max_attempts = 12;
	const retry_ms = 50;

	const run = (attempt) => {
		const done = highlight_child_table_changes(frm, state, fieldname, child_analysis, attempt);
		if (done || attempt >= max_attempts) return;
		setTimeout(() => run(attempt + 1), retry_ms);
	};

	if (typeof requestAnimationFrame === "function") {
		requestAnimationFrame(() => requestAnimationFrame(() => run(0)));
		return;
	}
	setTimeout(() => run(0), 0);
}

export function apply_field_highlight(frm, state, fieldname, kind, analysis, silent_startup) {
	if (silent_startup || !state.cfg.highlight_server_changes) return;

	if (is_child_table_field(frm, fieldname)) {
		const child_analysis = analysis.child_table_changes && analysis.child_table_changes[fieldname];
		if (child_table_has_highlight_targets(child_analysis)) {
			schedule_child_table_highlights(frm, state, fieldname, child_analysis);
			return;
		}
	}

	highlight_field(frm, state, fieldname, kind);
}

export function clear_highlight(frm, state, fieldname) {
	const $wrapper = get_field_wrapper(frm, fieldname);
	if ($wrapper) {
		$wrapper.removeClass(`${SERVER_HIGHLIGHT_CLASS} ${CONFLICT_HIGHLIGHT_CLASS}`);
		$wrapper.off(".dinext_fcm_clear_highlight");
	}
	if (state.highlighted_fields) {
		delete state.highlighted_fields[fieldname];
	}
	fcm_debug(state, "highlight_clear", {
		doc: fcm_doc_label(frm),
		fieldname,
	});
}

export function bind_clear_highlight_on_edit(frm, state, fieldname, $wrapper) {
	$wrapper.off(".dinext_fcm_clear_highlight");
	$wrapper.on(
		"focusin.dinext_fcm_clear_highlight input.dinext_fcm_clear_highlight change.dinext_fcm_clear_highlight keydown.dinext_fcm_clear_highlight",
		() => clear_highlight(frm, state, fieldname)
	);
}

export function highlight_field(frm, state, fieldname, kind) {
	if (!state.cfg.highlight_server_changes) return;
	const $wrapper = get_field_wrapper(frm, fieldname);
	if (!$wrapper) return;

	$wrapper.removeClass(`${SERVER_HIGHLIGHT_CLASS} ${CONFLICT_HIGHLIGHT_CLASS}`);
	$wrapper.addClass(kind === "conflict" ? CONFLICT_HIGHLIGHT_CLASS : SERVER_HIGHLIGHT_CLASS);
	bind_clear_highlight_on_edit(frm, state, fieldname, $wrapper);

	state.highlighted_fields = state.highlighted_fields || {};
	state.highlighted_fields[fieldname] = kind;

	fcm_debug(state, "highlight", {
		doc: fcm_doc_label(frm),
		fieldname,
		kind,
		wrapper_found: Boolean($wrapper),
	}, kind === "conflict" ? FCM_LOG_LEVELS.warn : FCM_LOG_LEVELS.info);
}

export function get_form_wrapper(frm) {
	if (!frm || !frm.wrapper) return null;
	return frm.wrapper.on ? frm.wrapper : $(frm.wrapper);
}

export function clear_all_fcm_highlights(frm, state) {
	const $root = get_form_wrapper(frm);
	if (!$root) return 0;

	const selector = [
		`.${SERVER_HIGHLIGHT_CLASS}`,
		`.${CONFLICT_HIGHLIGHT_CLASS}`,
		`.${CHILD_TABLE_REMOVED_CLASS}`,
		`.${CHILD_CELL_SERVER_CLASS}`,
		`.${CHILD_CELL_CONFLICT_CLASS}`,
		`.${CHILD_ROW_ADDED_CLASS}`,
	].join(", ");
	const $marked = $root.find(selector).add($root.filter(selector));
	const count = $marked.length;

	$marked
		.removeClass(
			`${SERVER_HIGHLIGHT_CLASS} ${CONFLICT_HIGHLIGHT_CLASS} ${CHILD_TABLE_REMOVED_CLASS} ${CHILD_CELL_SERVER_CLASS} ${CHILD_CELL_CONFLICT_CLASS} ${CHILD_ROW_ADDED_CLASS}`
		)
		.off(".dinext_fcm_clear_highlight")
		.off(".dinext_fcm_clear_child_highlight");

	if (state) {
		if (state.highlighted_child_tables) state.highlighted_child_tables = {};
		fcm_debug(state, "clear_all_highlights", {
			doc: fcm_doc_label(frm),
			count,
		});
	}

	return count;
}

export function clear_highlights(frm, state) {
	Object.keys(state.highlighted_fields || {}).forEach((fieldname) => {
		clear_highlight(frm, state, fieldname);
	});
	state.highlighted_fields = {};

	Object.keys(state.highlighted_child_tables || {}).forEach((fieldname) => {
		clear_child_table_highlights(frm, state, fieldname);
	});
	state.highlighted_child_tables = {};
}

export function show_docinfo_alert(changed_keys, cfg) {
	if (!changed_keys.length || !cfg.show_docinfo_alert) return;

	const labels = cfg.docinfo_key_labels || {};
	const changed_labels = changed_keys.map((key) => labels[key] || key);

	show_fcm_alert(cfg, `Обновлены данные документа: ${changed_labels.join(", ")}`, "orange");
}

export function show_realtime_alert(data, frm, cfg) {
	cfg = cfg || {};
	const prefix = format_modifier_prefix(data && data.modified_by);
	show_fcm_alert(cfg, `${prefix}Выполняется сверка изменений.`, "orange");
}

export function show_applied_alert(frm, analysis, cfg) {
	if (!analysis) return;
	cfg = cfg || {};

	const applied_server = analysis.applied_server || analysis.server_only || [];
	const applied_conflicts = analysis.applied_conflicts || [];
	if (!applied_server.length && !applied_conflicts.length) return;

	const prefix = format_modifier_prefix(analysis.server_modified_by);
	const messages = [];
	if (applied_server.length) {
		messages.push(`обновлены поля: ${format_field_labels(frm, applied_server).join(", ")}`);
	}
	if (applied_conflicts.length) {
		messages.push(
			`сервер перезаписал локальные правки: ${format_field_labels(frm, applied_conflicts).join(", ")}`
		);
	}

	const indicator = applied_conflicts.length ? "red" : "orange";
	show_fcm_alert(cfg, `${prefix}Объект был изменён на сервере, ${messages.join("; ")}`, indicator);
}

export const FormMergeUi = {
	apply_field_highlight,
	child_table_has_highlight_targets,
	clear_all_fcm_highlights,
	clear_child_table_highlights,
	clear_highlight,
	clear_highlights,
	ensure_highlight_styles,
	format_field_labels,
	format_modifier_prefix,
	get_alert_duration,
	get_child_table_grid,
	get_field_label,
	get_field_wrapper,
	get_form_wrapper,
	highlight_child_table_changes,
	highlight_field,
	resolve_user_full_name,
	schedule_child_table_highlights,
	show_applied_alert,
	show_docinfo_alert,
	show_fcm_alert,
	show_realtime_alert,
};
