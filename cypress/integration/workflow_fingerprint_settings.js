Cypress.removeAllListeners("uncaught:exception");
const api = "dinext_common.tests.fingerprint_settings_ui";
const table = '[data-fieldname="custom_fingerprint_excluded_fields"]';
let fixture;

function openWorkflow(user = fixture.editor) {
    cy.login(user, fixture.password);
    cy.visit("/app/workflow/" + encodeURIComponent(fixture.workflow));
    cy.window().should((win) => {
        expect(win.cur_frm?.doc?.name).to.eq(fixture.workflow);
    });
    if (user !== fixture.reader) {
        cy.window().should((win) => {
            expect(win.cur_frm._fingerprintFieldChoices?.some((item) =>
                item.value === "table.utilized_hours")).to.eq(true);
        });
    }
    cy.window().its("frappe.request.ajax_count", { timeout: 15000 }).should("eq", 0);
    cy.get(".modal:visible").should("not.exist");
    cy.get(table).scrollIntoView().should("be.visible");
}

function replaceRows(paths) {
    cy.window().then((win) => {
        const frm = win.cur_frm;
        frm.clear_table("custom_fingerprint_excluded_fields");
        for (const path of paths) frm.add_child("custom_fingerprint_excluded_fields", { field_path: path });
        frm.refresh_field("custom_fingerprint_excluded_fields");
        frm.dirty();
    });
}

function saveViaForm() {
    cy.window().then((win) => { win.cur_frm.ignore_warning = true; return win.cur_frm.save(); });
}


context("Editable Workflow fingerprint exclusions", { viewportWidth: 1440, viewportHeight: 960 }, () => {
    before(() => {
        cy.login();
        cy.openDesk("/app");
        cy.call(api + ".seed").then((r) => fixture = r.body.message);
    });
    after(() => {
        cy.login();
        cy.openDesk("/app");
        cy.call(api + ".cleanup");
    });

    it("selects scalar, whole-table and child fields, persists and removes rows", () => {
        openWorkflow();
        replaceRows([""]);
        cy.get(table + ' .grid-row[data-idx="1"] .grid-static-col[data-fieldname="field_path"]').click();
        cy.get(table + ' input[data-fieldname="field_path"]:visible').type("custom_username");
        cy.contains(table + " .awesomplete li", "custom_username").click();
        cy.window().should((win) =>
            expect(win.cur_frm.doc.custom_fingerprint_excluded_fields[0].field_path).to.eq("custom_username"));
        cy.window().then((win) => {
            const frm = win.cur_frm;
            frm.add_child("custom_fingerprint_excluded_fields", { field_path: "table.utilized_hours" });
            frm.add_child("custom_fingerprint_excluded_fields", { field_path: "table" });
            frm.refresh_field("custom_fingerprint_excluded_fields");
        });
        saveViaForm();
        cy.reload();
        cy.window().should((win) => expect(win.cur_frm?.doc?.custom_fingerprint_excluded_fields
            ?.map((row) => row.field_path)).to.deep.eq(["custom_username", "table.utilized_hours", "table"]));
        replaceRows(["table.utilized_hours"]);
        saveViaForm();
        cy.reload();
        cy.window().should((win) => expect(win.cur_frm?.doc?.custom_fingerprint_excluded_fields
            ?.map((row) => row.field_path)).to.deep.eq(["table.utilized_hours"]));
    });

    it("retains invalid rows after DocType changes and rejects invalid and duplicate paths", () => {
        openWorkflow();
        for (const paths of [["missing"], ["table.hours.more"], ["all_hours", "all_hours"]]) {
            replaceRows(paths);
            cy.window().then((win) => cy.call("frappe.client.save",
                { doc: JSON.stringify(win.cur_frm.doc) }, { failOnStatusCode: false })
                .its("status").should("eq", 417));
            cy.window().should((win) => expect(win.cur_frm.doc.custom_fingerprint_excluded_fields
                .map((row) => row.field_path)).to.deep.eq(paths));
        }
        replaceRows(["custom_username"]);
        cy.window().then((win) => win.cur_frm.set_value("document_type", "ToDo"));
        cy.window().should((win) => {
            expect(win.cur_frm.doc.custom_fingerprint_excluded_fields[0].field_path).to.eq("custom_username");
            expect(win.cur_frm._fingerprintFieldChoices.some((item) => item.value === "custom_username")).to.eq(false);
        });
        cy.window().then((win) => cy.call("frappe.client.save",
            { doc: JSON.stringify(win.cur_frm.doc) }, { failOnStatusCode: false })
            .its("status").should("eq", 417));
    });

    it("unions Workflow and hook exclusions while preserving other business values", () => {
        openWorkflow();
        replaceRows(["table.utilized_hours"]);
        saveViaForm();
        cy.call(api + ".verify_union").then((r) => {
            expect(r.body.message.base).to.eq(r.body.message.excluded);
            expect(r.body.message.base).not.to.eq(r.body.message.hours);
        });
    });

    it("shows readable Russian labels and choices in light and dark runtime themes", () => {
        openWorkflow();
        cy.window().its("frappe.boot.lang").should("eq", "ru");
        for (const theme of ["light", "dark"]) {
            cy.window().then((win) => { win.document.documentElement.dataset.theme = theme; });
            cy.get(table).scrollIntoView().should("contain", "Поля, исключаемые из снимка");
            cy.window().should((win) => {
                const choices = win.cur_frm._fingerprintFieldChoices;
                expect(choices.some((item) => item.value === "table" && item.label.includes("вся таблица"))).to.eq(true);
                expect(choices.some((item) => item.value === "table.utilized_hours")).to.eq(true);
                expect(choices.some((item) => ["name", "modified", "status", "workflow_state"].includes(item.value))).to.eq(false);
            });
            cy.screenshot("workflow-fingerprint-" + theme, { capture: "viewport" });
        }
    });

    it("enforces normal Workflow write permissions", () => {
        openWorkflow(fixture.reader);
        cy.window().should((win) => {
            expect(win.cur_frm.perm.some((perm) => perm.write)).to.eq(false);
        });
        cy.get(table + " .grid-add-row:visible").should("not.exist");
        cy.window().then((win) => {
            const doc = JSON.parse(JSON.stringify(win.cur_frm.doc));
            doc.custom_fingerprint_excluded_fields.push({ doctype: "Workflow Fingerprint Exclusion", field_path: "all_hours" });
            return cy.call("frappe.client.save", { doc: JSON.stringify(doc) }, { failOnStatusCode: false })
                .its("status").should("eq", 403);
        });
    });

    it("applies changes prospectively without changing historical task snapshots", () => {
        openWorkflow();
        let before;
        cy.call(api + ".history").then((r) => before = r.body.message);
        replaceRows(["table.utilized_hours", "all_hours"]);
        saveViaForm();
        cy.call(api + ".history").then((r) => {
            expect(r.body.message.task).to.eq(before.task);
            expect(r.body.message.fingerprint).not.to.eq(before.fingerprint);
        });
        replaceRows(["table.utilized_hours"]);
        saveViaForm();
    });
});
