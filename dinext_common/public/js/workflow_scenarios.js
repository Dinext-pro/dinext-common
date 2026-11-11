(() => {
	const enabled = () => Boolean(frappe.boot?.enable_parallel_workflow_approval);
	const contexts = new WeakMap();
	const nativeIndicatorScopes = [];
	let activeTransition;
	const currentFormDoc = (doctype) => {
		const route = frappe.get_route?.() || [];
		return route[0] === "Form" && typeof cur_frm !== "undefined" &&
			cur_frm?.doctype === doctype && cur_frm.doc?.name === route.slice(2).join("/")
			? cur_frm.doc : null;
	};
	const lookupDoc = (doctype, name) => name
		? (typeof locals !== "undefined" ? locals[doctype]?.[name] : null)
		: currentFormDoc(doctype);
	const envelopeFor = (doc) => {
		if (!enabled() || !doc) return undefined;
		if (doc.__onload && Object.hasOwn(doc.__onload, "dinext_workflow_context")) {
			return { context: doc.__onload.dinext_workflow_context,
				definition: doc.__onload.dinext_workflow_definition,
				error: doc.__onload.dinext_workflow_error };
		}
		return contexts.get(doc);
	};
	const contextFor = (doc) => envelopeFor(doc)?.context;
	const definitionFor = (doc) => {
		const envelope = envelopeFor(doc);
		if (!envelope?.context?.workflow) return null;
		return envelope.definition || frappe.get_doc("Workflow", envelope.context.workflow);
	};
	const stateFor = (doc) => {
		const context = contextFor(doc);
		return context?.state_field ? (context.state ?? doc[context.state_field]) : null;
	};
	const store = (doc, envelope) => {
		if (envelope?.managed === false) { contexts.delete(doc); return; }
		if (doc && envelope && Object.hasOwn(envelope, "context")) contexts.set(doc, envelope);
	};
	const loadBatches = async (method, doctype, names, call = options => frappe.call(options)) => {
		const unique = [...new Set(names)];
		const batches = [];
		for (let start = 0; start < unique.length; start += 500) {
			batches.push((async () => {
				const response = await call({
					method, args: { doctype, names: unique.slice(start, start + 500) }, silent: true, freeze: false,
				});
				return response.message || {};
			})());
		}
		return Object.assign({}, ...await Promise.all(batches));
	};
	const loadContexts = (...args) => loadBatches(
		"dinext_common.workflow_approval.scenarios.api.get_workflow_contexts", ...args);
	const updateForm = (frm, doc) => {
		const context = contextFor(doc);
		if (context === undefined) return;
		const field = context?.state_field || null;
		frm.state_fieldname = field;
		if (frm.states) {
			frm.states.state_fieldname = field;
			frm.states.update_fields = [...new Set((definitionFor(doc)?.states || [])
				.map(row => row.update_field).filter(Boolean))];
		}
	};
	const paintRoutingError = (frm) => {
		const messages = frm.layout?.message;
		if (!messages?.length) return;
		messages.children(".dinext-workflow-routing-error").remove();
		const error = envelopeFor(frm.doc)?.error;
		if (!error) {
			if (!messages.children().length) messages.addClass("hidden");
			return;
		}
		const heading = frappe.utils.escape_html(__("Workflow setup failed"));
		frm.dashboard.add_comment(`${heading}: ${frappe.utils.escape_html(String(error))}`, "orange", true);
		messages.children(".form-message").last().addClass("dinext-workflow-routing-error");
	};
	frappe.dinext = frappe.dinext || {};
	Object.assign(frappe.dinext, {
		getWorkflowContext: contextFor,
		getWorkflowDefinition: definitionFor,
		getWorkflowState: stateFor,
		storeWorkflowContext: store,
		paintWorkflowRoutingError: paintRoutingError,
		async withWorkflowTargets(transition, operation) {
			const previous = activeTransition;
			activeTransition = transition;
			try { return await operation(); }
			finally { activeTransition = previous; }
		},
		prepareWorkflowRequest(method, args) {
			if (enabled() && ["dinext_timesheets.workflow_approval.apply_timesheet_position_action",
				"dinext_common.workflow_approval.api.bulk_vote", "frappe.model.workflow.bulk_workflow_approval"].includes(method) &&
				activeTransition?.action === args.action && activeTransition.targets && !args.targets)
				return { ...args, targets: activeTransition.targets };
			return args;
		},
	});

	const patchWorkflow = () => {
		const workflow = frappe.workflow;
		if (!workflow || workflow.__dinext_scenarios) return;
		const wrap = (name, resolve) => {
			const original = workflow[name];
			if (!original) return;
			workflow[name] = function (...args) {
				const result = enabled() ? resolve.apply(this, args) : undefined;
				return result === undefined ? original.apply(this, args) : result;
			};
		};
		wrap("get_state_fieldname", (doctype, name) => {
			if (nativeIndicatorScopes.at(-1) === doctype) return null;
			const context = contextFor(lookupDoc(doctype, name));
			return context === undefined ? undefined : context?.state_field || null;
		});
		wrap("get_state", doc => contextFor(doc) === undefined ? undefined : stateFor(doc));
		wrap("is_read_only", (doctype, name) => {
			const doc = lookupDoc(doctype, name);
			if (contextFor(doc) === undefined) return undefined;
			if (!doc || doc.__islocal || !contextFor(doc)?.workflow) return false;
			const state = stateFor(doc);
			if (!state) return false;
			const roles = (definitionFor(doc)?.states || [])
				.filter(row => row.state === state).map(row => row.allow_edit);
			return !(frappe.user_roles || []).some(role => roles.includes(role));
		});
		wrap("get_default_state", (doctype, docstatus) => {
			const doc = currentFormDoc(doctype);
			if (contextFor(doc) === undefined) return undefined;
			return (definitionFor(doc)?.states || [])
				.find(row => Number(row.doc_status) === Number(docstatus))?.state || null;
		});
		wrap("get_document_state_roles", (doctype, state) => {
			const doc = currentFormDoc(doctype);
			if (contextFor(doc) === undefined) return undefined;
			return (definitionFor(doc)?.states || []).filter(row => row.state === state).map(row => row.allow_edit);
		});
		wrap("get_update_fields", (doctype) => {
			const doc = currentFormDoc(doctype);
			if (contextFor(doc) === undefined) return undefined;
			return [...new Set((definitionFor(doc)?.states || []).map(row => row.update_field).filter(Boolean))];
		});
		wrap("is_self_approval_enabled", doctype => {
			const doc = currentFormDoc(doctype);
			return contextFor(doc) === undefined ? undefined : Boolean(definitionFor(doc)?.allow_self_approval);
		});
		wrap("get_transitions", doc => contextFor(doc) === undefined ? undefined :
			frappe.xcall("frappe.model.workflow.get_transitions", { doc }));
		const hasWorkflow = frappe.model.has_workflow;
		frappe.model.has_workflow = function (doctype, name) {
			const context = contextFor(lookupDoc(doctype, name));
			if (context !== undefined) return Boolean(context?.workflow);
			// Inactive definitions may still own Running processes; the server resolves each row.
			if (enabled() && frappe.get_list) return Boolean(frappe.get_list("Workflow", { document_type: doctype }).length);
			return hasWorkflow.call(this, doctype);
		};
		const xcall = frappe.xcall;
		if (xcall) frappe.xcall = function (method, args, ...rest) {
			if (enabled() && method === "frappe.model.workflow.can_cancel_document") {
				const doc = currentFormDoc(args?.doctype);
				if (contextFor(doc) !== undefined) {
					const definition = definitionFor(doc);
					const cancelling = new Set((definition?.states || [])
						.filter(row => Number(row.doc_status) === 2).map(row => row.state));
					return Promise.resolve(!(definition?.transitions || []).some(row => cancelling.has(row.next_state)));
				}
			}
			return xcall.call(this, method, args, ...rest);
		};
		workflow.__dinext_scenarios = true;
	};

	const patchForms = () => {
		const Form = frappe.ui?.form?.Form;
		if (Form && !Form.__dinext_scenarios) {
			const refresh = Form.prototype.refresh;
			Form.prototype.refresh = function (name, ...args) {
				const doc = lookupDoc(this.doctype, name || this.docname) || this.doc;
				updateForm(this, doc);
				return refresh.call(this, name, ...args);
			};
			const setup = Form.prototype.setup;
			if (setup) Form.prototype.setup = function (...args) {
				const result = setup.apply(this, args);
				if (enabled() && contextFor(this.doc) !== undefined && this.states && !this.states.state_fieldname) {
					// Native States skips its event binding when the first document has no match.
					$(this.wrapper).on("render_complete.dinextScenarios", () => this.states.refresh());
				}
				updateForm(this, this.doc);
				return result;
			};
			Form.__dinext_scenarios = true;
		}
		const States = frappe.ui?.form?.States;
		if (States && !States.__dinext_scenarios) {
			const refresh = States.prototype.refresh;
			States.prototype.refresh = function (...args) {
				updateForm(this.frm, this.frm.doc);
				paintRoutingError(this.frm);
				if (contextFor(this.frm.doc) !== undefined && !contextFor(this.frm.doc)?.workflow) return;
				return refresh.apply(this, args);
			};
			const getState = States.prototype.get_state;
			States.prototype.get_state = function (...args) {
				return contextFor(this.frm.doc) === undefined
					? getState.apply(this, args) : stateFor(this.frm.doc);
			};
			const defaultState = States.prototype.set_default_state;
			States.prototype.set_default_state = function (...args) {
				// Persisted state belongs to the server-side process, including repeated instances.
				if (contextFor(this.frm.doc) !== undefined) return;
				if (enabled() && this.frm.doc.__islocal) return;
				return defaultState.apply(this, args);
			};
			const help = States.prototype.setup_help;
			States.prototype.setup_help = function (...args) {
				const doc = this.frm.doc;
				if (contextFor(doc) === undefined) return help.apply(this, args);
				const definition = definitionFor(doc);
				if (!definition) return;
				this.frm.page.add_action_item(__("Help"), async () => {
					const expected = contextFor(doc)?.process_id;
					const transitions = await frappe.workflow.get_transitions(doc);
					if (this.frm.doc !== doc || contextFor(doc)?.process_id !== expected) return;
					const escape = value => frappe.utils.escape_html(String(value || ""));
					const roles = (definition.states || []).filter(row => row.state === stateFor(doc))
						.map(row => __(row.allow_edit)).join(", ");
					const next = transitions.map(row => `${__(row.action)} (${__(row.allowed)})`).join(", ");
					frappe.msgprint({ title: escape(`${__("Workflow")}: ${definition.name}`),
						message: `<p>${__("Current status")}: ${escape(__(stateFor(doc)))}</p>` +
							`<p>${__("Document is only editable by users with role")}: ${escape(roles)}</p>` +
							`<p>${__("Next actions")}: ${escape(next || __("None: End of Workflow"))}</p>` });
				}, true);
			};
			States.__dinext_scenarios = true;
		}
		const Toolbar = frappe.ui?.form?.Toolbar;
		if (Toolbar && !Toolbar.__dinext_scenarios) {
			const original = Toolbar.prototype.has_workflow;
			Toolbar.prototype.has_workflow = function () {
				const context = contextFor(this.frm.doc);
				return context === undefined ? original.call(this) : Boolean(context?.workflow);
			};
			Toolbar.__dinext_scenarios = true;
		}
	};

	const patchIndicators = () => {
		if (frappe.get_indicator.__dinext_scenarios) return;
		const original = frappe.get_indicator;
		frappe.get_indicator = function (doc, doctype, showWorkflowState) {
			const context = contextFor(doc);
			const definition = definitionFor(doc);
			if (context !== undefined && definition && !doc.__unsaved) {
				const state = stateFor(doc);
				const row = (definition.states || []).find(item => item.state === state);
				if (state && (!definition.override_status || showWorkflowState) && !row?.avoid_status_override) {
					const style = frappe.boot?.workflow_state_styles?.[state] ||
						frappe.get_doc("Workflow State", state)?.style;
					const color = { Success: "green", Warning: "orange", Danger: "red", Primary: "blue",
						Inverse: "black", Info: "light-blue" }[style] || "gray";
					return [__(state, null, doctype || doc.doctype), color, `${context.state_field},=,${state}`];
				}
			}
			if (context !== undefined) {
				// Keep native status/docstatus handling while suppressing its type-wide workflow branch.
				nativeIndicatorScopes.push(doctype || doc.doctype);
				try { return original.call(this, doc, doctype, false); }
				finally { nativeIndicatorScopes.pop(); }
			}
			return original.call(this, doc, doctype, showWorkflowState);
		};
		frappe.get_indicator.__dinext_scenarios = true;
	};

	const patchLists = () => {
		const ListView = frappe.views?.ListView;
		if (!ListView || ListView.__dinext_scenarios) return;
		const render = ListView.prototype.render;
		const refresh = ListView.prototype.refresh;
		if (refresh) ListView.prototype.refresh = function (...args) {
			const result = refresh.apply(this, args);
			return Promise.resolve(result).then(async value => {
				await this._dinext_context_render_promise;
				await this._dinext_workflow_render_promise;
				return value;
			});
		};
		ListView.prototype.render = function (...args) {
			if (!enabled() || !frappe.model.has_workflow(this.doctype) || !this.data?.length)
				return render.apply(this, args);
			const rows = this.data;
			const generation = this._dinext_context_generation = (this._dinext_context_generation || 0) + 1;
			this._dinext_context_loading = true;
			if (this.settings?.refresh && !this.settings.refresh.__dinext_context_guard) {
				const onRefresh = this.settings.refresh;
				const owner = this;
				const guarded = function (...values) {
					if (!owner._dinext_context_loading) return onRefresh.apply(this, values);
				};
				guarded.__dinext_context_guard = true;
				this.settings = { ...this.settings, refresh: guarded };
			}
			const promise = (async () => {
				try {
					const response = await loadContexts(this.doctype, rows.map(row => row.name));
					if (this.data !== rows || this._dinext_context_generation !== generation) return;
					for (const doc of rows) {
						store(doc, response[doc.name]);
						if (this.doctype === "User Timesheet Position" && contextFor(doc)?.workflow)
							doc.status = contextFor(doc).state;
					}
					render.apply(this, args);
					this._dinext_context_loading = false;
					// BaseList.refresh invokes settings.refresh before an asynchronous render settles.
					this.settings?.refresh?.(this);
					const approvalRender = this._dinext_workflow_render_promise;
					if (approvalRender && approvalRender !== promise) await approvalRender;
				} catch (error) {
					if (this.data !== rows || this._dinext_context_generation !== generation) return;
					this._dinext_context_loading = false;
					frappe.show_alert?.({ message: __("Could not load approval status"), indicator: "red" });
					console.error(error);
				}
			})();
			this._dinext_context_render_promise = promise;
			this._dinext_workflow_render_promise = promise;
			return promise;
		};
		ListView.__dinext_scenarios = true;
	};
	const patchTimesheetData = () => {
		if (!frappe.call || frappe.call.__dinext_scenario_projection) return;
		const original = frappe.call;
		frappe.call = function (options, ...args) {
			if (enabled() && options?.method === "dinext_common.workflow_approval.api.get_my_source_transitions" &&
				Array.isArray(options.args?.names) && options.args.names.length > 500) {
				return loadBatches(options.method, options.args.doctype, options.args.names,
					options => original.call(this, options)).then(message => ({ message }));
			}
			const response = original.call(this, options, ...args);
			if (!enabled() || options?.method !== "frappe.desk.reportview.get_list" ||
				options.args?.doctype !== "User Timesheet Position" || !currentFormDoc("User Timesheet")) return response;
			return Promise.resolve(response).then(async result => {
				const rows = result.message;
				if (!Array.isArray(rows) || !rows.length) return result;
				const contexts = await loadContexts("User Timesheet Position", rows.map(row => row.name),
					options => original.call(this, options));
				for (const row of rows) {
					const envelope = contexts[row.name];
					store(row, envelope);
					if (envelope?.context?.workflow) row.status = envelope.context.state;
				}
				return result;
			});
		};
		frappe.call.__dinext_scenario_projection = true;
	};
	const install = () => { patchWorkflow(); patchForms(); patchIndicators(); patchLists(); patchTimesheetData(); };
	install();
	frappe.router?.on("change", install);
})();
