// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

frappe.ui.form.on("Workflow Task", {
	refresh(frm) {
		if (frm.doc.reference_doctype && frm.doc.reference_name && !frm.doc.source_deleted_at) {
			frm.add_custom_button(__("Open source document"), () => {
				frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
			});
		}
		if (
			frm.doc.status !== "Working" ||
			frm.doc.round_status !== "Open" ||
			frm.doc.approver !== frappe.session.user
		) {
			return;
		}
		(frm.doc.available_workflow_transitions || []).forEach((transition) => {
			frm.add_custom_button(
				__(transition.action),
				() => vote(frm, transition),
				__("Workflow")
			);
		});
	},
});

function vote(frm, transition) {
	const submit = async (comment = "") => {
		await frappe.xcall("dinext_common.workflow_approval.api.vote", {
			task_name: frm.doc.name,
			transition_uuid: transition.transition_uuid,
			comment,
			request_id:
				window.crypto?.randomUUID?.() ||
				`${Date.now()}-${Math.random().toString(16).slice(2)}`,
		});
		await frm.reload_doc();
	};
	if (!transition.comment_is_required) {
		return submit();
	}
	frappe.prompt(
		[
			{
				fieldname: "comment",
				fieldtype: "Small Text",
				label: __("Comment"),
				reqd: 1,
			},
		],
		(values) => submit(values.comment),
		__("Comment required for {0}", [__(transition.action)]),
		__("Apply")
	);
}
