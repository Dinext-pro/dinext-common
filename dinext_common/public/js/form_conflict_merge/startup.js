function is_startup_warmup_active(state) {
	return Boolean(state.startup_warmup_until && Date.now() < state.startup_warmup_until);
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
	state.startup_warmup_until = 0;

	if (!state.startup_user_touched) {
		mark_clean(frm);
	}
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
		return;
	}

	state.startup_warmup_until = Date.now() + warmup_ms;
	bind_startup_user_touch_marker(frm, state);
	state.startup_warmup_timer = setTimeout(() => finish_startup_warmup(frm, state), warmup_ms);
}

function set_startup_value(frm, fieldname, value, opts) {
	if (!frm || !fieldname) return Promise.resolve();

	mark_local_seed(frm, fieldname, opts);

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
	is_startup_warmup_active,
	set_startup_value,
	start_startup_warmup,
};
