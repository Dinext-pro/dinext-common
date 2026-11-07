frappe.query_reports["My Approval History"] = {
	formatter(...args) { return frappe.dinext.approvalReportFormatter(...args); },
	onload(report) {
		const filter = report.get_filter("completion_source");
		if (!filter) return;
		const selected = filter.get_value();
		const options = typeof filter.df.options === "string"
			? filter.df.options.split("\n") : filter.df.options;
		filter.df.context = "Approval completion source";
		filter.df.options = options.map((option) => {
			const value = typeof option === "string" ? option : option.value;
			return {value, label: __(value, null, filter.df.context)};
		});
		filter.refresh();
		filter.set_input(selected);
	},
};
