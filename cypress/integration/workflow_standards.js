let fixture;

describe('Workflow standards audit regressions', () => {
    before(() => cy.task('deadlineSeed').then(result => { fixture = result; }));
    after(() => cy.task('deadlineCleanup'));

    it('rejects an empty daily deadline time in Russian and saves a corrected schedule', () => {
        cy.login(fixture.editor, fixture.password);
        cy.visit('/app/workflow/' + encodeURIComponent(fixture.workflow));
        cy.window().should(w => expect(w.cur_frm?.doc.name).to.equal(fixture.workflow));
        cy.window().then(w => w.cur_frm.fields_dict.transitions.grid.grid_rows[0].toggle_view(true));
        cy.window().then(w => w.cur_frm.fields_dict.transitions.grid.grid_rows[0]
            .grid_form.fields_dict.custom_deadline_send_times.set_value(''));
        cy.intercept('POST', '**/frappe.desk.form.save.savedocs').as('invalidSchedule');
        cy.window().then(w => { w.cur_frm.ignore_warning = true; return w.cur_frm.save(); });
        cy.wait('@invalidSchedule').its('response.statusCode').should('eq', 417);
        cy.window().should(w => {
            expect(w.cur_frm.is_dirty()).to.be.ok;
            expect(w.__('Digest send time is required for daily delivery')).not.to.equal('Digest send time is required for daily delivery');
        });
        cy.window().then(w => cy.contains('.msgprint:visible', w.__('Digest send time is required for daily delivery')).should('be.visible'));
        cy.screenshot('daily-deadline-validation-ru');
        cy.get('.modal:visible .btn-modal-close').click();
        cy.window().then(w => w.frappe.model.set_value('Workflow Transition',
            w.cur_frm.doc.transitions[0].name, 'custom_deadline_send_times', '17:00, 08:00, 08:00'));
        cy.window().then(w => w.cur_frm.save());
        cy.reload();
        cy.window().should(w => expect(w.cur_frm?.doc.transitions[0].custom_deadline_send_times).to.equal('08:00, 17:00'));
    });

    it('renders standard diagnostic errors in RU and EN through the native report table and runtime themes', () => {
        cy.task('deadlineDiagnostics').then(datasets => {
            const profiles = [
                {user: fixture.editor, language: 'ru'},
                {user: fixture.locale_users.find(row => row.language === 'en').user, language: 'en'},
            ];
            for (const profile of profiles) {
                cy.login(profile.user, fixture.password);
                cy.intercept('**/api/method/frappe.desk.query_report.run*', {body: {message: datasets[profile.language]}}).as('diagnosticReport');
                cy.visit('/app/query-report/Approval Deadline Discipline');
                cy.wait('@diagnosticReport');
                cy.window().should(w => {
                    const values = w.frappe.query_report.data.map(row => row.deadline_error);
                    expect(values).to.deep.equal(datasets[profile.language].result.map(row => row.deadline_error));
                    if (profile.language === 'ru') {
                        expect(values[0]).not.to.equal('Original assignment time is unknown');
                        expect(values[1]).not.to.include('Worker is missing');
                    }
                });
                cy.window().then(w => cy.contains('.report-summary', w.__('No observations')).should('be.visible'));
                cy.get('.dt-scrollable').scrollTo('right', {ensureScrollable: false});
                cy.contains('.dt-cell__content', datasets[profile.language].result[0].deadline_error).should('be.visible');
                for (const theme of ['light', 'dark', 'light']) {
                    cy.window().then(w => w.frappe.ui.set_theme(theme));
                    cy.get('.datatable').should('be.visible');
                    cy.screenshot('deadline-diagnostics-' + profile.language + '-' + theme);
                }
            }
        });
    });

    it('denies retention over GET and denies an ordinary approver over POST', () => {
        const url = '/api/method/dinext_common.workflow_approval.retention.cleanup_workflow_approval_rounds';
        cy.login(fixture.editor, fixture.password);
        cy.request({url, method: 'GET', failOnStatusCode: false}).its('status').should('eq', 403);
        cy.login(fixture.ordinary_user, fixture.password);
        cy.visit('/app');
        cy.call('dinext_common.workflow_approval.retention.cleanup_workflow_approval_rounds', {}, {failOnStatusCode: false})
            .its('status').should('eq', 403);
    });
});
