(() => {
    const tableField = "custom_fingerprint_excluded_fields";
    const systemFields = new Set([
        "_assign", "_comments", "_liked_by", "_seen", "_user_tags", "creation",
        "docstatus", "idx", "modified", "modified_by", "name", "owner", "parent",
        "parentfield", "parenttype",
    ]);
    const childSystemFields = new Set([...systemFields, "__islocal", "__onload", "__run_link_triggers", "__unsaved"]);
    const nonValueTypes = new Set([
        "Button", "Column Break", "Fold", "HTML", "Heading", "Section Break", "Tab Break", "Password",
    ]);
    const tableTypes = new Set(["Table", "Table MultiSelect"]);
    const isContent = (df, excluded) => df.fieldname && !excluded.has(df.fieldname) &&
        !nonValueTypes.has(df.fieldtype) && !df.virtual && !df.is_virtual && !df.non_db;

    async function refreshChoices(frm) {
        const grid = frm.fields_dict[tableField]?.grid;
        if (!grid || (frm.perm && !frm.perm.some((row) => row.write))) return;
        const generation = (frm._fingerprintChoicesGeneration || 0) + 1;
        frm._fingerprintChoicesGeneration = generation;
        const doctype = frm.doc.document_type;
        const choices = [];
        if (doctype) {
            await frappe.model.with_doctype(doctype);
            const meta = frappe.get_meta(doctype);
            const excluded = new Set([...systemFields, frm.doc.workflow_state_field,
                ...(frm.doc.states || []).map((row) => row.update_field)]);
            const fields = meta.fields.filter((df) => isContent(df, excluded));
            await Promise.all(fields.filter((df) => tableTypes.has(df.fieldtype) && df.options)
                .map((df) => frappe.model.with_doctype(df.options)));
            for (const df of fields) {
                const label = __(df.label || df.fieldname, null, doctype);
                choices.push({
                    value: df.fieldname,
                    label: tableTypes.has(df.fieldtype)
                        ? __("{0} — entire table ({1})", [label, df.fieldname])
                        : label + " (" + df.fieldname + ")",
                });
                if (tableTypes.has(df.fieldtype) && df.options) {
                    const child = frappe.get_meta(df.options);
                    for (const field of child.fields || []) {
                        if (!isContent(field, childSystemFields) || tableTypes.has(field.fieldtype)) continue;
                        const path = df.fieldname + "." + field.fieldname;
                        choices.push({
                            value: path,
                            label: label + " / " + __(field.label || field.fieldname, null, df.options) +
                                " (" + path + ")",
                        });
                    }
                }
            }
        }
        if (generation !== frm._fingerprintChoicesGeneration || doctype !== frm.doc.document_type) return;
        grid.update_docfield_property("field_path", "options", choices);
        // Preserve invalid typed/stale rows for an actionable server validation error.
        grid.update_docfield_property("field_path", "ignore_validation", true);
        frm._fingerprintFieldChoices = choices;
        frm.refresh_field(tableField);
    }

    frappe.ui.form.on("Workflow", {
        refresh: refreshChoices,
        document_type: refreshChoices,
        workflow_state_field: refreshChoices,
    });
    frappe.ui.form.on("Workflow Document State", {
        update_field: refreshChoices,
        states_remove: refreshChoices,
    });
})();
