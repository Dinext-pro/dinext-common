frappe.query_reports["Approval Load"] = {
	filters: [
		{
			fieldname: "workflow",
			label: __("Workflow"),
			fieldtype: "Data",
		},
		{
			fieldname: "reference_doctype",
			label: __("Document Type"),
			fieldtype: "Data",
		},
		{
			fieldname: "chart",
			label: __("Chart"),
			fieldtype: "Select",
			options: "Open count\nOpen age",
			default: "Open count",
		},
	],
};
