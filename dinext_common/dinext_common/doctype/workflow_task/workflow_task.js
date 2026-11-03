// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

function can_view_workflow_task_desk() {
	return frappe.session.user === "Administrator" || frappe.user.has_role("System Manager");
}

function conceal_workflow_task(frm) {
	if (can_view_workflow_task_desk()) {
		return false;
	}
	if (frm.layout && frm.layout.wrapper) {
		frm.layout.wrapper.hide();
	}
	if (frm.doc.reference_doctype && frm.doc.reference_name && !frm.doc.source_deleted_at) {
		frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
	}
	return true;
}

frappe.ui.form.on("Workflow Task", {
	onload: conceal_workflow_task,
	refresh(frm) {
		if (conceal_workflow_task(frm)) {
			return;
		}
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
				frappe.dinext?.workflowTransitionLabel?.(transition) || __(transition.action),
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
