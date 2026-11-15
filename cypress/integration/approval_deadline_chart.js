let fixture;

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

        cy.contains('.chart-container .x.axis text', '2026-11-09').should('be.visible');
        for (const theme of ['light', 'dark', 'light']) {
            cy.window().then(w => w.frappe.ui.set_theme(theme));
            cy.get('html').should('have.attr', 'data-theme', theme);
            cy.get('.chart-container .dataset-line circle[data-point-index="0"]', {timeout: 5000})
                .should('have.length', 1).and('be.visible');
        }
    });
});
