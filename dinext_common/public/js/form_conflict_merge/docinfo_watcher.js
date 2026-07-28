import { equal } from "./diff.js";
import { get_state } from "./state.js";
import { show_docinfo_alert } from "./ui.js";
import { fcm_debug, fcm_doc_label } from "./debug.js";
import { is_merge_ready, is_startup_warmup_active } from "./startup.js";

export function get_docinfo(frm) {
	if (frm.get_docinfo) return frm.get_docinfo() || {};
	const docinfo_by_doctype = frappe.model.docinfo && frappe.model.docinfo[frm.doctype];
	return (docinfo_by_doctype && docinfo_by_doctype[frm.docname]) || {};
}

export function normalize_docinfo_object(value) {
	if (Array.isArray(value)) {
		return value
			.map((item) => normalize_docinfo_object(item))
			.sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
	}

	if (value && typeof value === "object") {
		const out = {};
		Object.keys(value)
			.sort()
			.forEach((key) => {
				out[key] = normalize_docinfo_object(value[key]);
			});
		return out;
	}

	return value === undefined ? null : value;
}

export function get_docinfo_keys(cfg) {
	return Array.isArray(cfg.watch_docinfo_keys) ? cfg.watch_docinfo_keys.filter(Boolean) : [];
}

export function snapshot_docinfo(frm, state, docinfo) {
	const source = docinfo || get_docinfo(frm);
	const out = {};

	get_docinfo_keys(state.cfg).forEach((key) => {
		out[key] = normalize_docinfo_object(source[key]);
	});

	return out;
}

export function peek_changed_docinfo_keys(state, docinfo) {
	const previous = state.docinfo_values || {};
	const current = snapshot_docinfo(null, state, docinfo);
	const changed = [];

	get_docinfo_keys(state.cfg).forEach((key) => {
		if (!equal(previous[key], current[key])) changed.push(key);
	});

	return changed;
}

export function commit_docinfo_snapshot(state, docinfo) {
	state.docinfo_values = snapshot_docinfo(null, state, docinfo);
}

export function get_changed_docinfo_keys(frm, state, docinfo) {
	const changed = peek_changed_docinfo_keys(state, docinfo);
	if (changed.length) {
		commit_docinfo_snapshot(state, docinfo);
	}
	return changed;
}

export function mark_docinfo_self_change(state, keys) {
	const expires_at = Date.now() + Number(state.cfg.docinfo_self_change_suppress_ms || 0);
	if (!expires_at) return;

	state.docinfo_self_changes = state.docinfo_self_changes || {};
	keys.forEach((key) => {
		state.docinfo_self_changes[key] = expires_at;
	});
}

export function filter_self_docinfo_changes(state, changed_keys) {
	const now = Date.now();
	const self_changes = state.docinfo_self_changes || {};

	return changed_keys.filter((key) => {
		if (!self_changes[key]) return true;
		if (self_changes[key] < now) {
			delete self_changes[key];
			return true;
		}

		delete self_changes[key];
		return false;
	});
}

export function init_docinfo_self_change_markers(frm, state) {
	const watched_keys = get_docinfo_keys(state.cfg);
	if (!watched_keys.length || state.docinfo_self_change_markers_ready) return;
	state.docinfo_self_change_markers_ready = true;

	if (watched_keys.includes("assignments") && frm.assign_to && frm.assign_to.parent) {
		frm.assign_to.parent.on("click.dinext_fcm_docinfo_self_change", () => {
			mark_docinfo_self_change(state, ["assignments"]);
		});
	}

	if (watched_keys.includes("attachments") && frm.attachments && frm.attachments.parent) {
		frm.attachments.parent.on("click.dinext_fcm_docinfo_self_change", () => {
			mark_docinfo_self_change(state, ["attachments"]);
		});
	}

	if (watched_keys.includes("shared") && frm.shared && frm.shared.parent) {
		frm.shared.parent.on("click.dinext_fcm_docinfo_self_change", () => {
			mark_docinfo_self_change(state, ["shared"]);
		});
	}
}

