let fixture;

function assertWeeklyMarker(chart) {
    cy.contains(`${chart} .x.axis text`, '2026-11-09').should('be.visible');
    for (const theme of ['light', 'dark', 'light']) {
        cy.window().then(w => w.frappe.ui.set_theme(theme));
        cy.get('html').should('have.attr', 'data-theme', theme);
        cy.get(`${chart} .dataset-line circle[data-point-index="0"]`, {timeout: 5000})
            .should('have.length', 1).and('be.visible');
    }
}

describe('Approval Deadline Discipline chart', () => {
    before(() => cy.task('deadlineSeed').then(result => { fixture = result; }));
    after(() => cy.task('deadlineCleanup'));

    it('shows a single weekly value in both report themes', () => {
        cy.login(fixture.editor, fixture.password);
        cy.task('deadlineDiagnostics').then(({single_week}) => {
            cy.intercept('**/api/method/frappe.desk.query_report.run*', {
                body: {message: single_week},
            }).as('disciplineReport');
            cy.visit('/app/query-report/Approval Deadline Discipline');
            cy.wait('@disciplineReport');
        });

        assertWeeklyMarker('.chart-container');
    });

    it('shows a single weekly value in the My Approvals widget', () => {
        const user = fixture.locale_users.find(profile => profile.language === 'en').user;
        cy.login(user, fixture.password);
        cy.task('deadlineDiagnostics').then(({single_week}) => {
            cy.intercept('POST', '**/api/method/frappe.desk.query_report.run', request => {
                const report = typeof request.body === 'string'
                    ? new URLSearchParams(request.body).get('report_name') : request.body?.report_name;
                if (report === 'Approval Deadline Discipline') {
                    request.alias = 'workspaceDiscipline';
                    request.reply({body: {message: single_week}});
                }
            });
            cy.visit('/app/my-approvals');
            cy.wait('@workspaceDiscipline');
        });

        const widget = '[chart_name="Approval Deadline Discipline Trend"] .dashboard-widget-box';
        cy.get(widget).scrollIntoView().should('be.visible');
        assertWeeklyMarker(`${widget} .chart-container`);
    });
});
