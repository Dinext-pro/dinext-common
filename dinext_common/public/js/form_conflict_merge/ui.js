function ensure_highlight_styles() {
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
	`;
	document.head.appendChild(style);
}

function get_field_wrapper(frm, fieldname) {
	const field = frm.fields_dict && frm.fields_dict[fieldname];
	return field && field.$wrapper;
}

function clear_highlight(frm, state, fieldname) {
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

function bind_clear_highlight_on_edit(frm, state, fieldname, $wrapper) {
	$wrapper.off(".dinext_fcm_clear_highlight");
	$wrapper.on(
		"focusin.dinext_fcm_clear_highlight input.dinext_fcm_clear_highlight change.dinext_fcm_clear_highlight keydown.dinext_fcm_clear_highlight",
		() => clear_highlight(frm, state, fieldname)
	);
}

function highlight_field(frm, state, fieldname, kind) {
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

function get_form_wrapper(frm) {
	if (!frm || !frm.wrapper) return null;
	return frm.wrapper.on ? frm.wrapper : $(frm.wrapper);
}

function clear_all_fcm_highlights(frm, state) {
	const $root = get_form_wrapper(frm);
	if (!$root) return 0;

	const selector = `.${SERVER_HIGHLIGHT_CLASS}, .${CONFLICT_HIGHLIGHT_CLASS}`;
	const $marked = $root.find(selector).add($root.filter(selector));
	const count = $marked.length;

	$marked.removeClass(`${SERVER_HIGHLIGHT_CLASS} ${CONFLICT_HIGHLIGHT_CLASS}`).off(".dinext_fcm_clear_highlight");

	if (state) {
		fcm_debug(state, "clear_all_highlights", {
			doc: fcm_doc_label(frm),
			count,
		});
	}

	return count;
}

function clear_highlights(frm, state) {
	Object.keys(state.highlighted_fields || {}).forEach((fieldname) => {
		clear_highlight(frm, state, fieldname);
	});
	state.highlighted_fields = {};
}

function show_docinfo_alert(changed_keys, cfg) {
	if (!changed_keys.length || !cfg.show_docinfo_alert) return;

	const labels = cfg.docinfo_key_labels || {};
	const changed_labels = changed_keys.map((key) => labels[key] || key);

	frappe.show_alert({
		message: `Обновлены данные документа: ${changed_labels.join(", ")}`,
		indicator: "orange",
	});
}

function show_realtime_alert(data) {
	const changed_by = data && data.modified_by ? ` (${data.modified_by})` : "";
	frappe.show_alert({
		message: `Документ изменён на сервере${changed_by}. Выполняется сверка изменений.`,
		indicator: "orange",
	});
}

function show_applied_alert(analysis) {
	if (!analysis) return;

	const applied_server = analysis.applied_server || analysis.server_only || [];
	const applied_conflicts = analysis.applied_conflicts || [];
	if (!applied_server.length && !applied_conflicts.length) return;

	const messages = [];
	if (applied_server.length) {
		messages.push(`обновлены поля: ${applied_server.join(", ")}`);
	}
	if (applied_conflicts.length) {
		messages.push(`сервер перезаписал локальные правки: ${applied_conflicts.join(", ")}`);
	}

	frappe.show_alert({
		message: `Объект был изменён на сервере, ${messages.join("; ")}`,
		indicator: applied_conflicts.length ? "red" : "orange",
	});
}

const FormMergeUi = {
	clear_all_fcm_highlights,
	clear_highlight,
	clear_highlights,
	ensure_highlight_styles,
	get_field_wrapper,
	get_form_wrapper,
	highlight_field,
	show_applied_alert,
	show_docinfo_alert,
	show_realtime_alert,
};
