function cancel_deferred_services(state) {
	if (!state) return;
	if (state.poll_timer) {
		clearInterval(state.poll_timer);
		state.poll_timer = null;
	}
	if (state.docinfo_poll_timer) {
		clearInterval(state.docinfo_poll_timer);
		state.docinfo_poll_timer = null;
	}
	if (state.startup_warmup_timer) {
		clearTimeout(state.startup_warmup_timer);
		state.startup_warmup_timer = null;
	}
	state.pollers_ready = false;
}

function cancel_bound_pollers(frm, except_key) {
	Object.keys(registry).forEach((key) => {
		if (key === except_key) return;
		const bound = registry[key];
		if (!bound || bound.frm !== frm) return;
		fcm_debug(bound, "cancel_bound_pollers", {
			doc: fcm_doc_label(frm),
			cancelled_key: key,
			active_key: except_key,
			highlighted_fields: Object.keys(bound.highlighted_fields || {}),
		});
		clear_highlights(frm, bound);
		cancel_deferred_services(bound);
		bump_sync_generation(bound);
	});
}

function cancel_pending_reload(frm) {
	if (frm.debounced_reload_doc && frm.debounced_reload_doc.cancel) {
		frm.debounced_reload_doc.cancel();
	}
}

function apply_server_changes(frm, server_doc, state, opts) {
	opts = opts || {};
	if (frm && frm.__dinext_fcm_resyncing) return { server_only: [], local_only: [], conflicts: [], applied_server: [], applied_conflicts: [] };

	const silent_startup = opts.silent || is_startup_warmup_active(state);
	const modified_changed = Boolean(server_doc && server_doc.modified && server_doc.modified !== state.initial_modified);
	const form_control_changes = detect_form_control_changes(frm, server_doc, state);
	const analysis = analyze(frm, server_doc, state);
	const applied_server = analysis.server_only.slice();
	const applied_conflicts = state.cfg.conflict_policy === "server_wins" ? analysis.conflicts.slice() : [];

	fcm_debug_analysis(state, frm, analysis, {
		source: opts.source || "apply_server_changes",
		server_snapshot: snapshot(server_doc, state.fields),
		silent_startup,
		modified_changed,
		server_modified: server_doc && server_doc.modified,
		server_modified_by: server_doc && server_doc.modified_by,
	});

	applied_server.forEach((fieldname) => {
		apply_field(frm, server_doc, fieldname, state);
		update_initial_value(state, server_doc, fieldname, frm);
	});

	applied_conflicts.forEach((fieldname) => {
		apply_field(frm, server_doc, fieldname, state);
		update_initial_value(state, server_doc, fieldname, frm);
	});

	applied_server.forEach((fieldname) => {
		apply_field_highlight(frm, state, fieldname, "server", analysis, silent_startup);
	});

	applied_conflicts.forEach((fieldname) => {
		apply_field_highlight(frm, state, fieldname, "conflict", analysis, silent_startup);
	});

	apply_modified(frm, server_doc);
	sync_matching_server_values(frm, server_doc, state);

	analysis.applied_server = applied_server;
	analysis.applied_conflicts = applied_conflicts;
	analysis.remaining_local = get_remaining_local_changes(frm, state);
	analysis.modified_changed = modified_changed;
	analysis.server_modified_by = server_doc.modified_by;

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

	if (form_control_changes.length) {
		resync_form_after_server_apply(frm, server_doc, state, form_control_changes);
	}

	fcm_debug(state, "apply_server_changes_done", {
		doc: fcm_doc_label(frm),
		source: opts.source || "apply_server_changes",
		applied_server,
		applied_conflicts,
		remaining_local: analysis.remaining_local,
		silent_startup,
	});

	return analysis;
}

