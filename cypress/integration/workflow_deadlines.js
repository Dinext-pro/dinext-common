let fixture;
const open = () => {
    cy.login(fixture.editor, fixture.password);
    cy.visit('/app/workflow/' + encodeURIComponent(fixture.workflow));
    cy.window().should(w => expect(w.cur_frm?.doc.name).to.equal(fixture.workflow));
};
const row = index => cy.window().then(w => w.cur_frm.fields_dict.transitions.grid.grid_rows[index]);
const save = () => {
    cy.window().then(w => { w.cur_frm.ignore_warning = true; return w.cur_frm.save(); });
    cy.window().should(w => expect(w.cur_frm.is_dirty()).to.equal(false));
};

describe('Workflow deadline settings and discipline', () => {
    before(() => cy.task('deadlineSeed').then(result => { fixture = result; }));
    after(() => cy.task('deadlineCleanup'));

    it('loads installed extensions, normalizes schedule and saves a mixed profile', () => {
        open();
        cy.window().should(w => {
            expect(w.cur_frm.deadline_options?.deadline_intervals.map(x => x.value)).to.include('Working Days');
            expect(w.cur_frm.deadline_options?.recipients.map(x => x.value)).to.include('Worker Group Manager');
        });
        row(0).then(r => r.toggle_view(true));
        row(0).should(r => {
            expect(r.doc.custom_deadline_send_times).to.equal('08:00, 17:00');
            expect(r.grid_form.fields_dict.custom_deadline_send_times.$wrapper.is(':visible')).to.equal(true);
        });
        row(0).then(r => r.grid_form.fields_dict.custom_deadline_interval_unit.set_value('Hours'));
        row(0).should(r => expect(r.grid_form.fields_dict.custom_deadline_send_times.$wrapper.is(':visible')).to.equal(false));
        row(0).then(r => r.grid_form.fields_dict.custom_deadline_email_mode.set_value('Immediate'));
        row(0).should(r => expect(r.grid_form.fields_dict.custom_deadline_interval_unit.$wrapper.is(':visible')).to.equal(false));
        save();
        cy.reload();
        cy.window().should(w => expect(w.cur_frm?.doc.transitions[0].custom_deadline_email_mode).to.equal('Immediate'));
        row(1).then(r => r.toggle_view(true));
        cy.window().should(w => {
            const r = w.cur_frm.fields_dict.transitions.grid.grid_rows[1];
            const section = r.grid_form.layout.sections_dict.custom_deadline_section;
            const control = r.grid_form.fields_dict.custom_deadline_enabled;
            const target = w.cur_frm.doc.states.find(s => s.state === r.doc.next_state);
            expect(control.$wrapper.is(':visible'), JSON.stringify({target:r.doc.next_state, optional:target?.is_optional_state, hidden:section?.df.hidden, sectionClass:section?.wrapper.attr('class'), actualSection:control.$wrapper.closest('.form-section').attr('data-fieldname')})).to.equal(false);
        });
    });

    it('keeps next-action template in the email section and supports both themes', () => {
        open();
        cy.window().then(w => w.cur_frm.fields_dict.states.grid.grid_rows[1].toggle_view(true));
        cy.window().should(w => {
            const form = w.cur_frm.fields_dict.states.grid.grid_rows[1].grid_form;
            const field = form.fields_dict.next_action_email_template;
            expect(field.$wrapper.is(':visible')).to.equal(true);
            expect(field.$wrapper.closest('.form-section').text()).to.include(w.__('Workflow Approval Email'));
        });
        for (const theme of ['light', 'dark', 'light']) {
            cy.window().then(w => { w.document.documentElement.dataset.theme = theme; });
            cy.window().then(w => cy.wrap(w.cur_frm.fields_dict.states.grid.grid_rows[1].grid_form.wrapper)
                .screenshot('deadline-state-email-' + theme));
        }
    });

    it('uses the standard Workflow checkbox in Notification Settings', () => {
        cy.login(fixture.editor, fixture.password);
        cy.visit('/app/notification-settings/' + fixture.editor);
        cy.window().should(w => expect(w.cur_frm?.doc.name).to.equal(fixture.editor));
        cy.get('[data-fieldname="email_notification_types_html"] input[data-unit="Workflow"]').should('have.length', 1);
        cy.get('[data-fieldname="email_notification_types_html"]').screenshot('workflow-notification-standard-checkbox');
    });

    for (const route of ['my-approvals', 'my-timesheets', 'query-report/Approval Deadline Discipline', 'query-report/Timesheet Deadline Discipline']) {
        it('opens ' + route + ' with permission-filtered data', () => {
            cy.login(fixture.editor, fixture.password);
            if (route.startsWith('query-report/')) {
                cy.intercept('**/api/method/frappe.desk.query_report.run*').as('disciplineReport');
            }
            cy.visit('/app/' + route);
            cy.get('.page-head:visible').should('exist');
            if (route.startsWith('query-report/')) {
                cy.wait('@disciplineReport', {requestTimeout:30000}).its('response.body.message.columns').should('have.length.at.least', 5);
            } else {
                const names = route === 'my-approvals'
                    ? ['Просроченные согласования', 'Согласования в срок', 'Согласования с опозданием', 'Ошибки расчёта сроков']
                    : ['Таймшиты, отправленные в срок', 'Таймшиты, согласованные в срок', 'Таймшиты с просроченным согласованием', 'Просроченные позиции таймшитов', 'Часы таймшитов на согласовании'];
                for (const name of names) {
                    cy.contains('.number-widget-box', name).find('.number').invoke('text').should('not.be.empty');
                }
            }
            cy.get('.msgprint:visible').should('not.exist');
            cy.get('#freeze:visible, .modal-backdrop:visible').should('not.exist');
            if (!route.startsWith('query-report/')) {
                cy.contains('.number-widget-box', route === 'my-approvals'
                    ? 'Просроченные согласования' : 'Таймшиты, отправленные в срок').scrollIntoView().should('be.visible');
            }
            for (const theme of ['light', 'dark']) {
                cy.window().then(w => w.frappe.ui.set_theme(theme));
                cy.screenshot('deadline-' + route.replaceAll('/', '-') + '-' + theme);
            }
        });
    }

    it('shows all nine deadline cards to an ordinary worker without System Manager', () => {
        cy.login(fixture.ordinary_user, fixture.password);
        for (const route of ['my-approvals', 'my-timesheets']) {
            cy.visit('/app/' + route);
            cy.window().should(w => expect(w.frappe.user_roles).not.to.include('System Manager'));
            const names = route === 'my-approvals'
                ? ['Просроченные согласования', 'Согласования в срок', 'Согласования с опозданием', 'Ошибки расчёта сроков']
                : ['Таймшиты, отправленные в срок', 'Таймшиты, согласованные в срок', 'Таймшиты с просроченным согласованием', 'Просроченные позиции таймшитов', 'Часы таймшитов на согласовании'];
            for (const name of names) {
                cy.contains('.number-widget-box', name).find('.number').should($number => {
                    const text = $number.text().trim();
                    expect(text).not.to.match(/[₽$€]/);
                    expect(/^[\d\s.,%]+$/.test(text) || ['Нет наблюдений', 'No observations'].includes(text), text).to.equal(true);
                });
            }
            cy.get('.msgprint:visible').should('not.exist');
            for (const theme of ['light', 'dark']) {
                cy.window().then(w => w.frappe.ui.set_theme(theme));
                cy.screenshot('ordinary-worker-' + route + '-' + theme);
            }
        }
    });

    it('loads English and system-language forms, reports and workspaces', () => {
        for (const profile of fixture.locale_users) {
            cy.login(profile.user, fixture.password);
            cy.visit('/app/workflow/' + encodeURIComponent(fixture.workflow));
            cy.window().should(w => expect(w.cur_frm?.doc.name).to.equal(fixture.workflow));
            row(0).then(r => r.toggle_view(true));
            cy.window().should(w => {
                const label = w.cur_frm.fields_dict.transitions.grid.grid_rows[0].grid_form.layout.sections_dict.custom_deadline_section.head.text();
                const language = profile.language === 'system' ? fixture.system_ui_language : profile.language;
                expect(label).to.include(language === 'ru' ? 'Срок согласования' : 'Approval Deadline');
            });
            cy.screenshot('deadline-form-' + profile.language);
            cy.visit('/app/notification-settings/' + profile.user);
            cy.get('[data-fieldname="email_notification_types_html"] input[data-unit="Workflow"]').should('have.length', 1);
            for (const route of ['my-approvals', 'my-timesheets']) {
                cy.visit('/app/' + route);
                cy.window().then(w => {
                    const label = w.__(route === 'my-approvals' ? 'Overdue Approval Assignments' : 'On-time Timesheet Submissions');
                    cy.contains('.number-widget-box', label).find('.number').invoke('text').should('not.be.empty');
                });
                cy.get('#freeze:visible, .modal-backdrop:visible').should('not.exist');
            }
            for (const report of ['Approval Deadline Discipline', 'Timesheet Deadline Discipline']) {
                cy.intercept('**/api/method/frappe.desk.query_report.run*').as('localeReport');
                cy.visit('/app/query-report/' + report);
                cy.wait('@localeReport', {requestTimeout:30000}).its('response.body.message.columns').should('have.length.at.least', 5);
                cy.get('.msgprint:visible').should('not.exist');
            }
        }
    });

    it('renders all seven templates in recipient languages at desktop and mobile widths', () => {
        cy.login(fixture.editor, fixture.password);
        cy.visit('/app');
        cy.task('deadlinePreviews').then(previews => {
            expect(previews).to.have.length(21);
            for (const email of previews) {
                for (const width of [1024, 360, 390, 430]) {
                    cy.viewport(width, 1000);
                    cy.document().then(doc => {
                        doc.head.innerHTML = '<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0}</style>';
                        doc.body.innerHTML = email.html;
                    });
                    cy.get('h1').should('be.visible');
                    cy.contains('Dinext').should('exist');
                    cy.document().should(doc => expect(doc.documentElement.scrollWidth).to.be.at.most(width));
                    if (email.name.includes('Correction') || email.name.includes('Deadline')) {
                        cy.get('a[href*="preview_action"]').should('not.exist');
                    }
                    if (email.language === 'ru') {
                        cy.screenshot(email.name.replaceAll(' ', '-') + '-' + width);
                        if (width === 360) {
                            cy.get('img').invoke('hide');
                            cy.screenshot(email.name.replaceAll(' ', '-') + '-images-off');
                        }
                    }
                }
            }
        });
    });
});
