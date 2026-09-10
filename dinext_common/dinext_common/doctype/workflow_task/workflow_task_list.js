frappe.listview_settings["Workflow Task"] = {
	add_fields: [
		"reference_doctype",
		"reference_name",
		"source_deleted_at",
		"source_title",
	],

	get_form_link(doc) {
		if (doc.source_deleted_at || !doc.reference_doctype || !doc.reference_name) {
			return frappe.utils.get_form_link("Workflow Task", doc.name);
		}
		return frappe.utils.get_form_link(doc.reference_doctype, doc.reference_name);
	},
};
