function can_view_workflow_task_desk() {
	return frappe.session.user === "Administrator" || frappe.user.has_role("System Manager");
}

frappe.listview_settings["Workflow Task"] = {
	add_fields: ["reference_doctype", "reference_name", "source_deleted_at", "source_title"],

	onload(listview) {
		if (can_view_workflow_task_desk()) {
			return;
		}
		listview.get_count_str = () => Promise.resolve(__("0"));
		listview.refresh = () => {
			listview.data = [];
			listview.toggle_result_area();
			listview.before_render();
			listview.render();
			listview.after_render();
			listview.freeze(false);
			return Promise.resolve();
		};
	},

	get_form_link(doc) {
		if (doc.source_deleted_at || !doc.reference_doctype || !doc.reference_name) {
			return frappe.utils.get_form_link("Workflow Task", doc.name);
		}
		return frappe.utils.get_form_link(doc.reference_doctype, doc.reference_name);
	},
};
