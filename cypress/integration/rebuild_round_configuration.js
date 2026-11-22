const helper = "dinext_common.tests.ui_test_helpers";
const api = "dinext_common.workflow_approval.api";
const fixture = () => Cypress.env("rebuildConfiguration");

function openIssue(user, source) {
	cy.login(user, fixture().password);
	cy.openDesk(`/app/issue/${source.name}`);
	cy.window().its("cur_frm.doc.name", { timeout: 120000 }).should("eq", source.name);
}

context("Live configuration conflict and grouped rebuild", () => {
	before(() => {
		cy.login(Cypress.env("bootstrapUser"), Cypress.env("bootstrapPassword"));
		cy.openDesk("/app");
		cy.call(
			`${helper}.seed_live_configuration_conflict_cypress`,
			{},
			{ timeout: 120000 }
		).then((response) => Cypress.env("rebuildConfiguration", response.body.message));
	});

	after(() => {
		cy.login(Cypress.env("bootstrapUser"), Cypress.env("bootstrapPassword"));
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_parallel_workflow_cypress`, {}, { timeout: 120000 });
	});

	it("shows a live conflict before another vote or source save", () => {
		const source = fixture().configuration_issues[0];
		openIssue(fixture().approver, source);
		cy.call("frappe.client.get", { doctype: "Workflow Task", name: source.task })
			.its("body.message.round_status")
			.should("eq", "Open");
		cy.get(".dinext-rebuild-summary").should("have.length", 1).and("be.visible");
		cy.call(`${api}.get_form_approval_banner`, { doctype: "Issue", name: source.name }).then(
			(response) => {
				expect(
					response.body.message.rounds[0].configuration_change.void[0].approvers
				).to.include(fixture().approver_b);
			}
		);
		cy.get(".dinext-reset-rounds").should("not.exist");
	});

	it("keeps conflict metadata after a rejected HTTP vote rolls back", () => {
		const source = fixture().configuration_issues[0];
		openIssue(fixture().approver, source);
		cy.call(
			`${helper}.attempt_conflicted_vote_cypress`,
			{ task_name: source.task },
			{ failOnStatusCode: false }
		).then((response) => {
			expect(response.status).to.eq(417);
			expect(response.body.exc_type).to.eq("WorkflowApprovalConflictError");
		});
		cy.call("frappe.client.get", { doctype: "Workflow Task", name: source.task }).then(
			(response) => {
				const task = response.body.message;
				expect(task.round_status).to.eq("Conflicted");
				expect(task.status).to.eq("Working");
			}
		);
		cy.call("frappe.client.get_value", {
			doctype: "Issue",
			filters: { name: source.name },
			fieldname: "status",
		})
			.its("body.message.status")
			.should("eq", "Open");
		cy.call("frappe.client.get", { doctype: "Issue", name: source.name }).then((response) => {
			expect(response.body.message.description || "").not.to.contain(
				"Cypress rejected temporary change"
			);
		});
	});

	it("one compact control rebuilds two independent live-conflicted sources", () => {
		const sources = fixture().configuration_issues.slice(1);
		openIssue(fixture().manager, sources[0]);
		cy.get(".dinext-rebuild-summary").should("have.length", 1).and("be.visible");
		cy.call(`${api}.get_form_approval_banner`, {
			doctype: "Issue",
			name: sources[1].name,
		}).then((response) => {
			const second = response.body.message.rounds;
			cy.call(`${api}.get_form_approval_banner`, {
				doctype: "Issue",
				name: sources[0].name,
			}).then((first) => {
				cy.window().then((win) => {
					const host = win
						.$('<div class="cypress-grouped-rebuild"></div>')
						.prependTo(win.cur_frm.page.wrapper.find(".page-body"));
					win.frappe.dinext.paintRebuildRounds(
						{ parent: host },
						[...first.body.message.rounds, ...second],
						{
							container: host,
							reload: () => win.cur_frm.reload_doc(),
						}
					);
				});
			});
		});
		cy.get(".cypress-grouped-rebuild .dinext-rebuild-summary").should("have.length", 1);
		cy.get(".cypress-grouped-rebuild .dinext-reset-rounds")
			.should("have.length", 1)
			.and("be.visible")
			.click();
		const reason = "Repair all configuration conflicts";
		cy.get('.modal:visible textarea[data-fieldname="reason"]')
			.type(reason)
			.should("have.value", reason)
			.trigger("change");
		cy.window().should((win) => expect(win.cur_dialog.get_value("reason")).to.eq(reason));
		cy.intercept(`**/api/method/${api}.reset_rounds`).as("batchReset");
		cy.get(".modal:visible .btn-primary").click();
		cy.wait("@batchReset", { requestTimeout: 15000 }).then(({ response }) => {
			expect(response.statusCode).to.eq(200);
			expect(response.body.message.succeeded).to.have.members(
				sources.map((source) => source.round_id)
			);
			expect(response.body.message.failed).to.have.length(0);
		});
		cy.get(".dinext-rebuild-summary, .dinext-rebuild-round").should("not.exist");
		for (const source of sources) {
			cy.call(`${api}.get_form_approval_banner`, { doctype: "Issue", name: source.name })
				.its("body.message.rounds")
				.should("have.length", 0);
		}
	});
});
