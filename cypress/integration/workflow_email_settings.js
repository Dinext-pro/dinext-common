Cypress.removeAllListeners('uncaught:exception');
let fixture;
const open = () => {
    cy.viewport(1440, 1000);
    cy.login(fixture.editor, fixture.password);
    cy.visit('/app/workflow/' + encodeURIComponent(fixture.workflow));
    cy.window().should(w => expect(w.cur_frm?.doc.name).to.equal(fixture.workflow));
};
const rowForm = () => cy.window().then(w => w.cur_frm.fields_dict.states.grid.grid_rows[0]);
const expand = index => cy.window().then(w => w.cur_frm.fields_dict.states.grid.grid_rows[index].toggle_view(true));
const save = () => {
    cy.window().then(w => {w.cur_frm.ignore_warning = true; return w.cur_frm.save();});
    cy.window().should(w => expect(w.cur_frm.is_dirty()).to.equal(false));
};
const reload = () => {cy.reload(); cy.window().should(w => expect(w.cur_frm?.doc.name).to.equal(fixture.workflow));};

describe('Workflow email state settings', () => {
    before(() => cy.task('emailProfileSeed').then(r => {fixture = r;}));
    after(() => cy.task('emailProfileCleanup'));

    it('inherits, overrides immediate mode, saves and resets without changing state gate', () => {
        open();
        cy.window().should(w => {
            expect(w.cur_frm.doc.states[0].custom_email_settings_override).to.equal(0);
            expect(w.cur_frm.doc.states[0].custom_group_send_times).to.equal('08:00, 17:00');
            expect(w.cur_frm.fields_dict.custom_group_send_times.$wrapper.is(':visible')).to.equal(true);
        });
        expand(0);
        rowForm().then(r => r.grid_form.fields_dict.custom_group_workflow_action_emails.set_value(0));
        cy.window().should(w => expect(w.cur_frm.doc.states[0].custom_email_settings_override).to.equal(1));
        rowForm().should(r => {
            expect(r.grid_form.fields_dict.next_action_email_template.$wrapper.is(':visible')).to.equal(true);
            expect(r.grid_form.fields_dict.custom_group_send_times.$wrapper.is(':visible')).to.equal(false);
        });
        save(); reload(); expand(0);
        rowForm().should(r => expect(r.doc.custom_group_workflow_action_emails).to.equal(0));
        rowForm().then(r => r.grid_form.fields_dict.custom_email_settings_reset.$input.click());
        cy.window().should(w => {
            expect(w.cur_frm.doc.states[0].custom_email_settings_override).to.equal(0);
            expect(w.cur_frm.doc.states[0].send_email).to.equal(1);
            expect(w.cur_frm.doc.states[0].custom_group_workflow_action_emails).to.equal(1);
        });
        save(); reload();
    });

    it('keeps correction profile separate while inherited schedule follows global edits', () => {
        open();
        cy.window().then(w => w.cur_frm.set_value('custom_group_send_times','09:00, 18:00'));
        cy.window().should(w => {
            expect(w.cur_frm.doc.states[0].custom_group_send_times).to.equal('09:00, 18:00');
            expect(w.cur_frm.doc.states[0].custom_email_settings_override).to.equal(0);
            expect(w.cur_frm.doc.states[1].custom_email_settings_override).to.equal(1);
            expect(w.cur_frm.doc.states[1].custom_group_workflow_action_emails).to.equal(0);
        });
        save(); reload(); expand(1);
        cy.window().should(w => {
            const form = w.cur_frm.fields_dict.states.grid.grid_rows[1].grid_form;
            expect(form.fields_dict.next_action_email_template.$wrapper.is(':visible')).to.equal(true);
            expect(form.fields_dict.custom_group_send_times.$wrapper.is(':visible')).to.equal(false);
        });
        cy.get('.modal:visible').should('not.exist');
        cy.get('#freeze:visible, .modal-backdrop:visible').should('not.exist');
        cy.window().then(w => cy.wrap(w.cur_frm.fields_dict.states.grid.grid_rows[1].grid_form.fields_dict.custom_email_settings_source.$wrapper).scrollIntoView());
        for (const theme of ['light','dark']) {
            cy.window().then(w => {w.document.documentElement.dataset.theme=theme;});
            cy.contains('Настройки состояния').filter(':visible').should('have.length.at.least',1);
            cy.window().then(w => cy.wrap(w.cur_frm.fields_dict.states.grid.grid_rows[1].grid_form.wrapper).screenshot('workflow-email-profile-' + theme));
        }
    });
});
