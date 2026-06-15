function cancel_pending_reload(frm) {
	if (frm.debounced_reload_doc && frm.debounced_reload_doc.cancel) {
		frm.debounced_reload_doc.cancel();
	}
}

function apply_server_changes(frm, server_doc, state, opts) {
	opts = opts || {};
	const silent_startup = opts.silent || is_startup_warmup_active(state);
	const modified_changed = Boolean(server_doc && server_doc.modified && server_doc.modified !== state.initial_modified);
	const analysis = analyze(frm, server_doc, state);
	const applied_server = analysis.server_only.slice();
	const applied_conflicts = state.cfg.conflict_policy === "server_wins" ? analysis.conflicts.slice() : [];

	applied_server.forEach((fieldname) => {
		apply_field(frm, server_doc, fieldname);
		update_initial_value(state, server_doc, fieldname);
		if (!silent_startup) highlight_field(frm, state, fieldname, "server");
	});

	applied_conflicts.forEach((fieldname) => {
		apply_field(frm, server_doc, fieldname);
		update_initial_value(state, server_doc, fieldname);
		if (!silent_startup) highlight_field(frm, state, fieldname, "conflict");
	});

	apply_modified(frm, server_doc);
	sync_matching_server_values(frm, server_doc, state);

	analysis.applied_server = applied_server;
	analysis.applied_conflicts = applied_conflicts;
	analysis.remaining_local = get_remaining_local_changes(frm, state);
	analysis.modified_changed = modified_changed;

	state.server_changed = analysis.conflicts.length > applied_conflicts.length;
	state.server_modified = server_doc.modified;
	state.server_modified_by = server_doc.modified_by;

	if (!state.server_changed) {
		state.initial_modified = server_doc.modified;
	}

	if (!analysis.remaining_local.length) {
		mark_clean(frm);
	}

	if (modified_changed && state.cfg.refresh_docinfo_on_server_apply) {
		refresh_docinfo(frm, state, { silent: silent_startup });
	}

	return analysis;
}

function handle_doc_update(data) {
	const frm = cur_frm;
	if (!frm || !frm.doc || frm.is_new() || !data) return;
	if (data.doctype !== frm.doctype || data.name !== frm.docname) return;
	if (frappe.ui.form.is_saving) return;
	if (data.modified && data.modified === frm.doc.modified) return;

	const state = get_state(frm);
	if (!state.installed) return;

	cancel_pending_reload(frm);

	state.server_changed = true;
	state.server_modified = data.modified;
	state.server_modified_by = data.modified_by;

	const silent_startup = is_startup_warmup_active(state);
	if (state.cfg.show_realtime_alert && !silent_startup) {
		show_realtime_alert(data);
	}

	if (state.cfg.apply_server_changes_on_realtime) {
		fetch_server_doc(frm).then((server_doc) => {
			if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) return;
			const analysis = apply_server_changes(frm, server_doc, state, { silent: silent_startup });
			if (state.cfg.show_applied_alert && !silent_startup) show_applied_alert(analysis);
		});
	}
}

function init_listener() {
	if (window.__dinext_form_conflict_merge_listener_ready) return;
	window.__dinext_form_conflict_merge_listener_ready = true;
	frappe.realtime.on("doc_update", handle_doc_update);
}

function check_server_changes(frm, state) {
	if (!frm || !frm.doc || frm.is_new()) return Promise.resolve();
	state = state || get_state(frm);
	if (!state.installed) return Promise.resolve();

	return fetch_server_doc(frm).then((server_doc) => {
		if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) return;
		const silent_startup = is_startup_warmup_active(state);
		const analysis = apply_server_changes(frm, server_doc, state, { silent: silent_startup });
		if (state.cfg.show_applied_alert && !silent_startup) show_applied_alert(analysis);
		return analysis;
	});
}

function init_polling(frm, state) {
	const interval = Number(state.cfg.poll_server_changes_interval_ms || 0);
	if (!interval || interval < 1000) return;

	if (state.poll_timer) {
		clearInterval(state.poll_timer);
	}

	state.poll_timer = setInterval(() => {
		const current = cur_frm;
		if (!current || current.doctype !== frm.doctype || current.docname !== frm.docname) return;
		check_server_changes(current, state);
	}, interval);
}

