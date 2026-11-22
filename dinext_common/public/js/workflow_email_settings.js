(() => {
    const fields = [
        "custom_group_workflow_action_emails", "custom_attach_document_pdf",
        "custom_group_interval_unit", "custom_group_interval_value", "custom_group_send_times",
        "custom_group_email_template", "next_action_email_template",
    ];
    const enabled = (value) => value === true || String(value || "") === "1";
    const parentValue = (frm, field) => {
        if (field === "next_action_email_template") return frm.doc.custom_workflow_action_email_template || "";
        if (field === "custom_group_send_times") return frm.doc[field] || (frm.doc.custom_group_send_time || "").slice(0, 5);
        return frm.doc[field] ?? (field === "custom_group_interval_unit" ? "Days" : "");
    };
    function inherit(frm, row) {
        for (const field of fields) row[field] = parentValue(frm, field);
        row.custom_group_schedule_anchor = frm.doc.custom_group_schedule_anchor;
    }
    function refreshRows(frm) {
        for (const row of frm.doc.states || []) {
            if (!enabled(row.custom_email_settings_override)) inherit(frm, row);
            row.custom_email_settings_source = enabled(row.custom_email_settings_override) ? "State settings" : "From Workflow";
        }
        frm.refresh_field("states");
    }
    function edit(field) {
        return (frm, cdt, cdn) => {
            const row = locals[cdt][cdn];
            const desired = row[field];
            if (!enabled(row.custom_email_settings_override)) inherit(frm, row);
            row[field] = desired;
            row.custom_email_settings_override = 1;
            row.custom_email_settings_source = "State settings";
            frm.dirty();
            frm.refresh_field("states");
        };
    }
    const parentEvents = {refresh: refreshRows};
    for (const field of fields) parentEvents[field === "next_action_email_template" ? "custom_workflow_action_email_template" : field] = refreshRows;
    const childEvents = {
        form_render: refreshRows,
        states_add: refreshRows,
        custom_email_settings_reset(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            row.custom_email_settings_override = 0;
            inherit(frm, row);
            refreshRows(frm);
            frm.dirty();
        },
    };
    for (const field of fields) childEvents[field] = edit(field);
    frappe.ui.form.on("Workflow", parentEvents);
    frappe.ui.form.on("Workflow Document State", childEvents);
})();
