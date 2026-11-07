(() => {
	const enabled = () => Boolean(frappe.boot?.enable_parallel_workflow_approval);
	const requestId = () =>
		window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;

	const progressEvent = "dinext_workflow_progress";
	let workflowBusy = false;

	// Use the underlying request promise so all HTTP and connection failures settle.
	const workflowRequest = async (method, args) => {
		const response = await frappe.call({ method, args, silent: workflowBusy });
		return response.message;
	};
	const captureWorkflowForm = (frm) => {
		const { doctype, name } = frm.doc;
		const route = frappe.get_route_str();
		return {
			name,
			isCurrent: () => frappe.get_route_str() === route &&
				frm.doc?.name === name && frm.doc?.doctype === doctype,
		};
	};
	const reloadWorkflowForm = async (frm, refresh = () => frm.refresh()) => {
		const target = captureWorkflowForm(frm);
		const { doctype, docname: name } = frm;
		const response = await frappe.call({
			method: "frappe.desk.form.load.getdoc",
			type: "GET",
			args: { doctype, name },
		});
		if (!target.isCurrent()) return;
		if (!response.docs?.some((doc) => doc.doctype === doctype && doc.name === name)) {
			throw new Error(__("Could not reload the workflow document"));
		}
		await refresh();
		// Form.refresh schedules its script hooks on the promise queue.
		await new Promise((resolve) => setTimeout(resolve, 0));
		await frappe.after_ajax();
	};
	const reportWorkflowError = (error) => {
		const serverMessages = error?.responseJSON?._server_messages;
		if (serverMessages) {
			try {
				frappe.msgprint(JSON.parse(serverMessages));
				return;
			} catch {
				// Fall back to the request error when a response is incomplete.
			}
		}
		frappe.msgprint({
			indicator: "red",
			message: frappe.utils.escape_html(
				error?.message || __("The workflow result could not be confirmed")
			),
		});
	};

	const closeProgressDialog = (dialog) => new Promise((resolve) => {
		const remove = () => {
			if (frappe.cur_progress === dialog) frappe.cur_progress = null;
			const dialogs = frappe.ui.open_dialogs;
			const index = dialogs?.indexOf(dialog) ?? -1;
			if (index >= 0) dialogs.splice(index, 1);
			dialog.$wrapper.remove();
			resolve();
		};
		if (!dialog.is_visible && !dialog.$wrapper.is(":visible")) {
			remove();
			return;
		}
		dialog.$wrapper.one("hidden.bs.modal", remove);
		const hide = () => {
			if (frappe.cur_progress === dialog) frappe.hide_progress();
			else dialog.hide();
		};
		if (dialog.display) hide();
		else dialog.$wrapper.one("shown.bs.modal", hide);
	});

	const runWorkflowOperation = async (page, operation, { count = 1, title, requestId } = {}) => {
		if (workflowBusy) return;
		workflowBusy = true;
		const wrapper = page?.wrapper?.[0];
		const wasInert = wrapper?.inert;
		const wasBusy = wrapper?.getAttribute("aria-busy");
		const blockKeys = (event) => {
			event.preventDefault();
			event.stopImmediatePropagation();
		};
		let dialog;
		const progressCleanups = [];
		let processed = 0;
		let total = count;
		const blockBackdrop = (event) => {
			if (event.target === event.currentTarget) event.stopImmediatePropagation();
		};
		const updateProgress = (completed, currentTotal = total) => {
			if (
				count < 2 ||
				!Number.isInteger(completed) ||
				completed < processed ||
				!Number.isInteger(currentTotal) ||
				currentTotal < 1 ||
				completed > currentTotal
			)
				return;
			processed = completed;
			total = currentTotal;
			const current = frappe.show_progress(
				title,
				processed,
				total,
				__("Processed {0} of {1}", [processed, total])
			);
			if (dialog !== current) {
				if (dialog) progressCleanups.push(closeProgressDialog(dialog));
				dialog = current;
				dialog.no_cancel();
				dialog.$wrapper[0].addEventListener("click", blockBackdrop, true);
			}
		};
		const onProgress = (progress) => {
			if (progress.request_id === requestId) {
				updateProgress(progress.count, progress.total);
			}
		};

		try {
			if (wrapper) {
				wrapper.inert = true;
				wrapper.setAttribute("aria-busy", "true");
			}
			document.addEventListener("keydown", blockKeys, true);
			frappe.dom.freeze();
			if (count > 1) {
				frappe.realtime.on(progressEvent, onProgress);
				updateProgress(0);
			}
			return await operation(updateProgress);
		} finally {
			try {
				if (count > 1) frappe.realtime.off(progressEvent, onProgress);
				if (dialog) progressCleanups.push(closeProgressDialog(dialog));
				await Promise.all(progressCleanups);
			} finally {
				frappe.dom.unfreeze();
				document.removeEventListener("keydown", blockKeys, true);
				if (wrapper) {
					wrapper.inert = wasInert;
					if (wasBusy == null) wrapper.removeAttribute("aria-busy");
					else wrapper.setAttribute("aria-busy", wasBusy);
				}
				workflowBusy = false;
			}
		}
	};

	const normalizeWorkflowComment = (value) => {
		// Match policy.normalize_comment: decode entities, strip markup and Cc/Cf,
		// trim, then count Unicode code points (not UTF-16 units).
		let text = String(value || "");
		if (typeof document.createElement === "function") {
			const decoder = document.createElement("textarea");
			// Preserve control separators during entity parsing. HTML replaces
			// literal NUL, so use another removable Cc until the final strip.
			decoder.innerHTML = text.replace(/\0/g, "\u0001").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
			text = decoder.value;
		} else {
			text = text.replace(/&(?:#([xX][0-9a-fA-F]+|[0-9]+);?|(nbsp|lt|gt|quot|apos|amp);)/g,
				(_, code, key) => {
					if (!code) return {nbsp: "\u00a0", lt: "<", gt: ">", quot: '"', apos: "'", amp: "&"}[key];
					const value = code[0].toLowerCase() === "x" ? parseInt(code.slice(1), 16) : Number(code);
					return value === 0 || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)
						? "\ufffd" : String.fromCodePoint(value);
				});
		}
		return text.replace(/<[^>]*>/g, "").replace(/[\p{Cc}\p{Cf}]/gu, "").trim();
	};

	const bindWorkflowCommentValidation = (dialog, required = () => true) => {
		const field = dialog.fields_dict.comment;
		let submitting = false;
		const validate = () => {
			const comment = normalizeWorkflowComment(dialog.get_value("comment"));
			const valid = (!required() || Boolean(comment)) && [...comment].length <= 4000;
			if (valid && !submitting) dialog.enable_primary_action();
			else dialog.disable_primary_action();
			return valid;
		};
		field.$input.on("input.dinextApproval change.dinextApproval", validate);
		dialog.$wrapper.on("shown.bs.modal.dinextApproval", () => field.set_focus());
		validate();
		return {
			validate,
			setSubmitting(value) { submitting = value; validate(); },
		};
	};

	const approvalValueLabel = (value, fieldname) =>
		fieldname === "completion_source"
			? __(value || "", null, "Approval completion source")
			: __(value || "");

	const approvalReportFormatter = (value, row, column, data, defaultFormatter) => {
		const field = column.fieldname;
		const safe = frappe.utils.escape_html;
		if (field === "reference_name" && data?.source_deleted_at) return safe(value || "");
		if (field === "available_actions") {
			const actions = data?.available_transitions?.map((item) => item.action)
				|| String(value || "").split(", ");
			return [...new Set(actions)].map((action) => safe(__(action))).join(", ");
		}
		if (field === "progress" && data?.progress_transitions) {
			return data.progress_transitions.map((transition) =>
				`${safe(__(transition.action))} ${Number(transition.votes)}/${Number(transition.threshold)}`
			).join("; ");
		}
		if (["action", "status", "round_status", "workflow_state", "reference_doctype", "completion_source"].includes(field)) {
			return safe(approvalValueLabel(value, field));
		}
		if (field === "group_label" && data?.group_type === "Document Type") return safe(__(value));
		return defaultFormatter(value, row, column, data);
	};

	const localizeApprovalEvent = (content) => {
		// Only engine-generated Workflow templates with the expected escaped bold
		// actor/action structure. User suffixes are preserved, never translated.
		const safe = frappe.utils.escape_html;
		const decode = (text) => String(text).replace(/&(amp|lt|gt|quot|apos|#39);/g,
			(_, key) => ({amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", "#39": "'"})[key]);
		const vote = String(content || "").match(/^<(strong|b)>([^<>]+)<\/\1> (voted|automatically reused action) <(strong|b)>([^<>]+)<\/\4>(: [^<>]*)?$/);
		if (vote) {
			const actor = `<strong>${safe(decode(vote[2]))}</strong>`;
			const action = `<strong>${safe(__(decode(vote[5])))}</strong>`;
			const suffix = vote[6] ? safe(decode(vote[6])) : "";
			return vote[3] === "voted"
				? __("{0} voted {1}{2}", [actor, action, suffix])
				: __("{0} automatically reused action {1}", [actor, action]);
		}
		const reset = String(content || "").match(/^Approval round reset by <(strong|b)>([^<>]+)<\/\1>: ([^<>]*)$/);
		if (reset) {
			const actor = `<strong>${safe(decode(reset[2]))}</strong>`;
			const details = reset[3].match(/^([\s\S]*?)\. Carried: ([\s\S]*)\. Dropped: ([\s\S]*)\.$/);
			return details
				? __("Approval round reset by {0}: {1}. Carried: {2}. Dropped: {3}.",
					[actor, ...details.slice(1).map((part) => safe(decode(part)))])
				: __("Approval round reset by {0}: {1}", [actor, safe(decode(reset[3]))]);
		}
		const retry = String(content || "").match(/^Approval finalization retried by <(strong|b)>([^<>]+)<\/\1>$/);
		if (retry) return __("Approval finalization retried by {0}", [`<strong>${safe(decode(retry[2]))}</strong>`]);
		const fixed = [
			"Workflow approval is stalled because no action can reach its threshold.",
			"Workflow finalization failed and requires a manager rebuild.",
		];
		return fixed.includes(content) ? safe(__(content)) : null;
	};

	const localizeApprovalTimeline = (frm) => {
		const timeline = frm.timeline;
		if (!timeline || timeline._dinextApprovalEvents) return;
		const original = timeline.get_workflow_timeline_contents;
		if (typeof original !== "function") return;
		timeline._dinextApprovalEvents = true;
		timeline.get_workflow_timeline_contents = function () {
			const items = original.call(this);
			if (cur_frm !== frm) return items;
			const logs = this.doc_info.workflow_logs || [];
			return items.map((item, index) => {
				const content = logs[index]?.content;
				const localized = localizeApprovalEvent(content);
				if (localized === null) return item;
				return {...item, content: item.content.replace(__(content), () => localized)};
			});
		};
		timeline.refresh();
	};

	const withWorkflowComment = (transition, submit) => {
		if (workflowBusy) return;
		if (!(transition.comment_is_required ?? transition.custom_comment_is_required))
			return submit("");
		let validation;
		const dialog = new frappe.ui.Dialog({
			title: frappe.utils.escape_html(__("Comment required for {0}", [__(transition.action)])),
			fields: [{fieldname: "comment", fieldtype: "Small Text", label: __("Comment"), reqd: 1}],
			primary_action_label: __("Apply"),
			async primary_action() {
				if (!validation.validate()) return;
				validation.setSubmitting(true);
				try {
					const result = await submit(dialog.get_value("comment"));
					dialog.hide();
					return result;
				} finally {
					validation.setSubmitting(false);
				}
			},
		});
		validation = bindWorkflowCommentValidation(dialog);
		dialog.show();
		return dialog;
	};

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

	const supportedStyles = new Set([
		"primary",
		"info",
		"success",
		"warning",
		"danger",
		"inverse",
	]);
	const workflowTransitionStyle = (transition) => {
		const targets = transition.next_state
			? [transition.next_state]
			: (transition.positions || []).map((row) => row.next_state);
		const styles = targets.map((state) => {
			const local = frappe.get_doc("Workflow State", state);
			const value = local ? local.style : frappe.boot?.workflow_state_styles?.[state];
			const style = String(value || "")
				.trim()
				.toLowerCase();
			return supportedStyles.has(style) ? style : "";
		});
		return styles.length && styles.every((style) => style === styles[0]) ? styles[0] : "";
	};
	const workflowTransitionLabel = (transition, text) => {
		let label = workflowActionLabel(transition.action, text);
		// Frappe's filled close glyph has a fixed fill; its themed equivalent uses --icon-stroke.
		if (typeof document !== "undefined" && document.getElementById("icon-close-alt")) {
			label = label.replace('href="#icon-close"', 'href="#icon-close-alt"');
		}
		return `<span class="dinext-workflow-transition" data-workflow-style="${workflowTransitionStyle(
			transition
		)}">${label}</span>`;
	};
	const decorateWorkflowTransition = (element, transition) =>
		$(element)
			.addClass("dinext-workflow-transition")
			.attr("data-workflow-style", workflowTransitionStyle(transition));

	const getPendingApproverNames = (rows) => {
		const byUser = new Map();
		for (const row of rows || []) {
			if (!row?.approver || row.approver === frappe.session?.user) continue;
			if (!byUser.has(row.approver)) {
				byUser.set(row.approver, String(row.approver_name || row.approver));
			}
		}
		return [...byUser.values()].sort((left, right) => left.localeCompare(right));
	};

	const paintPendingApprovers = (frm, rows) => {
		const messages = frm.layout?.message;
		if (!messages?.length) return;
		frm.dashboard?.parent?.find(".dinext-pending-approvers").remove();
		messages.children(".dinext-pending-approvers").remove();
		const names = getPendingApproverNames(rows).map((name) => frappe.utils.escape_html(name));
		if (!names.length) {
			if (!messages.children().length) messages.addClass("hidden");
			return;
		}
		frm.dashboard.add_comment(
			__("Action expected from: {0}", [frappe.utils.comma_and(names)]),
			"blue",
			true
		);
		return messages.children(".form-message").last().addClass("dinext-pending-approvers");
	};

	Object.assign(frappe.dinext, {
		normalizeWorkflowComment,
		bindWorkflowCommentValidation,
		approvalValueLabel,
		approvalReportFormatter,
		localizeApprovalEvent,
		workflowTransitionStyle,
		workflowTransitionLabel,
		decorateWorkflowTransition,
		runWorkflowOperation,
		withWorkflowComment,
		workflowRequest,
		reloadWorkflowForm,
		captureWorkflowForm,
		reportWorkflowError,
		getPendingApproverNames,
		paintPendingApprovers,
	});

	const rebuildCleanups = new WeakMap();

	const promptResetRounds = (rounds, options, button, clear) => {
		frappe.prompt(
			[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
			async (values) => {
				button.prop("disabled", true).text(__("Rebuilding…"));
				try {
					const result = await frappe.xcall(
						"dinext_common.workflow_approval.api.reset_rounds",
						{
							round_ids: rounds.map((round) => round.round_id),
							reason: values.reason,
						}
					);
					if (!result.failed?.length) clear();
					await options.reload?.();
					if (result.failed?.length) {
						const byId = new Map(rounds.map((round) => [round.round_id, round]));
						const failures = result.failed
							.map((failure) => {
								const round = byId.get(failure.round_id);
								const label =
									round?.label || round?.source_title || __("Approval round");
								return `<li>${frappe.utils.escape_html(
									label
								)}: ${frappe.utils.escape_html(failure.error)}</li>`;
							})
							.join("");
						frappe.msgprint({
							title: __("Some approvals could not be rebuilt"),
							indicator: "orange",
							message: `<ul>${failures}</ul>`,
						});
					}
				} finally {
					button.prop("disabled", false).text(__("Rebuild all"));
				}
			},
			__("Rebuild approval rounds"),
			__("Rebuild all")
		);
	};

	frappe.dinext.paintRebuildRounds = (dashboard, rounds, options = {}) => {
		if (!dashboard) return;
		rebuildCleanups.get(dashboard)?.();
		const parent = $(dashboard.parent || dashboard.wrapper);
		parent.find(".dinext-rebuild-round").remove();
		let host = options.container ? $(options.container) : parent.closest(".page-body");
		if (!host.length) host = parent;
		host.children(".dinext-rebuild-summary").remove();
		if (!rounds?.length || !host.length) return;

		const message = options.message || __("Approval needs rebuilding");
		const summary = $('<div class="dinext-rebuild-summary" role="alert"></div>');
		$('<span class="dinext-rebuild-summary-icon" aria-hidden="true">!</span>').appendTo(
			summary
		);
		$('<span class="dinext-rebuild-summary-message"></span>')
			.text(message)
			.attr("title", message)
			.appendTo(summary);
		let observer;
		const clear = () => {
			observer?.disconnect();
			summary.remove();
			if (rebuildCleanups.get(dashboard) === clear) rebuildCleanups.delete(dashboard);
		};
		rebuildCleanups.set(dashboard, clear);
		if (rounds.every((round) => round.can_reset)) {
			const button = $(
				'<button type="button" class="btn btn-sm dinext-reset-rounds"></button>'
			)
				.text(__("Rebuild all"))
				.appendTo(summary);
			button.on("click", () => promptResetRounds(rounds, options, button, clear));
		}
		host.prepend(summary);
		if (options.fullWidth !== false) {
			const element = host[0];
			const root = element.ownerDocument.documentElement;
			const page = host.closest(".page-container")[0] || root;
			const resize = () => {
				if (!summary[0].isConnected) return clear();
				const style = getComputedStyle(element);
				const hostRect = element.getBoundingClientRect();
				const left = 0;
				const right = root.clientWidth;
				const start = hostRect.left + (parseFloat(style.paddingLeft) || 0);
				const end = hostRect.right - (parseFloat(style.paddingRight) || 0);
				summary.addClass("dinext-rebuild-summary-wide").css({
					width: right - left,
					marginLeft: left - start,
					marginRight: end - right,
					paddingLeft: 32,
					paddingRight: 32,
				});
			};
			resize();
			observer = new ResizeObserver(resize);
			for (const target of new Set([element, page, root])) observer.observe(target);
		}
	};

	const transitionLabel = (transition, transitions) => {
		const sameAction = (transitions || []).filter((row) => row.action === transition.action);
		let text = __(transition.action);
		if (sameAction.length >= 2) {
			const role = transition.allowed || transition.allowed_role || "";
			const next = transition.next_state || "";
			const suffix = [role, next]
				.filter(Boolean)
				.map((value) => __(value))
				.join(" → ");
			if (suffix) text = `${__(transition.action)} (${suffix})`;
		}
		return workflowTransitionLabel(transition, text);
	};

	const applyAction = async (frm, transition, comment, target = captureWorkflowForm(frm)) => {
		if (!target.isCurrent()) return;
		try {
			await runWorkflowOperation(frm.page, async () => {
				frm.selected_workflow_action = transition.action;
				try {
					if (!frappe.ui.form.check_mandatory(frm)) return;
					await frm.script_manager.trigger("before_workflow_action");
					if (!target.isCurrent()) return;
					const args = { doc: frm.doc, action: transition.action };
					if (enabled()) {
						Object.assign(args, {
							transition_uuid: transition.custom_transition_uuid,
							comment,
							request_id: requestId(),
						});
					}
					const result = await workflowRequest(
						"frappe.model.workflow.apply_workflow",
						args
					);
					if (!target.isCurrent()) return;
					if (enabled()) {
						await reloadWorkflowForm(frm);
					} else {
						frappe.model.sync(result);
						await frm.refresh();
						frm.selected_workflow_action = null;
					}
					if (target.isCurrent()) await frm.script_manager.trigger("after_workflow_action");
				} finally {
					frm.selected_workflow_action = null;
				}
			});
		} catch (error) {
			reportWorkflowError(error);
		}
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
				if (
					!frappe.user_roles.includes(transition.allowed) ||
					!hasApprovalAccess(transition)
				) {
					return;
				}
				added = true;
				me.frm.page.add_action_item(workflowTransitionLabel(transition), () =>
					applyAction(me.frm, transition)
				);
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
					this.frm.page.add_action_item(transitionLabel(transition, transitions), () => {
						const target = captureWorkflowForm(this.frm);
						return withWorkflowComment(transition, (comment) =>
							applyAction(this.frm, transition, comment, target)
						);
					});
				});
				this.setup_btn(transitions.length > 0);
			});
		};
		frappe.ui.form.States.__dinext_approval_patched = true;
	};

	const showBulkResult = (result) => {
		const succeeded = result.succeeded || [];
		const successItems = succeeded.map((row) => `<li>${frappe.utils.escape_html(row.name)}</li>`).join("");
		const failures = (result.failed || [])
			.map(
				(row) =>
					`<li><strong>${frappe.utils.escape_html(
						row.name
					)}</strong>: ${frappe.utils.escape_html(row.error)}</li>`
			)
			.join("");
		frappe.msgprint({
			title: __("Workflow result"),
			indicator: failures ? "orange" : "green",
			message: `<p>${__("Succeeded")}: ${succeeded.length}</p>${
				successItems ? `<details><summary>${__("Succeeded")}</summary><ul>${successItems}</ul></details>` : ""
			}${failures ? `<p>${__("Failed")}:</p><ul>${failures}</ul>` : ""}`,
		});
	};

	const waitForBulkJob = async (jobId) => {
		let timeout;
		let request;
		let active = true;
		const unknown = () => new Error(__("The workflow result could not be confirmed"));
		try {
			return await Promise.race([
				(async () => {
					while (active) {
						request = frappe.call({
							method: "dinext_common.workflow_approval.api.get_bulk_workflow_job",
							args: { job_id: jobId },
							silent: true,
						});
						const { message } = await Promise.resolve(request).catch(() => {
							throw unknown();
						});
						if (message?.status === "finished") return message.result;
						if (message?.status === "failed")
							throw new Error(__("The background workflow operation failed"));
						if (message?.status !== "pending") throw unknown();
						await new Promise((resolve) => setTimeout(resolve, 1000));
					}
				})(),
				new Promise((_, reject) => {
					timeout = setTimeout(() => reject(unknown()), 20 * 60 * 1000);
				}),
			]);
		} finally {
			active = false;
			clearTimeout(timeout);
			request?.abort?.();
		}
	};

	let activeListMenu;
	const selectedNames = (listview) => {
		const names = listview.view_name === "List"
			? Array.from(listview.$result.find(".list-row-checkbox:checked"), (row) => row.dataset.name)
			: listview.get_checked_items(true);
		return [...new Set(names)];
	};
	const selectionKey = (names) => JSON.stringify([...names].sort());
	const clearListWorkflowMenu = (listview) => {
		if (activeListMenu === listview) activeListMenu = null;
		listview._dinext_workflow_menu = null;
		listview.page.actions
			.find(".dinext-list-workflow-item, .dinext-workflow-menu-status")
			.remove();
	};
	const workflowMenuStatus = (listview, message) => {
		listview.page.actions.prepend(
			$('<li class="dinext-workflow-menu-status text-muted px-3 py-2" role="status">').text(
				message
			)
		);
	};

	const executeListTransition = async (listview, names, transition, comment) => {
		const id = requestId();
		try {
			const result = await runWorkflowOperation(
				listview.page,
				async (updateProgress) => {
					const wasDisabled = listview.disable_list_update;
					listview.disable_list_update = true;
					try {
						const response = await workflowRequest(
							"frappe.model.workflow.bulk_workflow_approval",
							{
								docnames: names,
								doctype: listview.doctype,
								action: transition.action,
								transition_uuid: transition.transition_uuid,
								comment,
								request_id: id,
								track_progress: names.length > 1,
							}
						);
						const outcome = response?.job_id
							? await waitForBulkJob(response.job_id)
							: response;
						if (!outcome)
							throw new Error(__("The workflow result could not be confirmed"));
						updateProgress(outcome.succeeded.length + outcome.failed.length);
						listview.last_args = null;
						await listview.refresh();
						await listview._dinext_workflow_render_promise;
						return outcome;
					} finally {
						listview.disable_list_update = wasDisabled;
					}
				},
				{
					count: names.length,
					title: frappe.utils.escape_html(__("Applying: {0}", [__(transition.action)], "Workflow")),
					requestId: id,
				}
			);
			if (result?.failed?.length) showBulkResult(result);
		} catch (error) {
			reportWorkflowError(error);
		}
	};

	const patchBulkActions = () => {
		const ListView = frappe.views?.ListView;
		if (!ListView || ListView.__dinext_approval_patched) return;
		const originalToggle = ListView.prototype.toggle_workflow_actions;
		ListView.prototype.toggle_workflow_actions = async function () {
			if (!enabled()) return originalToggle.call(this);
			if (!frappe.model.has_workflow(this.doctype)) return;
			clearListWorkflowMenu(this);
			if (workflowBusy) return;
			const names = selectedNames(this);
			if (!names.length) return;
			const route = frappe.get_route_str();
			const key = selectionKey(names);
			const menu = { key };
			activeListMenu = this;
			this._dinext_workflow_menu = menu;
			const sameSelection = () =>
				frappe.get_route_str() === route && selectionKey(selectedNames(this)) === key;
			const isCurrent = () => this._dinext_workflow_menu === menu && sameSelection();
			this.page.actions_btn_group
				.off("hide.bs.dropdown.dinextWorkflow")
				.on("hide.bs.dropdown.dinextWorkflow", () => clearListWorkflowMenu(this));
			workflowMenuStatus(this, __("Loading workflow actions…"));
			let transitions;
			try {
				transitions = await workflowRequest(
					"dinext_common.workflow_approval.api.get_common_list_transitions",
					{
						doctype: this.doctype,
						names,
					}
				);
			} catch {
				if (isCurrent()) {
					clearListWorkflowMenu(this);
					workflowMenuStatus(this, __("Could not load workflow actions"));
				}
				return;
			}
			if (!isCurrent()) return;
			this.page.actions.find(".dinext-workflow-menu-status").remove();
			if (!transitions?.length) {
				workflowMenuStatus(this, __("No common workflow actions"));
				return;
			}
			for (const transition of transitions) {
				this.page
					.add_actions_menu_item(transitionLabel(transition, transitions), () => {
						if (!isCurrent()) return;
						return withWorkflowComment(transition, (comment) => {
							if (sameSelection())
								return executeListTransition(this, names, transition, comment);
						});
					})
					.closest("li")
					.addClass("dinext-list-workflow-item");
			}
		};
		const originalChecked = ListView.prototype.on_row_checked;
		ListView.prototype.on_row_checked = function () {
			originalChecked.call(this);
			const menu = this._dinext_workflow_menu;
			if (menu && menu.key !== selectionKey(selectedNames(this))) {
				clearListWorkflowMenu(this);
			}
		};
		const original = ListView.prototype.get_workflow_action_menu_items;
		ListView.prototype.get_workflow_action_menu_items = function () {
			if (!frappe.model.has_workflow(this.doctype)) return original.call(this);
			if (enabled()) return [];
			const transitions = frappe.workflow.get_all_transitions(this.doctype) || [];
			return (original.call(this) || []).map((item) => ({
				...item,
				label: workflowTransitionLabel(
					{
						action: item.name,
						positions: transitions.filter((row) => row.action === item.name),
					},
					item.label
				),
			}));
		};
		ListView.__dinext_approval_patched = true;
	};

	const pendingRegistered = new Set();
	const paintApprovalBanner = async (frm) => {
		if (!frm || !frm.dashboard?.parent) return;
		const target = captureWorkflowForm(frm);
		const generation = (frm._dinext_approval_banner_generation || 0) + 1;
		frm._dinext_approval_banner_generation = generation;
		const isCurrent = () => target.isCurrent() &&
			frm._dinext_approval_banner_generation === generation;
		const options = {
			container: frm.page?.wrapper?.find(".page-body").first(),
			reload: () => frm.reload_doc(),
		};
		frappe.dinext.paintRebuildRounds(frm.dashboard, [], options);
		paintPendingApprovers(frm, []);
		if (frm.is_new()) return;
		let banner;
		try {
			banner = await workflowRequest(
				"dinext_common.workflow_approval.api.get_form_approval_banner",
				{ doctype: frm.doctype, name: target.name }
			);
		} catch (error) {
			if (!isCurrent()) return;
			console.error(error);
			frappe.show_alert({
				message: __("Could not load approval status"),
				indicator: "red",
			});
			return;
		}
		if (!banner || !isCurrent()) return;
		const rounds = banner.rounds || [];
		frappe.dinext.paintRebuildRounds(frm.dashboard, rounds, options);
		paintPendingApprovers(frm, banner.pending_approvers || []);
	};
	const scheduleBanner = (frm, attempt = 0) => {
		if (!frm) return;
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
					localizeApprovalTimeline(frm);
				},
				timeline_refresh(frm) {
					localizeApprovalTimeline(frm);
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
		frappe.router.on("change", () => {
			if (activeListMenu) clearListWorkflowMenu(activeListMenu);
			registerPendingApprovers();
		});
		$(document).on("form-refresh.dinextApproval", registerPendingApprovers);
	};
	if (window.frappe?.router) {
		start();
	} else {
		document.addEventListener("DOMContentLoaded", start);
	}
})();
