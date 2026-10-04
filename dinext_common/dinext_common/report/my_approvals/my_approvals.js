frappe.query_reports["My Approvals"] = {
	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},

	onload(report) {
		if (!report.page) return;
		report.page.add_inner_button(__("Apply selected"), async () => {
			const indexes = report.datatable.rowmanager.getCheckedRows();
			const rows = indexes.map((index) => report.data[index]).filter(Boolean);
			if (!rows.length) {
				frappe.throw(__("Select at least one approval"));
			}
			const common = rows
				.map(
					(row) =>
						new Set(
							(row.available_transitions || []).map(
								(transition) => transition.action
							)
						)
				)
				.reduce(
					(result, actions) =>
						new Set([...result].filter((action) => actions.has(action)))
				);
			if (!common.size) {
				frappe.throw(__("Selected approvals have no common action"));
			}
			const dialog = new frappe.ui.Dialog({
				title: __("Apply selected approvals"),
				fields: [
					{
						fieldname: "action",
						fieldtype: "Select",
						label: __("Action"),
						options: [...common].sort().join("\n"),
						reqd: 1,
						change() {
							const action = dialog.get_value("action");
							const required = rows.some((row) =>
								row.available_transitions.some(
									(transition) =>
										transition.action === action &&
										transition.comment_is_required
								)
							);
							dialog.set_df_property("comment", "reqd", required ? 1 : 0);
						},
					},
					{
						fieldname: "comment",
						fieldtype: "Small Text",
						label: __("Comment"),
					},
				],
				primary_action_label: __("Apply"),
				async primary_action(values) {
					const items = rows.map((row) => {
						const transition = row.available_transitions.find(
							(candidate) => candidate.action === values.action
						);
						return {
							task_name: row.name,
							transition_uuid: transition.transition_uuid,
							action: values.action,
						};
					});
					dialog.disable_primary_action();
					try {
						const result = await frappe.xcall(
							"dinext_common.workflow_approval.api.bulk_task_vote",
							{
								items,
								comment: values.comment,
								request_id:
									window.crypto?.randomUUID?.() ||
									`${Date.now()}-${Math.random().toString(16).slice(2)}`,
							}
						);
						frappe.msgprint({
							title: __("Workflow result"),
							indicator: result.failed.length ? "orange" : "green",
							message: __("Succeeded: {0}; failed: {1}", [
								result.succeeded.length,
								result.failed.length,
							]),
						});
						dialog.hide();
						report.refresh();
					} finally {
						dialog.enable_primary_action();
					}
				},
			});
			dialog.show();
		});
	},
};