function handle_doc_update(data) {
	const frm = cur_frm;
	if (!frm || !frm.doc || frm.is_new() || !data) return;
	if (frm.__dinext_fcm_resyncing) return;
	if (data.doctype !== frm.doctype || data.name !== frm.docname) return;
	if (frappe.ui.form.is_saving) return;
	if (data.modified && data.modified === frm.doc.modified) return;

	const state = get_state(frm);
	if (!state.installed) return;

	if (!is_merge_ready(state)) {
		fcm_debug(state, "doc_update_skipped", {
			doc: fcm_doc_label(frm),
			reason: "merge_not_ready",
			data,
			frm_modified: frm.doc.modified,
			initial_modified: state.initial_modified,
		});
		return;
	}

	fcm_debug(state, "doc_update", {
		doc: fcm_doc_label(frm),
		data,
		frm_modified: frm.doc.modified,
		initial_modified: state.initial_modified,
	});

	cancel_pending_reload(frm);

	state.server_changed = true;
	state.server_modified = data.modified;
	state.server_modified_by = data.modified_by;

	const silent_startup = is_startup_warmup_active(state);
	if (state.cfg.show_realtime_alert && !silent_startup) {
		show_realtime_alert(data, frm, state.cfg);
	}

	if (state.cfg.apply_server_changes_on_realtime) {
		const generation = state.sync_generation;
		const bound_docname = frm.docname;
		fetch_server_doc(frm).then((server_doc) => {
			if (is_sync_stale(state, generation, frm) || frm.docname !== bound_docname) {
				fcm_debug(state, "doc_update_stale", {
					doc: fcm_doc_label(frm),
					bound_docname,
					current_docname: frm.docname,
					generation,
					sync_generation: state.sync_generation,
				});
				return;
			}
			if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) {
				fcm_debug(state, "doc_update_fetch_skipped", {
					doc: fcm_doc_label(frm),
					reason: !server_doc
						? "no_server_doc"
						: !server_doc.modified
							? "no_server_modified"
							: "modified_unchanged",
					server_modified: server_doc && server_doc.modified,
					initial_modified: state.initial_modified,
				});
				return;
			}
			fcm_debug_child_tables(state, frm, "doc_update_child_tables_before_apply", server_doc, {
				source: "doc_update",
			});
			const analysis = apply_server_changes(frm, server_doc, state, {
				silent: silent_startup,
				source: "doc_update",
			});
			if (state.cfg.show_applied_alert && !silent_startup) {
				show_applied_alert(frm, analysis, state.cfg);
			}
		});
	}
}

function init_listener() {
	if (window.__dinext_form_conflict_merge_listener_ready) return;
	window.__dinext_form_conflict_merge_listener_ready = true;
	frappe.realtime.on("doc_update", handle_doc_update);
}

function check_server_changes(frm) {
	if (!frm || !frm.doc || frm.is_new()) return Promise.resolve();
	if (frm.__dinext_fcm_resyncing) return Promise.resolve();
	const state = get_state(frm);
	if (!state.installed) return Promise.resolve();

	if (!is_merge_ready(state)) {
		fcm_debug(state, "poll_skipped", {
			doc: fcm_doc_label(frm),
			reason: "merge_not_ready",
			startup_baseline_ready: state.startup_baseline_ready,
			startup_warmup_active: is_startup_warmup_active(state),
		});
		return Promise.resolve();
	}

	if (state.initial_modified && frm.doc.modified && state.initial_modified !== frm.doc.modified) {
		fcm_debug(
			state,
			"poll_baseline_mismatch",
			{
				doc: fcm_doc_label(frm),
				initial_modified: state.initial_modified,
				frm_modified: frm.doc.modified,
			},
			FCM_LOG_LEVELS.warn
		);
	}

	fcm_debug_local_drift(state, frm, "poll_local_drift");

	const generation = state.sync_generation;
	const bound_docname = frm.docname;

	return fetch_server_doc(frm).then((server_doc) => {
		if (is_sync_stale(state, generation, frm) || frm.docname !== bound_docname) {
			fcm_debug(state, "poll_stale", {
				doc: fcm_doc_label(frm),
				bound_docname,
				current_docname: frm.docname,
				generation,
				sync_generation: state.sync_generation,
			});
			return;
		}
		if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) {
			fcm_debug(state, "poll_noop", {
				doc: fcm_doc_label(frm),
				reason: !server_doc
					? "no_server_doc"
					: !server_doc.modified
						? "no_server_modified"
						: "modified_unchanged",
				server_modified: server_doc && server_doc.modified,
				initial_modified: state.initial_modified,
				frm_modified: frm.doc.modified,
			});
			return;
		}

		fcm_debug(state, "poll_detected_change", {
			doc: fcm_doc_label(frm),
			server_modified: server_doc.modified,
			initial_modified: state.initial_modified,
			frm_modified: frm.doc.modified,
			server_modified_by: server_doc.modified_by,
		});
		fcm_debug_child_tables(state, frm, "poll_child_tables_before_apply", server_doc, {
			source: "poll",
		});

		const silent_startup = is_startup_warmup_active(state);
		const analysis = apply_server_changes(frm, server_doc, state, {
			silent: silent_startup,
			source: "poll",
		});
		if (state.cfg.show_applied_alert && !silent_startup) {
			show_applied_alert(frm, analysis, state.cfg);
		}
		return analysis;
	});
}

