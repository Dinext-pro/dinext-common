function is_startup_warmup_active(state) {
	return Boolean(state.startup_warmup_until && Date.now() < state.startup_warmup_until);
}

function is_merge_ready(state) {
	if (!state || !state.installed) return false;
	if (Number(state.cfg.startup_warmup_ms || 0) > 0 && !state.startup_baseline_ready) return false;
	return true;
}

function get_form_wrapper(frm) {
	if (!frm.wrapper) return null;
	return frm.wrapper.on ? frm.wrapper : $(frm.wrapper);
}

function bind_startup_user_touch_marker(frm, state) {
	const $wrapper = get_form_wrapper(frm);
	if (!$wrapper || !$wrapper.on || state.startup_user_touch_marker_ready) return;
	state.startup_user_touch_marker_ready = true;

	$wrapper.on(
		"focusin.dinext_fcm_startup_touch input.dinext_fcm_startup_touch change.dinext_fcm_startup_touch keydown.dinext_fcm_startup_touch",
		(event) => {
			const original_event = event && event.originalEvent;
			if (!original_event || original_event.isTrusted === false) return;
			if (is_startup_warmup_active(state)) state.startup_user_touched = true;
		}
	);
}

function finish_startup_warmup(frm, state) {
	const current = cur_frm;
	if (!current || current.doctype !== frm.doctype || current.docname !== frm.docname) return;

	refresh_initial(frm);
	state.docinfo_values = snapshot_docinfo(frm, state);
	state.startup_docinfo_baseline_ready = true;
	state.startup_baseline_ready = true;
	state.startup_warmup_until = 0;

	if (!state.startup_user_touched) {
		mark_clean(frm);
	}

	fcm_debug(state, "warmup_finish", {
		doc: fcm_doc_label(frm),
		startup_user_touched: state.startup_user_touched,
	});
	fcm_debug_state_snapshot(state, frm, "warmup_finish_snapshot");
	fcm_debug_local_drift(state, frm, "warmup_finish_drift");

	start_deferred_services(frm, state);
}

function start_startup_warmup(frm, state) {
	const warmup_ms = Number(state.cfg.startup_warmup_ms || 0);
	state.startup_user_touched = false;
	state.startup_docinfo_baseline_ready = false;

	if (state.startup_warmup_timer) {
		clearTimeout(state.startup_warmup_timer);
		state.startup_warmup_timer = null;
	}

	if (!warmup_ms) {
		state.startup_warmup_until = 0;
		state.startup_docinfo_baseline_ready = true;
		state.startup_baseline_ready = true;
		if (!state.initial_values) refresh_initial(frm);
		start_deferred_services(frm, state);
		return;
	}

	state.startup_baseline_ready = false;

	state.startup_warmup_until = Date.now() + warmup_ms;
	bind_startup_user_touch_marker(frm, state);
	fcm_debug(state, "warmup_start", {
		doc: fcm_doc_label(frm),
		warmup_ms,
		until: new Date(state.startup_warmup_until).toISOString(),
	});
	state.startup_warmup_timer = setTimeout(() => finish_startup_warmup(frm, state), warmup_ms);
}

function set_startup_value(frm, fieldname, value, opts) {
	if (!frm || !fieldname) return Promise.resolve();

	mark_local_seed(frm, fieldname, opts);

	fcm_debug(get_state(frm), "startup_value_set", {
		doc: fcm_doc_label(frm),
		fieldname,
		value: summarize_field_value(value),
		opts,
	});

	const set_value = frappe.model.set_value(
		frm.doctype,
		frm.docname,
		fieldname,
		value,
		null,
		true
	);

	return Promise.resolve(set_value).then(() => {
		frm.refresh_field(fieldname);
		return value;
	});
}

const apply_local_seed = set_startup_value;

const FormStartup = {
	apply_local_seed,
	bind_startup_user_touch_marker,
	finish_startup_warmup,
	get_form_wrapper,
	is_merge_ready,
	is_startup_warmup_active,
	set_startup_value,
	start_startup_warmup,
};
