frappe.query_reports["My Approval History"] = {
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "reference_name" && data?.source_deleted_at) {
			return frappe.utils.escape_html(value || "");
		}
		return default_formatter(value, row, column, data);
	},
};
