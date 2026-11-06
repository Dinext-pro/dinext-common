Cypress.removeAllListeners("uncaught:exception");

const workflows = {
	"AFL Workflow": {
		states: ["Editing", "Pending Approval", "Approved", "Rejected"],
		actions: ["Submit for Approval", "Approve", "Reject", "Stop Workflow"],
	},
	"UTP Workflow": {
		states: ["Editing", "Pending Approval", "Approved", "Rejected"],
		actions: ["Submit for Approval", "Approve", "Reject", "Stop Workflow", "Edit"],
	},
	Expense_Claim_Workflow: {
		states: ["Draft", "Pending Approval", "Approved", "Rejected"],
		actions: ["Submit for Approval", "Approve", "Reject"],
	},
};
const stateStyles = {
	Draft: ["Черновик", "info"],
	Editing: ["Редактирование", "primary"],
	"Pending Approval": ["На согласовании", "warning"],
	Approved: ["Согласовано", "success"],
	Rejected: ["Отклонено", "danger"],
};
const actionIcons = {
	"Submit for Approval": ["Передать на согласование", "arrow-up-right"],
	Approve: ["Согласовать", "check"],
	Reject: ["Отклонить", "close"],
	"Stop Workflow": ["Остановить согласование", "reply"],
	Edit: ["Редактировать", "edit"],
};

const helper = "dinext_common.tests.workflow_localization_ui";

describe("Localized approval workflows", () => {
	let fixture;
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed`).then((res) => {
			fixture = res.body.message;
		});
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup`);
	});

	for (const language of ["en", "ru"]) {
		for (const [workflow, expected] of Object.entries(workflows)) {
			it(`uses stored English values and renders the ${language} actions for ${workflow}`, () => {
				cy.login(fixture.users[language], fixture.password);
				cy.visit(`/app/workflow/${encodeURIComponent(workflow)}`);
				cy.window().should((win) => {
					const doc = win.cur_frm?.doc;
					expect(doc?.name).to.eq(workflow);
					expect(win.frappe.boot.lang).to.eq(language);
					expect(doc.states.map((row) => row.state)).to.have.members(expected.states);
					expect([...new Set(doc.transitions.map((row) => row.action))]).to.have.members(
						expected.actions
					);
					for (const row of doc.states) {
						const [label, style] = stateStyles[row.state];
						expect(win.__(row.state)).to.eq(language === "ru" ? label : row.state);
						expect(win.frappe.boot.workflow_state_styles[row.state].toLowerCase()).to.eq(style);
						expect(row.is_optional_state).to.eq(
							Number(["Draft", "Editing", "Rejected"].includes(row.state))
						);
					}
					for (const row of doc.transitions) {
						const [label, icon] = actionIcons[row.action];
						expect(win.frappe.boot.workflow_action_icons[row.action]).to.eq(icon);
						const html = win.frappe.dinext.workflowTransitionLabel(row);
						const template = win.document.createElement("template");
						template.innerHTML = html;
						const rendered = template.content.firstElementChild;
						expect(rendered.textContent.trim()).to.eq(language === "ru" ? label : row.action);
						expect(rendered.dataset.workflowStyle).to.eq(stateStyles[row.next_state][1]);
						const glyph = rendered.querySelector("svg use");
						expect(glyph?.getAttribute("href") || glyph?.getAttribute("xlink:href")).to.be.oneOf(
							icon === "close" ? ["#icon-close", "#icon-close-alt"] : [`#icon-${icon}`]
						);
					}
				});
			});
		}
	}
});
