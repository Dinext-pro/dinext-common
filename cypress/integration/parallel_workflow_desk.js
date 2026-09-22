const method = "dinext_common.tests.ui_test_helpers";

const load = () => Cypress.env("wf");

const asApprover = (email) => {
	const fixture = load();
	cy.login(email || fixture.approver, fixture.password);
	cy.openDesk("/app");
};

const openIssue = (name) => {
	cy.visit(`/app/issue/${name}`);
	cy.get(".form-dashboard", { timeout: 120000 }).should("exist");
	cy.window().then((win) => {
		win.frappe.workflow.setup("Issue");
		win.frappe.router.trigger("change");
	});
};

const vote = (email, workflow, issue, action, uuid, extra = {}) => {
	asApprover(email);
	cy.call(`${method}.activate_issue_workflow`, { name: workflow });
	return cy.call("dinext_common.workflow_approval.api.apply_workflow", {
		doc: { doctype: "Issue", name: issue },
		action,
		transition_uuid: uuid,
		request_id: `cy-desk-${Date.now()}-${Math.random().toString(16).slice(2)}`,
		...extra,
	});
};

const issueStatus = (name) =>
	cy
		.call("frappe.client.get_value", {
			doctype: "Issue",
			filters: name,
			fieldname: "status",
		})
		.its("body.message.status");