function confirm_conflicts(conflicts, cfg) {
	if (!conflicts.length) return Promise.resolve("continue");
	if (cfg.conflict_policy === "local_wins") return Promise.resolve("local_wins");
	if (cfg.conflict_policy === "server_wins") return Promise.resolve("server_wins");
	if (cfg.conflict_policy === "block") return Promise.resolve("block");

	return new Promise((resolve) => {
		const message = [
			"Документ был изменён на сервере, и часть полей конфликтует с вашими правками.",
			"",
			`Конфликтующие поля: ${conflicts.join(", ")}`,
			"",
			"Выберите, как продолжить сохранение.",
		].join("<br>");

		const dialog = new frappe.ui.Dialog({
			title: "Конфликт изменений",
			fields: [{ fieldtype: "HTML", fieldname: "message", options: message }],
			primary_action_label: "Сохранить мои значения",
			primary_action() {
				dialog.hide();
				resolve("local_wins");
			},
			secondary_action_label: "Взять значения сервера",
			secondary_action() {
				dialog.hide();
				resolve("server_wins");
			},
		});

		dialog.$wrapper.find(".modal-footer").prepend(
			$(`<button class="btn btn-default btn-sm">${__("Отменить сохранение")}</button>`).on("click", () => {
				dialog.hide();
				resolve("block");
			})
		);

		dialog.show();
	});
}

function fetch_server_doc(frm) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: "frappe.client.get",
			type: "GET",
			args: {
				doctype: frm.doctype,
				name: frm.docname,
			},
			callback(r) {
				resolve(r.message);
			},
			error: reject,
		});
	});
}

function before_save(frm) {
	if (frm.is_new()) return Promise.resolve();

	const state = get_state(frm);
	if (!state.installed) return Promise.resolve();

	return fetch_server_doc(frm).then((server_doc) => {
		if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) return;

		if (state.cfg.conflict_policy === "server_wins") {
			const analysis = apply_server_changes(frm, server_doc, state);
			if (state.cfg.show_applied_alert) show_applied_alert(analysis);
			return;
		}

		const analysis = analyze(frm, server_doc, state);
		analysis.server_only.forEach((fieldname) => {
			apply_field(frm, server_doc, fieldname);
			update_initial_value(state, server_doc, fieldname);
			highlight_field(frm, state, fieldname, "server");
		});

		return confirm_conflicts(analysis.conflicts, state.cfg).then((decision) => {
			if (decision === "block") {
				frappe.validated = false;
				frappe.throw("Сохранение отменено: документ был изменён на сервере.");
			}

			if (decision === "server_wins") {
				analysis.conflicts.forEach((fieldname) => {
					apply_field(frm, server_doc, fieldname);
					update_initial_value(state, server_doc, fieldname);
					highlight_field(frm, state, fieldname, "conflict");
				});
			}

			apply_modified(frm, server_doc);
			sync_matching_server_values(frm, server_doc, state);
			state.server_changed = decision !== "server_wins" && analysis.conflicts.length > 0;
			state.initial_modified = server_doc.modified;
		});
	});
}

function install(frm, opts) {
	opts = opts || {};
	if (!frm || !frm.doctype) frappe.throw("FormConflictMerge: вызовите из onload(frm)");

	const cfg = Object.assign({}, DEFAULT_CONFIG, opts);
	const state = get_state(frm);
	const first_install = !state.installed;
	const new_form_instance = state.frm !== frm;
	state.cfg = cfg;
	state.fields = get_fields(frm, cfg);
	state.installed = true;
	state.frm = frm;

	ensure_highlight_styles();
	if (first_install || !state.initial_values) refresh_initial(frm);
	import_pending_local_seeds(frm, state);
	if (first_install || new_form_instance) start_startup_warmup(frm, state);
	state.docinfo_values = snapshot_docinfo(frm, state);
	init_docinfo_self_change_markers(frm, state);
	init_listener();
	init_polling(frm, state);
	init_docinfo_polling(frm, state);

	if (window.__dinext_form_conflict_merge_doctype_hooks && window.__dinext_form_conflict_merge_doctype_hooks[frm.doctype]) {
		return;
	}

	window.__dinext_form_conflict_merge_doctype_hooks = window.__dinext_form_conflict_merge_doctype_hooks || {};
	window.__dinext_form_conflict_merge_doctype_hooks[frm.doctype] = true;

	frappe.ui.form.on(frm.doctype, {
		before_save,
		after_save(frm) {
			clear_local_seeds(frm);
			refresh_initial(frm);
		},
		refresh(frm) {
			const active = get_state(frm);
			if (!active.initial_values) refresh_initial(frm);
		},
	});
}

const FormMergeEngine = {
	analyze,
	apply_server_changes,
	before_save,
	cancel_pending_reload,
	check_server_changes,
	confirm_conflicts,
	fetch_server_doc,
	handle_doc_update,
	init_listener,
	init_polling,
	install,
};
