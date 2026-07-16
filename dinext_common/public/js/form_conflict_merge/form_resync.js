import { clone_raw_value, equal } from "./diff.js";
import { fcm_debug, fcm_doc_label, FCM_LOG_LEVELS } from "./debug.js";
import { cancel_pending_reload } from "./merge_engine.js";

export function get_form_resync_fieldnames(frm, cfg) {
	if (!frm || !cfg || cfg.form_resync_on_server_apply === false) return [];

	const fields = new Set(cfg.form_resync_fields || []);
	fields.add("docstatus");

	if (frappe.workflow && frappe.workflow.get_state_fieldname) {
		const workflow_field = frappe.workflow.get_state_fieldname(frm.doctype);
		if (workflow_field) fields.add(workflow_field);
	}

	return Array.from(fields);
}

export function detect_form_control_changes(frm, server_doc, state) {
	const fieldnames = get_form_resync_fieldnames(frm, state.cfg);
	if (!fieldnames.length || !server_doc) return [];

	return fieldnames.filter((fieldname) => {
		if (server_doc[fieldname] === undefined) return false;
		return !equal(frm.doc[fieldname], server_doc[fieldname]);
	});
}

export function sync_form_control_fields(frm, server_doc, fieldnames) {
	(fieldnames || []).forEach((fieldname) => {
		if (!server_doc || server_doc[fieldname] === undefined) return;
		frm.doc[fieldname] = clone_raw_value(server_doc[fieldname]);
		const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
		if (local_doc) local_doc[fieldname] = frm.doc[fieldname];
	});
}

export function resync_form_after_server_apply(frm, server_doc, state, changed_fields) {
	if (!frm || frm.is_new() || frm.__dinext_fcm_resyncing) return false;
	if (!changed_fields || !changed_fields.length) return false;
	if (state.cfg.form_resync_on_server_apply === false) return false;

	const resync_fields = get_form_resync_fieldnames(frm, state.cfg);
	sync_form_control_fields(frm, server_doc, resync_fields);

	frm.__dinext_fcm_resyncing = true;
	fcm_debug(
		state,
		"form_resync_start",
		{
			doc: fcm_doc_label(frm),
			changed_fields,
			resync_fields,
		},
		FCM_LOG_LEVELS.warn
	);

	try {
		cancel_pending_reload(frm);
		frm.refresh();
	} finally {
		frm.__dinext_fcm_resyncing = false;
	}

	fcm_debug(
		state,
		"form_resync_done",
		{
			doc: fcm_doc_label(frm),
			read_only: frm.read_only,
			docstatus: frm.doc.docstatus,
		},
		FCM_LOG_LEVELS.warn
	);
	return true;
}

export const FormResync = {
	detect_form_control_changes,
	get_form_resync_fieldnames,
	resync_form_after_server_apply,
	sync_form_control_fields,
};
