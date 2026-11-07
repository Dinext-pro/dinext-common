frappe.query_reports["My Approval History"] = {
	formatter(...args) { return frappe.dinext.approvalReportFormatter(...args); },
};
