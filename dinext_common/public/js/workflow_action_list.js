function can_view_workflow_action_desk() {
	return (
		frappe.session.user === "Administrator" || frappe.user.has_role("System Manager")
	);
}

function workflow_action_form_link(doc) {
	let doctype = "Workflow Action";
	let docname = doc.name;
	if (doc.status === "Open") {
		doctype = doc.reference_doctype;
		docname = doc.reference_name;
	}
	if (!docname) {
		return `/app/${frappe.router.slug("Workflow Action")}/${encodeURIComponent(doc.name)}`;
	}
	docname = docname.match(/[%'"]/) ? encodeURIComponent(docname) : docname;
	return `/app/${frappe.router.slug(doctype)}/${docname}`;
}

frappe.listview_settings["Workflow Action"] = {
	get_form_link: workflow_action_form_link,

	onload(listview) {
		if (can_view_workflow_action_desk()) {
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
};
