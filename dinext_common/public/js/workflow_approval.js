(() => {
	const enabled = () => Boolean(frappe.boot?.enable_parallel_workflow_approval);
	const requestId = () =>
		window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;

	const applyAction = async (frm, transition, comment = "") => {
		frappe.dom.freeze(__("Applying workflow action…"));
		frm.selected_workflow_action = transition.action;
		try {
			if (!frappe.ui.form.check_mandatory(frm)) return;
			await frm.script_manager.trigger("before_workflow_action");
			await frappe.xcall("frappe.model.workflow.apply_workflow", {
				doc: frm.doc,
				action: transition.action,
				comment,
				request_id: requestId(),
			});
			await frm.reload_doc();
			await frm.script_manager.trigger("after_workflow_action");
		} finally {
			frm.selected_workflow_action = null;
			frappe.dom.unfreeze();
		}
	};

	const promptForAction = (frm, transition) => {
		if (!transition.custom_comment_is_required) {
			return applyAction(frm, transition);
		}
		const dialog = new frappe.ui.Dialog({
			title: __("Comment required for {0}", [__(transition.action)]),
			fields: [
				{
					fieldname: "comment",
					fieldtype: "Small Text",
					label: __("Comment"),
					reqd: 1,
				},
			],
			primary_action_label: __("Apply"),
			primary_action(values) {
				dialog.hide();
				applyAction(frm, transition, values.comment);
			},
		});
		dialog.show();
	};

	const patchFormActions = () => {
		if (!frappe.ui?.form?.States || frappe.ui.form.States.__dinext_approval_patched) return;
		const original = frappe.ui.form.States.prototype.show_actions;
		frappe.ui.form.States.prototype.show_actions = function () {
			if (!enabled()) return original.call(this);
			if (this.frm.doc.__unsaved === 1) return;
			frappe.workflow.get_transitions(this.frm.doc).then((transitions) => {
				this.frm.page.clear_actions_menu();
				transitions.forEach((transition) => {
					this.frm.page.add_action_item(__(transition.action), () =>
						promptForAction(this.frm, transition)
					);
				});
				this.setup_btn(transitions.length > 0);
			});
		};
		frappe.ui.form.States.__dinext_approval_patched = true;
	};

	const showBulkResult = (result) => {
		const succeeded = result.succeeded?.length || 0;
		const failures = (result.failed || [])
			.map(
				(row) =>
					`<li><strong>${frappe.utils.escape_html(row.name)}</strong>: ${frappe.utils.escape_html(
						row.error
					)}</li>`
			)
			.join("");
		frappe.msgprint({
			title: __("Workflow result"),
			indicator: failures ? "orange" : "green",
			message: `<p>${__("Succeeded")}: ${succeeded}</p>${
				failures ? `<p>${__("Failed")}:</p><ul>${failures}</ul>` : ""
			}`,
		});
	};

	const patchBulkActions = () => {
		const ListView = frappe.views?.ListView;
		if (!ListView || ListView.__dinext_approval_patched) return;
		const original = ListView.prototype.get_workflow_action_menu_items;
		ListView.prototype.get_workflow_action_menu_items = function () {
			if (!enabled() || !frappe.model.has_workflow(this.doctype)) {
				return original.call(this);
			}
			return frappe.workflow.get_all_transition_actions(this.doctype).map((action) => ({
				label: __(action),
				name: action,
				is_workflow_action: true,
				action: () => {
					const selected = this.get_checked_items(true);
					frappe.prompt(
						[
							{
								fieldname: "comment",
								fieldtype: "Small Text",
								label: __("Comment"),
							},
						],
						async (values) => {
							this.disable_list_update = true;
							try {
								const result = await frappe.xcall(
									"frappe.model.workflow.bulk_workflow_approval",
									{
										docnames: selected,
										doctype: this.doctype,
										action,
										comment: values.comment,
										request_id: requestId(),
									}
								);
								if (result) {
									showBulkResult(result);
								} else {
									frappe.show_alert({
										message: __("Workflow operation accepted"),
										indicator: "green",
									});
								}
								this.refresh();
							} finally {
								this.disable_list_update = false;
							}
						},
						__("Apply {0}", [__(action)]),
						__("Apply")
					);
				},
			}));
		};
		ListView.__dinext_approval_patched = true;
	};

	const pendingRegistered = new Set();
	const registerPendingApprovers = () => {
		if (!enabled()) return;
		const doctypes = new Set([
			...Object.keys(frappe.workflow?.workflows || {}),
			"User Timesheet",
			"Application For Leave",
		]);
		doctypes.forEach((doctype) => {
			if (pendingRegistered.has(doctype)) return;
			pendingRegistered.add(doctype);
			frappe.ui.form.on(doctype, {
				async refresh(frm) {
					if (frm.is_new()) return;
					const selector = ".dinext-pending-approvers";
					frm.dashboard.wrapper.find(selector).remove();
					const rows = await frappe
						.xcall("dinext_common.workflow_approval.api.get_pending_approvers", {
							doctype: frm.doctype,
							name: frm.doc.name,
						})
						.catch(() => []);
					if (!rows.length) return;
					const users = [
						...new Set(rows.map((row) => row.approver_name || row.approver)),
					].sort();
					const content = users
						.map((user) => frappe.utils.escape_html(user))
						.join(", ");
					frm.dashboard.wrapper.prepend(
						`<div class="form-dashboard-section dinext-pending-approvers">
							<div class="section-head">${__("Pending approvers")}</div>
							<div class="section-body">${content}</div>
						</div>`
					);
				},
			});
		});
	};

	frappe.ready(() => {
		patchFormActions();
		patchBulkActions();
		registerPendingApprovers();
		frappe.router.on("change", registerPendingApprovers);
	});
})();
