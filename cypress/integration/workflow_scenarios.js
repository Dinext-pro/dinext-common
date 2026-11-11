const fixture = () => Cypress.env("workflowScenarios");
const contextMethod = "dinext_common.workflow_approval.scenarios.api.get_workflow_context";

const openSource = (name) => {
	cy.window().then(win => win.frappe.set_route("Form", fixture().doctype, name));
	cy.window().should(win => {
		expect(win.cur_frm?.doc?.name).to.equal(name);
		expect(win.frappe.get_route().slice(2).join("/")).to.equal(name);
	});
};

context("multiple active workflow scenarios", () => {
	before(() => cy.task("scenarioSeed").then(data => Cypress.env("workflowScenarios", data)));
	after(() => cy.task("scenarioCleanup"));
	beforeEach(() => {
		cy.login(fixture().user, fixture().password);
		cy.openDesk(`/app/cypress-scenario-source/${fixture().documents.a_form}`);
		cy.window().should(win => expect(win.cur_frm?.doc?.name).to.equal(fixture().documents.a_form));
	});

	it("uses the correct field and edit role on first render and same-type navigation", () => {
		const data = fixture();
		openSource(data.documents.a_form);
		cy.window().should(win => {
			expect(win.cur_frm.state_fieldname).to.equal(data.state_fields[0]);
			expect(win.cur_frm.read_only).to.equal(false);
		});
		cy.contains(".indicator-pill, .indicator", "Scenario Waiting A").should("be.visible");
		openSource(data.documents.b_form);
		cy.window().should(win => {
			expect(win.cur_frm.state_fieldname).to.equal(data.state_fields[1]);
			expect(win.cur_frm.states.state_fieldname).to.equal(data.state_fields[1]);
			expect(win.cur_frm.read_only).to.equal(true);
		});
		cy.contains(".indicator-pill, .indicator", "Scenario Waiting B").should("be.visible");
		cy.screenshot("workflow-scenarios-en-first-render", { capture: "viewport" });
		openSource(data.documents.a_form);
		cy.window().should(win => expect(win.cur_frm.read_only).to.equal(false));
		cy.noPermissionDialog();
	});

	it("applies one shared action with distinct UUIDs and a mandatory shared comment", () => {
		const data = fixture();
		const names = [data.documents.a_list, data.documents.b_list];
		cy.window().then(win => win.frappe.set_route("List", data.doctype, "List"));
		cy.window().should(win => {
			expect(win.cur_list?.doctype).to.equal(data.doctype);
			expect(win.cur_list?.filter_area?.add).to.be.a("function");
		});
		cy.window().then(async win => {
			await win.cur_list.filter_area.clear(false);
			await win.cur_list.filter_area.set([[data.doctype, "name", "in", names]]);
			win.cur_list.last_args = null;
			await win.cur_list.refresh();
		});
		for (const name of names) cy.get(`.list-row-checkbox[data-name="${name}"]`).check({ force: true });
		cy.get(".page-container:visible .actions-btn-group button:visible").first().click();
		cy.contains(".dinext-list-workflow-item", "Approve").should("be.visible").click();
		cy.get(".modal:visible textarea[data-fieldname='comment']").type("Cypress mixed scenario decision").blur();
		cy.intercept("POST", "**/api/method/frappe.model.workflow.bulk_workflow_approval").as("mixedVote");
		cy.get(".modal:visible .btn-primary").click();
		cy.wait("@mixedVote").then(({ request }) => {
			const body = typeof request.body === "string" ? JSON.stringify(Object.fromEntries(new URLSearchParams(request.body))) : JSON.stringify(request.body);
			for (const uuid of data.uuids) expect(body).to.include(uuid);
			for (const workflow of data.workflows) expect(body).to.include(workflow);
		});
		for (let index = 0; index < names.length; index += 1) {
			cy.call("frappe.client.get_value", { doctype: data.doctype, filters: names[index], fieldname: data.state_fields[index] })
				.its(`body.message.${data.state_fields[index]}`).should("eq", `Scenario Done ${index ? "B" : "A"}`);
		}
		cy.window().should(win => {
			expect(win.frappe.dom.freeze_count).to.equal(0);
			expect(win.cur_list.page.wrapper[0].inert).to.equal(false);
		});
	});

	it("prepares a distinct repeated process and submits the menu's original process identity", () => {
		const data = fixture();
		const name = data.documents.a_repeat;
		let initial;
		cy.call(contextMethod, { doctype: data.doctype, name }).then(response => { initial = response.body.message.context; });
		openSource(name);
		cy.intercept("POST", "**/api/method/frappe.model.workflow.apply_workflow").as("repeatVote");
		cy.contains(".actions-btn-group .dropdown-item", "Approve").click({ force: true });
		cy.wait("@repeatVote").then(({ request }) => {
			const body = typeof request.body === "string" ? decodeURIComponent(request.body) : JSON.stringify(request.body);
			expect(body).to.include(initial.process_id);
		});
		cy.call(contextMethod, { doctype: data.doctype, name }).then(response => {
			const next = response.body.message.context;
			expect(next.workflow).to.equal(initial.workflow);
			expect(next.process_id).to.not.equal(initial.process_id);
			expect(next.state).to.equal("Scenario Waiting A");
		});
	});

	it("discards a delayed common-action response after the selection changes", () => {
		const data = fixture();
		const names = [data.documents.a_form, data.documents.b_form];
		cy.window().then(win => win.frappe.set_route("List", data.doctype, "List"));
		cy.window().should(win => {
			expect(win.cur_list?.doctype).to.equal(data.doctype);
			expect(win.cur_list?.filter_area?.add).to.be.a("function");
		});
		cy.window().then(async win => {
			await win.cur_list.filter_area.clear(false);
			await win.cur_list.filter_area.set([[data.doctype, "name", "in", names]]);
			win.cur_list.last_args = null;
			await win.cur_list.refresh();
		});
		for (const name of names) cy.get(`.list-row-checkbox[data-name="${name}"]`).check({ force: true });
		cy.intercept("POST", "**/api/method/dinext_common.workflow_approval.api.get_common_list_transitions",
			request => request.continue(response => response.setDelay(1000))).as("delayedActions");
		cy.get(".page-container:visible .actions-btn-group button:visible").first().click();
		cy.get(`.list-row-checkbox[data-name="${names[1]}"]`).uncheck({ force: true });
		cy.wait("@delayedActions").its("response.body.message").should("have.length", 1);
		cy.get(".dinext-list-workflow-item").should("not.exist");
	});

	it("keeps Russian action labels and indicators readable while switching themes", () => {
		const data = fixture();
		cy.login(data.russian_user, data.password);
		cy.openDesk(`/app/cypress-scenario-source/${data.documents.a_form}`);
		openSource(data.documents.a_form);
		cy.window().should(win => expect(win.frappe.boot.lang).to.equal("ru"));
		for (const [index, theme] of ["light", "dark", "light"].entries()) {
			cy.window().then(win => win.frappe.ui.set_theme(theme));
			cy.document().its("documentElement").invoke("attr", "data-theme").should("eq", theme);
			cy.contains(".indicator-pill, .indicator", "Scenario Waiting A").should("be.visible");
			cy.window().then(win => {
				const translated = win.__("Approve");
				expect(translated).to.not.equal("Approve");
				cy.contains(".actions-btn-group .dropdown-item", translated).should("exist");
			});
			if (index < 2) cy.screenshot(`workflow-scenarios-ru-${theme}`, { capture: "viewport" });
		}
		cy.noPermissionDialog();
	});

	it("suggests the next order for a new Workflow and preserves a manual order", () => {
		const data = fixture();
		cy.login(data.designer, data.password);
		cy.openDesk("/app/workflow");
		cy.window().then(win => win.frappe.new_doc("Workflow"));
		cy.window().should(win => expect(win.cur_frm?.doctype).to.equal("Workflow"));
		cy.window().then(win => win.cur_frm.set_value("document_type", data.doctype));
		cy.window().should(win => expect(win.cur_frm.doc.custom_selection_order).to.equal(3));
		cy.window().then(async win => {
			await win.cur_frm.set_value("custom_selection_order", 27);
			await win.cur_frm.trigger("document_type");
		});
		cy.window().should(win => expect(win.cur_frm.doc.custom_selection_order).to.equal(27));
	});
});
