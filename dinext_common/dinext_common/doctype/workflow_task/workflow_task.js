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
		const label = (value, df) => frappe.utils.escape_html(
			frappe.dinext.approvalValueLabel(value, df?.fieldname)
		);
		for (const fieldname of ["status", "round_status", "workflow_state", "completion_source", "action", "finalization_status"]) {
			if (frm.fields_dict[fieldname]) {
				frm.set_df_property(fieldname, "formatter", label);
				frm.refresh_field(fieldname);
			}
		}
		const grid = frm.fields_dict.available_workflow_transitions?.grid;
		if (grid) {
			for (const fieldname of ["state", "action", "next_state", "policy", "allowed_role"]) {
				grid.update_docfield_property(fieldname, "formatter", label);
			}
			grid.refresh();
		}

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
	const {
		captureWorkflowForm,
		runWorkflowOperation,
		withWorkflowComment,
		workflowRequest,
		reloadWorkflowForm,
		reportWorkflowError,
	} = frappe.dinext;
	const target = captureWorkflowForm(frm);
	return withWorkflowComment(transition, async (comment) => {
		if (!target.isCurrent()) return;
		try {
			await runWorkflowOperation(frm.page, async () => {
				await workflowRequest("dinext_common.workflow_approval.api.vote", {
					task_name: target.name,
					transition_uuid: transition.transition_uuid,
					comment,
					request_id:
						window.crypto?.randomUUID?.() ||
						`${Date.now()}-${Math.random().toString(16).slice(2)}`,
				});
				if (target.isCurrent()) await reloadWorkflowForm(frm);
			});
		} catch (error) {
			reportWorkflowError(error);
		}
	});
}