context("parallel workflow desk", () => {
	before(() => {
		cy.login("wf.approver2@example.com", "Wf-Test-2026!");
		cy.openDesk("/app");
		cy.call(`${method}.seed_parallel_workflow_cypress`).then((res) => {
			Cypress.env("wf", res.body.message);
		});
	});

	after(() => {
		cy.login("wf.approver2@example.com", "Wf-Test-2026!");
		cy.openDesk("/app");
		cy.call(`${method}.cleanup_parallel_workflow_cypress`);
	});

	it("Existing approver is untouched", () => {
		const fixture = load();
		expect(fixture.ikhmel_modified_unchanged).to.eq(true);
		expect(fixture.project_write).to.eq(false);
		expect(fixture.holiday_list_read).to.eq(false);
		expect(fixture.can_write_issue).to.eq(false);
	});

	it("All cohort needs every eligible vote", () => {
		const fixture = load();
		expect(fixture.all_threshold).to.eq(2);
		expect(fixture.all_approvers).to.include.members([fixture.approver, fixture.approver_b]);
		vote(fixture.approver, fixture.all_workflow, fixture.all_issue, fixture.all_action, fixture.all_uuid).then(
			(res) => {
				expect(res.body.message.transitioned).to.eq(false);
			}
		);
		issueStatus(fixture.all_issue).should("eq", "Open");
		vote(
			fixture.approver_b,
			fixture.all_workflow,
			fixture.all_issue,
			fixture.all_action,
			fixture.all_uuid
		).then((res) => {
			expect(res.body.message.transitioned).to.eq(true);
			expect(res.body.message.round_status).to.not.eq("Conflicted");
		});
		issueStatus(fixture.all_issue).should("eq", "Closed");
	});

	it("Empty UUID does not conflict the round", () => {
		const fixture = load();
		expect(fixture.empty_uuid).to.be.a("string").and.not.eq("");
		expect(fixture.empty_uuid_again).to.eq(fixture.empty_uuid);
		expect(fixture.empty_round_status).to.eq("Open");
		asApprover();
		cy.visit(`/app/issue/${fixture.empty_issue}`);
		cy.get(".form-dashboard", { timeout: 60000 }).should("exist");
		cy.contains("Раунд согласования требует пересборки").should("not.exist");
		cy.contains("Approval round needs a rebuild").should("not.exist");
	});

	it("Read-only approver rejects", () => {
		const fixture = load();
		expect(fixture.can_write_issue).to.eq(false);
		const comment = "Cypress read-only reject";
		vote(fixture.approver, fixture.reject_workflow, fixture.reject_issue, fixture.reject_action, fixture.reject_uuid, {
			comment,
		}).then((res) => {
			expect(res.body.message.transitioned).to.eq(true);
			expect(res.body.message.round_status).to.eq("Transitioned");
			cy.call(`${method}.task_snapshot`, { task_name: res.body.message.task }).then((snap) => {
				expect(snap.body.message.vote_comment).to.eq(comment);
				expect(snap.body.message.round_status).to.not.eq("Conflicted");
			});
		});
		issueStatus(fixture.reject_issue).should("eq", "Closed");
	});

	it("Approver opens the workspace", () => {
		const fixture = load();
		asApprover();
		cy.visit(`/app/${encodeURIComponent("мои-согласования")}`);
		cy.document().its("documentElement").invoke("attr", "data-theme").should("match", /dark/i);
		cy.get(".number-widget-box", { timeout: 120000 }).should("have.length", 4);
		cy.get(".number-widget-box .widget-title", { timeout: 120000 }).should(($titles) => {
			expect($titles).to.have.length(4);
			$titles.each((_, el) => {
				const view = el.ownerDocument.defaultView;
				const title = view.getComputedStyle(el);
				const box = view.getComputedStyle(el.closest(".number-widget-box"));
				expect((el.textContent || "").trim()).to.not.eq("");
				expect(title.color).to.not.eq(box.backgroundColor);
			});
		});
		cy.get(".dinext-my-approvals", { timeout: 60000 }).should("contain", "Cypress queue");
		cy.noPermissionDialog();
	});

	it("Pending names after reload", () => {
		const fixture = load();
		asApprover();
		cy.visit(`/app/application-for-leave/${encodeURIComponent(fixture.leave)}`);
		cy.get(".dinext-pending-approvers", { timeout: 60000 })
			.should("contain", fixture.approver_name)
			.and("contain", fixture.approver_b_name);
		cy.visit(`/app/application-for-leave/${encodeURIComponent(fixture.leave)}`);
		cy.get(".dinext-pending-approvers", { timeout: 60000 }).should("contain", fixture.approver_name);
		cy.visit(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
		cy.get(".dinext-pending-approvers", { timeout: 60000 })
			.should("contain", fixture.approver_name)
			.and("contain", fixture.approver_b_name);
		cy.reload();
		cy.get(".dinext-pending-approvers", { timeout: 60000 }).should("contain", fixture.approver_name);
		cy.noPermissionDialog();
	});

	it("Conflicted round is visible", () => {
		const fixture = load();
		asApprover();
		openIssue(fixture.conflicted_issue);
		cy.get(".dinext-pending-approvers", { timeout: 120000 }).should(($el) => {
			const text = $el.text();
			expect(text.includes("Раунд согласования требует пересборки") || text.includes("Approval round needs a rebuild"))
				.to.eq(true);
		});
		cy.get(".dinext-reset-round").should("not.exist");
		cy.intercept("**/api/method/dinext_common.workflow_approval.api.get_form_approval_banner").as("quietBanner");
		openIssue(fixture.quiet_issue);
		cy.wait("@quietBanner");
		cy.get(".dinext-pending-approvers").should("not.exist");
		asApprover(fixture.manager);
		openIssue(fixture.conflicted_issue);
		cy.get(".dinext-reset-round", { timeout: 60000 }).should("exist");
	});

	it("History with a completed task", () => {
		asApprover();
		cy.visit("/app/query-report/My%20Approval%20History");
		cy.get(".dt-row", { timeout: 120000 }).should("have.length.at.least", 1);
		cy.noPermissionDialog();
	});

	it("Monitoring with an empty approver", () => {
		const fixture = load();
		asApprover(fixture.monitor);
		cy.visit("/app/query-report/Approval%20Monitoring");
		cy.get(".dt-row", { timeout: 120000 }).should("have.length.at.least", 1);
		cy.noPermissionDialog();
	});

	it("Approver list renders", () => {
		const fixture = load();
		asApprover();
		cy.visit("/app");
		cy.window().then((win) => {
			win.frappe.route_options = { name: fixture.position };
			win.frappe.set_route("List", "User Timesheet Position");
		});
		cy.get(".dinext-utp-action-select", { timeout: 60000 }).should("exist");
		cy.contains("button", /Apply workflow action|Применить действие согласования/).should("exist");
		cy.noPermissionDialog();
	});

	it("Approver opens a pending timesheet", () => {
		const fixture = load();
		asApprover();
		cy.visit(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
		cy.get(".dinext-pending-approvers", { timeout: 60000 }).should("contain", fixture.approver_name);
		cy.get(".dinext-utp-action-select, .actions-btn-group, .dinext-pending-approvers").should("exist");
		cy.noPermissionDialog();
		cy.contains("Holiday List").should("not.exist");
	});

	it("Inaccessible approver is excluded", () => {
		const fixture = load();
		expect(fixture.cohort_threshold).to.eq(1);
		expect(fixture.cohort_approvers).to.deep.eq([fixture.approver]);
		expect(fixture.cohort_approvers).to.not.include(fixture.excluded);
		asApprover();
		openIssue(fixture.cohort_issue);
		cy.get(".dinext-pending-approvers", { timeout: 120000 })
			.should("contain", fixture.approver_name)
			.and("not.contain", "Cypress Excluded");
	});

	it("Date edit then vote", () => {
		const fixture = load();
		expect(fixture.edit_round_status).to.eq("Open");
		vote(fixture.approver, fixture.edit_workflow, fixture.edit_issue, fixture.edit_action, fixture.edit_uuid).then(
			(res) => {
				expect(res.body.message.transitioned).to.eq(true);
				expect(res.body.message.round_status).to.not.eq("Conflicted");
			}
		);
	});

	it("Reports and timesheet desk", () => {
		const fixture = load();
		asApprover();
		cy.visit("/app/query-report/My%20Approval%20History");
		cy.get(".dt-row", { timeout: 120000 }).should("have.length.at.least", 1);
		asApprover(fixture.monitor);
		cy.visit("/app/query-report/Approval%20Monitoring");
		cy.get(".dt-row", { timeout: 120000 }).should("have.length.at.least", 1);
		asApprover();
		cy.visit("/app");
		cy.window().then((win) => {
			win.frappe.route_options = { name: fixture.position };
			win.frappe.set_route("List", "User Timesheet Position");
		});
		cy.get(".dinext-utp-action-select", { timeout: 60000 }).should("exist");
		cy.visit(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
		cy.get(".dinext-pending-approvers", { timeout: 60000 }).should("exist");
		cy.noPermissionDialog();
	});
});
