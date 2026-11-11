const fixture = () => Cypress.env("workflowScenarioTimesheet");
const parentActions = "dinext_timesheets.workflow_approval.get_timesheet_position_actions";
const parentApply = "dinext_timesheets.workflow_approval.apply_timesheet_position_action";
const contextMethod = "dinext_common.workflow_approval.scenarios.api.get_workflow_context";
const personalTransitions = "dinext_common.workflow_approval.api.get_my_source_transitions";
const bulkVote = "dinext_common.workflow_approval.api.bulk_vote";

context("mixed Workflow scenarios in Timesheets", () => {
	before(() => cy.task("scenarioTimesheetSeed", null, { timeout: 120000 })
		.then(data => Cypress.env("workflowScenarioTimesheet", data)));
	after(() => cy.task("scenarioTimesheetCleanup", null, { timeout: 120000 }));

	it("keeps exact child targets, quorum, progress and pending names on the real parent and list", () => {
		const data = fixture();
		let requestId;
		let targets;
		cy.login(data.actor, data.password);
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(data.parent)}`);
		cy.window().should(win => expect(win.cur_frm?.doc?.name).to.equal(data.parent));
		cy.window().should(win => {
			expect(win.cur_frm.ut?.table).to.exist;
			expect(win.cur_frm.ts_positions.map(row => row.name)).to.have.members(data.positions);
		});
		cy.contains(".form-message.blue", data.other_name).should("be.visible");
		cy.call(parentActions, { timesheet_name: data.parent }).then(response => {
			const selected = response.body.message.actions.find(row => row.action === data.action);
			expect(selected.comment_is_required).to.equal(true);
			expect(selected.targets).to.have.length(2);
		});
		const group = ".page-container:visible .inner-group-button[data-label='Workflow']";
		cy.get(`${group} > button`).should("be.visible").click();
		cy.contains(`${group} .dropdown-item`, data.action).should("be.visible").click();
		cy.get(".modal:visible .btn-primary").should("be.disabled");
		cy.get(".modal:visible textarea[data-fieldname='comment']").type("Cypress mixed Timesheet decision").blur();
		cy.intercept("POST", `**/api/method/${parentApply}`,
			request => request.continue(response => response.setDelay(1500))).as("parentVote");
		cy.get(".modal:visible .btn-primary").should("not.be.disabled").click();
		cy.window().should(win => {
			expect(win.cur_frm.page.wrapper[0].inert).to.equal(true);
			expect(win.frappe.dom.freeze_count).to.be.greaterThan(0);
			expect(win.frappe.cur_progress?.is_visible).to.equal(true);
		});
		cy.wait("@parentVote").then(({ request, response }) => {
			expect(response.statusCode).to.equal(200);
			const body = typeof request.body === "string" ? Object.fromEntries(new URLSearchParams(request.body)) : request.body;
			requestId = body.request_id;
			targets = typeof body.targets === "string" ? JSON.parse(body.targets) : body.targets;
			expect(targets).to.have.length(2);
			expect(targets.map(row => row.name)).to.have.members(data.positions);
			expect(targets.map(row => row.transition_uuid)).to.have.members(data.uuids);
			expect(targets.map(row => row.workflow)).to.have.members(data.workflows);
			expect(response.body.message.processed).to.equal(2);
			expect(response.body.message.total).to.equal(2);
		});
		cy.window().should(win => {
			expect(win.cur_frm.doc.ut_status).to.equal("Rejected");
			expect(win.cur_frm.page.wrapper[0].inert).to.equal(false);
			expect(win.frappe.dom.freeze_count).to.equal(0);
			expect(win.frappe.cur_progress == null).to.equal(true);
		});
		cy.get(".modal:visible, .modal-backdrop, #freeze").should("not.exist");
		cy.contains(".form-message.blue", data.other_name).should("be.visible");
		cy.contains(`${group} .dropdown-item`, data.action).should("not.exist");
		cy.window().should(win => {
			for (const [index, name] of data.positions.entries())
				expect(win.cur_frm.ts_positions.find(row => row.name === name)?.status)
					.to.equal(index ? data.target_state : data.initial_state);
		});
		cy.window().then(win => win.scrollTo(0, 0));
		cy.screenshot("workflow-scenarios-timesheet-parent", { capture: "viewport" });
		cy.then(() => cy.call(parentApply, { timesheet_name: data.parent, action: data.action,
			comment: "Cypress mixed Timesheet decision", request_id: requestId, targets }));
		for (let index = 0; index < data.positions.length; index += 1) {
			cy.call(contextMethod, { doctype: "User Timesheet Position", name: data.positions[index] }).then(response => {
				expect(response.body.message.context.state_field).to.equal(data.state_fields[index]);
				expect(response.body.message.context.state).to.equal(index ? data.target_state : data.initial_state);
			});
		}
		cy.window().then(win => win.frappe.set_route("List", "User Timesheet Position", "List"));
		cy.window().should(win => expect(win.cur_list?.filter_area?.set).to.be.a("function"));
		cy.window().then(async win => {
			await win.cur_list.filter_area.clear(false);
			await win.cur_list.filter_area.set([["User Timesheet Position", "name", "in", data.positions]]);
			win.cur_list.filter_area.trigger_refresh = false;
			try {
				win.cur_list.last_args = null;
				// Avoid the instance throttle queuing a second render during selection.
				await win.frappe.views.ListView.prototype.refresh.call(win.cur_list);
				await win.frappe.after_ajax();
			} finally {
				win.cur_list.filter_area.trigger_refresh = true;
			}
		});
		for (let index = 0; index < data.positions.length; index += 1) {
			cy.get(`.list-row-checkbox[data-name='${data.positions[index]}']`).closest(".list-row")
				.should("contain", index ? data.target_state : data.initial_state);
		}
		cy.get(`.list-row-checkbox[data-name='${data.positions[0]}']`).closest(".list-row")
			.find(".dinext-utp-action-select").should("not.exist");
		cy.screenshot("workflow-scenarios-timesheet-positions", { capture: "viewport" });
		let rowTransition;
		cy.call(personalTransitions, { doctype: "User Timesheet Position", names: [data.positions[1]] })
			.then(response => {
				rowTransition = response.body.message[data.positions[1]].find(row => row.action === data.reopen_action);
				expect(rowTransition.targets).to.have.length(1);
			});
		cy.intercept("POST", `**/api/method/${bulkVote}`).as("rowVote");
		cy.window().then(async win => {
			await win.frappe.after_ajax();
			await win.cur_list._dinext_workflow_render_promise;
		});
		cy.get(`.list-row-checkbox[data-name='${data.positions[1]}']`).closest(".list-row")
			.find(".dinext-utp-action-select").should("be.visible").select(data.reopen_action);
		cy.wait("@rowVote").then(({ request, response }) => {
			const body = typeof request.body === "string" ? Object.fromEntries(new URLSearchParams(request.body)) : request.body;
			const rowTargets = typeof body.targets === "string" ? JSON.parse(body.targets) : body.targets;
			expect(rowTargets).to.deep.equal(rowTransition.targets);
			expect(response.body.message.failed).to.deep.equal([]);
			expect(response.body.message.succeeded).to.have.length(1);
			expect(response.body.message.succeeded[0].result.transitioned,
				JSON.stringify(response.body.message.succeeded[0].result)).to.equal(true);
		});
		cy.call(contextMethod, { doctype: "User Timesheet Position", name: data.positions[1] })
			.its("body.message.context.state").should("equal", data.initial_state);
		cy.get(`.list-row-checkbox[data-name='${data.positions[1]}']`).closest(".list-row")
			.should("contain", data.initial_state);
		cy.window().should(win => {
			expect(win.cur_list.page.wrapper[0].inert).to.equal(false);
			expect(win.frappe.dom.freeze_count).to.equal(0);
		});
		cy.get(".modal:visible, .modal-backdrop, #freeze").should("not.exist");
		cy.noPermissionDialog();
	});
});
