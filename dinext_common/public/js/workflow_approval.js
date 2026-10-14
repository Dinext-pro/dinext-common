(() => {
	const enabled = () => Boolean(frappe.boot?.enable_parallel_workflow_approval);
	const requestId = () =>
		window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;

	const knownIcon = (name) => {
		const icon = String(name || "").trim();
		if (!/^[A-Za-z0-9-]+$/.test(icon) || typeof document === "undefined") return "";
		const id = icon.startsWith("es-") ? icon : `icon-${icon}`;
		return document.getElementById(id) ? icon : "";
	};

	const workflowActionLabel = (action, text) => {
		const plain = text == null ? __(action) : text;
		const safe = frappe.utils.escape_html(String(plain));
		const icon = knownIcon(frappe.boot?.workflow_action_icons?.[action]);
		if (!icon || typeof frappe.utils.icon !== "function") return safe;
		return `${frappe.utils.icon(icon)} ${safe}`;
	};

	frappe.dinext = frappe.dinext || {};
	frappe.dinext.workflowActionLabel = workflowActionLabel;

	const transitionLabel = (transition, transitions) => {
		const sameAction = (transitions || []).filter((row) => row.action === transition.action);
		let text = __(transition.action);
		if (sameAction.length >= 2) {
			const role = transition.allowed || transition.allowed_role || "";
			const next = transition.next_state || "";
			const suffix = [role, next].filter(Boolean).map((value) => __(value)).join(" → ");
			if (suffix) text = `${__(transition.action)} (${suffix})`;
		}
		return workflowActionLabel(transition.action, text);
	};

	const applyAction = async (frm, transition, comment = "") => {
		frappe.dom.freeze(__("Applying workflow action…"));
		frm.selected_workflow_action = transition.action;
		try {
			if (!frappe.ui.form.check_mandatory(frm)) return;
			await frm.script_manager.trigger("before_workflow_action");
			await frappe.xcall("frappe.model.workflow.apply_workflow", {
				doc: frm.doc,
				action: transition.action,
				transition_uuid: transition.custom_transition_uuid,
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

	const showStandardActions = function () {
		if (this.frm.doc.__unsaved === 1) return;
		const me = this;
		const hasApprovalAccess = (transition) => {
			const user = frappe.session.user;
			return (
				user === "Administrator" ||
				transition.allow_self_approval ||
				user !== me.frm.doc.owner
			);
		};
		frappe.workflow.get_transitions(this.frm.doc).then((transitions) => {
			this.frm.page.clear_actions_menu();
			let added = false;
			transitions.forEach((transition) => {
				if (!frappe.user_roles.includes(transition.allowed) || !hasApprovalAccess(transition)) {
					return;
				}
				added = true;
				me.frm.page.add_action_item(workflowActionLabel(transition.action), () => {
					frappe.dom.freeze();
					me.frm.selected_workflow_action = transition.action;
					if (!frappe.ui.form.check_mandatory(me.frm)) return frappe.dom.unfreeze();
					me.frm.script_manager.trigger("before_workflow_action").then(() => {
						frappe
							.xcall("frappe.model.workflow.apply_workflow", {
								doc: me.frm.doc,
								action: transition.action,
							})
							.then((doc) => {
								frappe.model.sync(doc);
								me.frm.refresh();
								me.frm.selected_workflow_action = null;
								me.frm.script_manager.trigger("after_workflow_action");
							})
							.finally(() => {
								frappe.dom.unfreeze();
							});
					});
				});
			});
			this.setup_btn(added);
		});
	};

	const patchFormActions = () => {
		if (!frappe.ui?.form?.States || frappe.ui.form.States.__dinext_approval_patched) return;
		frappe.ui.form.States.prototype.show_actions = function () {
			if (!enabled()) return showStandardActions.call(this);
			if (this.frm.doc.__unsaved === 1) return;
			frappe.workflow.get_transitions(this.frm.doc).then((transitions) => {
				this.frm.page.clear_actions_menu();
				transitions.forEach((transition) => {
					this.frm.page.add_action_item(transitionLabel(transition, transitions), () =>
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
			if (!frappe.model.has_workflow(this.doctype)) {
				return original.call(this);
			}
			if (!enabled()) {
				return (original.call(this) || []).map((item) => ({
					...item,
					label: workflowActionLabel(item.name, item.label),
				}));
			}
			const transitions = frappe.workflow.get_all_transitions(this.doctype) || [];
			return transitions.map((transition) => ({
				label: transitionLabel(transition, transitions),
				name: transition.custom_transition_uuid || transition.action,
				is_workflow_action: true,
				action: () => {
					const selected = this.get_checked_items(true);
					const action = transition.action;
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
										transition_uuid: transition.custom_transition_uuid,
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
	const paintApprovalBanner = async (frm) => {
		if (!frm || frm.is_new() || !frm.dashboard?.parent) return;
		const requested = frm.doc.name;
		frm.dashboard.parent.find(".dinext-pending-approvers").remove();
		let banner;
		try {
			banner = await frappe.xcall(
				"dinext_common.workflow_approval.api.get_form_approval_banner",
				{ doctype: frm.doctype, name: requested }
			);
		} catch (error) {
			console.error(error);
			frappe.show_alert({
				message: __("Could not load approval status"),
				indicator: "red",
			});
			return;
		}
		if (!banner || frm.doc?.name !== requested) return;
		const stalled = banner.round_status === "Conflicted" || banner.round_status === "Stalled";
		const pending = banner.pending_approvers || [];
		if (!stalled && !pending.length) return;
		const title = stalled
			? __("Approval round needs a rebuild")
			: __("Pending approvers");
		const names = [
			...new Set(pending.map((row) => row.approver_name || row.approver)),
		].sort();
		const body = stalled
			? banner.can_reset
				? `<button type="button" class="btn btn-xs btn-default dinext-reset-round">${__(
						"Reset round"
				  )}</button>`
				: ""
			: names.map((user) => frappe.utils.escape_html(user)).join(", ");
		const section = frm.dashboard.add_section(body, title, "dinext-pending-approvers");
		frm.dashboard.show();
		if (!banner.can_reset) return;
		$(section)
			.find(".dinext-reset-round")
			.on("click", () => {
				frappe.prompt(
					[
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Reason"),
							reqd: 1,
						},
					],
					async (values) => {
						await frappe.xcall("dinext_common.workflow_approval.api.reset_round", {
							round_id: banner.round_id,
							reason: values.reason,
						});
						frm.reload_doc();
					},
					__("Reset approval round"),
					__("Reset")
				);
			});
	};
	const scheduleBanner = (frm, attempt = 0) => {
		if (!frm || frm.is_new()) return;
		if (!frm.dashboard?.parent) {
			if (attempt < 20) {
				setTimeout(() => scheduleBanner(frm, attempt + 1), 50);
			}
			return;
		}
		paintApprovalBanner(frm);
	};
	const registerPendingApprovers = () => {
		if (!enabled()) return;
		const doctypes = new Set([
			...Object.keys(frappe.workflow?.workflows || {}),
			"Application For Leave",
		]);
		doctypes.delete("User Timesheet");
		doctypes.forEach((doctype) => {
			if (pendingRegistered.has(doctype)) return;
			pendingRegistered.add(doctype);
			frappe.ui.form.on(doctype, {
				refresh(frm) {
					scheduleBanner(frm);
				},
			});
			if (cur_frm && cur_frm.doctype === doctype && !cur_frm.is_new()) {
				scheduleBanner(cur_frm);
			}
		});
	};

	const start = () => {
		patchFormActions();
		patchBulkActions();
		registerPendingApprovers();
		frappe.router.on("change", registerPendingApprovers);
	};
	if (window.frappe?.router) {
		start();
	} else {
		document.addEventListener("DOMContentLoaded", start);
	}
})();
