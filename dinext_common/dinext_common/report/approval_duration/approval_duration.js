frappe.query_reports["Approval Duration"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: "Document Type\nApprover\nWorkflow",
			default: "Document Type",
		},
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
			options: "Completed duration\nOpen rounds",
			default: "Completed duration",
		},
	],
};