function init_polling(frm, state) {
	const interval = Number(state.cfg.poll_server_changes_interval_ms || 0);
	if (!interval || interval < 1000) return;

	if (state.poll_timer) {
		clearInterval(state.poll_timer);
	}

	const bound_doctype = frm.doctype;
	const bound_docname = frm.docname;

	state.poll_timer = setInterval(() => {
		const current = cur_frm;
		if (!current || current.doctype !== bound_doctype || current.docname !== bound_docname) return;
		check_server_changes(current);
	}, interval);
}

function confirm_conflicts(frm, conflicts, cfg) {
	if (!conflicts.length) return Promise.resolve("continue");
	if (cfg.conflict_policy === "local_wins") return Promise.resolve("local_wins");
	if (cfg.conflict_policy === "server_wins") return Promise.resolve("server_wins");
	if (cfg.conflict_policy === "block") return Promise.resolve("block");

	return new Promise((resolve) => {
		const conflict_labels = format_field_labels(frm, conflicts).join(", ");
		const message = [
			__("The document was modified on the server and some fields conflict with your edits."),
			"",
			__("Conflicting fields: {0}", [conflict_labels]),
			"",
			__("Choose how to continue saving."),
		].join("<br>");

		const dialog = new frappe.ui.Dialog({
			title: __("Change Conflict"),
			fields: [{ fieldtype: "HTML", fieldname: "message", options: message }],
			primary_action_label: __("Keep my values"),
			primary_action() {
				dialog.hide();
				resolve("local_wins");
			},
			secondary_action_label: __("Use server values"),
			secondary_action() {
				dialog.hide();
				resolve("server_wins");
			},
		});

		dialog.$wrapper.find(".modal-footer").prepend(
			$(`<button class="btn btn-default btn-sm">${__("Cancel save")}</button>`).on("click", () => {
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

	fcm_debug_child_tables(state, frm, "before_save_local", null, {
		frm_modified: frm.doc.modified,
		initial_modified: state.initial_modified,
		frm_unsaved: frm.doc.__unsaved,
	});

	return fetch_server_doc(frm).then((server_doc) => {
		if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) {
			fcm_debug(state, "before_save_noop", {
				doc: fcm_doc_label(frm),
				reason: !server_doc
					? "no_server_doc"
					: !server_doc.modified
						? "no_server_modified"
						: "modified_unchanged",
				server_modified: server_doc && server_doc.modified,
				initial_modified: state.initial_modified,
				frm_modified: frm.doc.modified,
			});
			return;
		}

		fcm_debug_child_tables(state, frm, "before_save_server", server_doc, {
			server_modified: server_doc.modified,
			initial_modified: state.initial_modified,
			conflict_policy: state.cfg.conflict_policy,
		});

		if (state.cfg.conflict_policy === "server_wins") {
			const analysis = apply_server_changes(frm, server_doc, state);
			if (state.cfg.show_applied_alert) show_applied_alert(frm, analysis, state.cfg);
			return;
		}

		const analysis = analyze(frm, server_doc, state);
		analysis.server_modified_by = server_doc.modified_by;
		analysis.server_only.forEach((fieldname) => {
			apply_field(frm, server_doc, fieldname, state);
			update_initial_value(state, server_doc, fieldname, frm);
			apply_field_highlight(frm, state, fieldname, "server", analysis, false);
		});

		return confirm_conflicts(frm, analysis.conflicts, state.cfg).then((decision) => {
			if (decision === "block") {
				frappe.validated = false;
				frappe.throw(__("Save cancelled: the document was modified on the server."));
			}

			if (decision === "server_wins") {
				analysis.conflicts.forEach((fieldname) => {
					apply_field(frm, server_doc, fieldname, state);
					update_initial_value(state, server_doc, fieldname, frm);
					apply_field_highlight(frm, state, fieldname, "conflict", analysis, false);
				});
			}

			apply_modified(frm, server_doc);
			sync_matching_server_values(frm, server_doc, state);
			state.server_changed = decision !== "server_wins" && analysis.conflicts.length > 0;
			state.initial_modified = server_doc.modified;
		});
	});
}

function start_deferred_services(frm, state) {
	if (state.pollers_ready) return;
	state.pollers_ready = true;
	fcm_debug(state, "pollers_start", {
		doc: fcm_doc_label(frm),
		poll_ms: state.cfg.poll_server_changes_interval_ms,
		watch_docinfo_keys: state.cfg.watch_docinfo_keys,
	});
	init_polling(frm, state);
	init_docinfo_polling(frm, state);
}

function install(frm, opts) {
	opts = opts || {};
	if (!frm || !frm.doctype) frappe.throw("FormConflictMerge: call from onload(frm)");

	const cfg = Object.assign({}, DEFAULT_CONFIG, opts);
	const state_key = `${frm.doctype}::${frm.docname}`;
	cancel_bound_pollers(frm, state_key);
	const state = get_state(frm);
	clear_all_fcm_highlights(frm, state);
	const first_install = !state.installed;
	const new_form_instance = state.frm !== frm;
	state.cfg = cfg;
	state.fields = get_fields(frm, cfg);
	state.installed = true;
	state.frm = frm;
	state.doc_key = state_key;
	bump_sync_generation(state);

	if (new_form_instance) {
		cancel_deferred_services(state);
	}

	ensure_highlight_styles();
	const warmup_enabled = Number(cfg.startup_warmup_ms || 0) > 0;
	if (!warmup_enabled && (first_install || !state.initial_values)) {
		refresh_initial(frm);
		state.startup_baseline_ready = true;
	} else if (warmup_enabled && (first_install || new_form_instance)) {
		state.startup_baseline_ready = false;
	}
	import_pending_local_seeds(frm, state);
	if (first_install || new_form_instance) start_startup_warmup(frm, state);
	else if (!state.pollers_ready && is_merge_ready(state)) start_deferred_services(frm, state);
	state.docinfo_values = snapshot_docinfo(frm, state);
	init_docinfo_self_change_markers(frm, state);
	init_listener();

	fcm_debug(state, "install", {
		doc: fcm_doc_label(frm),
		first_install,
		new_form_instance,
		warmup_enabled,
		startup_baseline_ready: state.startup_baseline_ready,
		debug_enabled: is_fcm_debug_enabled(state),
		tracked_fields: state.fields.length,
		child_tables: state.fields.filter((fieldname) => is_child_table_field(frm, fieldname)),
		cfg: {
			conflict_policy: cfg.conflict_policy,
			poll_server_changes_interval_ms: cfg.poll_server_changes_interval_ms,
			startup_warmup_ms: cfg.startup_warmup_ms,
			watch_docinfo_keys: cfg.watch_docinfo_keys,
			debug_log: cfg.debug_log,
		},
	});

	if (is_fcm_debug_enabled(state)) {
		console.info(
			`${FCM_LOG_PREFIX} debug ON for ${fcm_doc_label(frm)}. Console filter: FCM. Events: install, warmup_*, refresh_initial, poll_*, analyze, child_tables, apply_child_table, before_save_*, sync_matching_baseline, highlight, highlight_child_table, local_drift, form_resync_*. dump: dinext_common.formConflictMerge.dump_debug_state()`
		);
		fcm_debug_state_snapshot(state, frm, "install_snapshot");
	}

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
			if (!active.initial_values && is_merge_ready(active)) refresh_initial(frm);
		},
	});
}

const FormMergeEngine = {
	analyze,
	apply_server_changes,
	before_save,
	cancel_deferred_services,
	cancel_pending_reload,
	check_server_changes,
	confirm_conflicts,
	fetch_server_doc,
	handle_doc_update,
	init_listener,
	init_polling,
	install,
	start_deferred_services,
};