export function fetch_docinfo(frm) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: "frappe.desk.form.load.get_docinfo",
			args: {
				doctype: frm.doctype,
				name: frm.docname,
			},
			callback(r) {
				resolve(r && r.docinfo);
			},
			error: reject,
		});
	});
}

export function refresh_watched_docinfo_blocks(frm, changed_keys) {
	if (changed_keys.includes("assignments") && frm.assign_to && frm.assign_to.refresh) {
		frm.assign_to.refresh();
	}
	if (changed_keys.includes("attachments") && frm.attachments && frm.attachments.refresh) {
		frm.attachments.refresh();
	}
	if (changed_keys.includes("shared") && frm.shared && frm.shared.refresh) {
		frm.shared.refresh();
	}
	if (changed_keys.includes("comments") && frm.timeline && frm.timeline.refresh) {
		frm.timeline.refresh();
	}
}

export function apply_docinfo_changes(frm, state, docinfo, opts) {
	opts = opts || {};
	const changed_keys = peek_changed_docinfo_keys(state, docinfo);
	if (!changed_keys.length) return [];

	commit_docinfo_snapshot(state, docinfo);

	const visible_changed_keys = filter_self_docinfo_changes(state, changed_keys);
	const silent_startup = is_startup_warmup_active(state) || !state.startup_docinfo_baseline_ready;
	if (!silent_startup) {
		state.startup_docinfo_baseline_ready = true;
	}
	if (!opts.silent && !silent_startup) {
		show_docinfo_alert(visible_changed_keys, state.cfg);
	}

	refresh_watched_docinfo_blocks(frm, changed_keys);
	fcm_debug(state, "docinfo_apply", {
		doc: fcm_doc_label(frm),
		changed_keys,
		visible_changed_keys,
		silent_startup,
		opts,
	});
	return changed_keys;
}

export function check_docinfo_changes(frm, state, opts) {
	state = state || get_state(frm);
	opts = opts || {};

	if (!get_docinfo_keys(state.cfg).length || !is_merge_ready(state)) {
		fcm_debug(state, "docinfo_poll_skipped", {
			doc: fcm_doc_label(frm),
			reason: !get_docinfo_keys(state.cfg).length ? "no_watched_keys" : "merge_not_ready",
		});
		return Promise.resolve([]);
	}

	return fetch_docinfo(frm)
		.then((docinfo) => {
			if (!docinfo) return [];
			return apply_docinfo_changes(frm, state, docinfo, opts);
		})
		.catch(() => []);
}

export function refresh_docinfo(frm, state, opts) {
	return check_docinfo_changes(frm, state, opts);
}

export function init_docinfo_polling(frm, state) {
	if (!state.cfg.refresh_docinfo_on_server_apply && !get_docinfo_keys(state.cfg).length) return;

	const interval = Number(state.cfg.poll_server_changes_interval_ms || 0);
	if (!interval || interval < 1000) return;

	if (state.docinfo_poll_timer) {
		clearInterval(state.docinfo_poll_timer);
	}

	const bound_doctype = frm.doctype;
	const bound_docname = frm.docname;

	state.docinfo_poll_timer = setInterval(() => {
		const current = cur_frm;
		if (!current || current.doctype !== bound_doctype || current.docname !== bound_docname) return;
		check_docinfo_changes(current, get_state(current));
	}, interval);
}

export const FormDocInfoWatcher = {
	apply_docinfo_changes,
	check_docinfo_changes,
	commit_docinfo_snapshot,
	fetch_docinfo,
	filter_self_docinfo_changes,
	get_changed_docinfo_keys,
	get_docinfo,
	get_docinfo_keys,
	init_docinfo_polling,
	init_docinfo_self_change_markers,
	mark_docinfo_self_change,
	normalize_docinfo_object,
	peek_changed_docinfo_keys,
	refresh_docinfo,
	refresh_watched_docinfo_blocks,
	snapshot_docinfo,
};
