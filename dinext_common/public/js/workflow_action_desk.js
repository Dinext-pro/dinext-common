function can_view_workflow_action_desk() {
	return (
		frappe.session.user === "Administrator" || frappe.user.has_role("System Manager")
	);
}

function conceal_workflow_action(frm) {
	if (can_view_workflow_action_desk()) {
		return;
	}
	if (frm.layout && frm.layout.wrapper) {
		frm.layout.wrapper.hide();
	}
	const doctype = frm.doc.reference_doctype;
	const name = frm.doc.reference_name;
	if (doctype && name) {
		frappe.set_route("Form", doctype, name);
	}
}

frappe.ui.form.on("Workflow Action", {
	onload: conceal_workflow_action,
	refresh: conceal_workflow_action,
});
