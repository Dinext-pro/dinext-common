frappe.query_reports["Approval Monitoring"] = {
	formatter(...args) { return frappe.dinext.approvalReportFormatter(...args); },
};
