let fixture;
const cards = {
    "my-approvals": ["Overdue Approval Assignments", "On-time Approvals", "Approvals Completed Late", "Approval Deadline Errors"],
    "my-timesheets": ["Overdue Timesheets", "On-time Timesheet Submissions", "On-time Timesheet Approvals", "Overdue Timesheet Approvals", "Overdue Timesheet Positions", "Timesheet Hours Awaiting Approval"],
};
const charts = ["Overdue Timesheet Submissions by Author", "Overdue Timesheet Approvals by Approver"];

describe("Standard deadline workspace controls", () => {
    before(() => cy.task("emailLayoutSeed").then(r => { fixture = r; }));
    after(() => cy.task("emailLayoutCleanup"));
    for (const language of ["ru", "en"]) {
        for (const route of ["my-timesheets", "my-approvals"]) {
            it(route + " in " + language + " has valid cards and chart labels in both themes", () => {
                const user = fixture.locales.find(p => p.language === language).user;
                cy.login(user, fixture.password);
                cy.visit("/app/" + route);
                cy.window().should(w => expect(w.frappe.boot.lang).to.equal(language));
                cy.window().then(w => {
                    for (const name of cards[route]) {
                        cy.contains(".number-widget-box", w.__(name)).find(".number").should($number => {
                            const text = $number.text().trim();
                            expect(text).not.to.equal("");
                            expect(text).not.to.match(/N\/A|Н\/Д|undefined|NaN|[₽$€]/);
                        });
                    }
                    if (route === "my-timesheets") {
                        cy.contains(".ce-header", w.__("Deadline Control")).should("exist");
                        for (const chart of charts) cy.contains(".dashboard-widget-box", w.__(chart).slice(0, 24)).should("exist");
                        cy.get(".ce-header").then($headers => {
                            const text = [...$headers].map(x => x.textContent.trim());
                            expect(text.slice(-3)).to.deep.equal([w.__("Deadline Control"), w.__("Timesheet Reports"), w.__("Timesheet Configuration")]);
                        });
                    }
                });
                cy.get(".dashboard-widget-box").should("have.length", route === "my-timesheets" ? 2 : 6);
                if (route === "my-timesheets") {
                    cy.get(".dashboard-widget-box").first().scrollIntoView().find(".bar").first()
                        .trigger("mousemove", "center", {force:true, eventConstructor:"MouseEvent"});
                    cy.get(".graph-svg-tip:visible").should("exist").invoke("text").should("not.match", /[₽$€]|RUB/);
                }
                cy.get(".dashboard-widget-box").invoke("text").should("not.include", "undefined");
                cy.window().then(w => {
                    for (const name of route === "my-timesheets" ? charts : ["Approval Deadline Discipline Trend"]) {
                        expect(w.frappe.get_doc("Dashboard Chart", name).currency).not.to.be.ok;
                    }
                });
                cy.get(".msgprint:visible").should("not.exist");
                for (const theme of ["light", "dark"]) {
                    cy.window().then(w => w.frappe.ui.set_theme(theme));
                    cy.window().then(w => {
                        if (route === "my-timesheets") cy.contains(".ce-header", w.__("Deadline Control")).scrollIntoView();
                        else cy.contains(".number-widget-box", w.__("Overdue Approval Assignments")).scrollIntoView();
                    });
                    cy.screenshot("workspace-" + route + "-" + language + "-" + theme);
                    if (route === "my-timesheets") {
                        cy.window().then(w => cy.contains(".ce-header", w.__("Timesheet Reports")).scrollIntoView());
                        cy.screenshot("workspace-reports-" + language + "-" + theme);
                    }
                }
                if (route === "my-timesheets") {
                    cy.window().then(w => cy.contains(".shortcut-widget-box", w.__("Timesheet Deadline Discipline")).click());
                    cy.url().should("include", "Timesheet%20Deadline%20Discipline");
                    cy.window().should(w => expect(w.frappe.query_report?.report_name).to.equal("Timesheet Deadline Discipline"));
                }
            });
        }
    }
    it("explains empty percentages for an ordinary worker", () => {
        cy.login(fixture.ordinary_user, fixture.password);
        for (const route of ["my-approvals", "my-timesheets"]) {
            cy.visit("/app/" + route);
            cy.window().then(w => {
                expect(w.frappe.user_roles).not.to.include("System Manager");
                const names = route === "my-approvals" ? ["On-time Approvals"] : ["On-time Timesheet Submissions", "On-time Timesheet Approvals"];
                for (const name of names) cy.contains(".number-widget-box", w.__(name)).find(".number").should("have.text", w.__("No observations"));
            });
            cy.get(".dashboard-widget-box").invoke("text").should("not.include", "undefined");
        }
    });
});
