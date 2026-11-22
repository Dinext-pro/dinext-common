(() => {
    const fields = {
        custom_deadline_unit: "deadline_intervals",
        custom_deadline_interval_unit: "sending_intervals",
        custom_deadline_recipient_type: "recipients",
    };
    async function options(frm) {
        if (!frm.doc.document_type) return;
        const result = await frappe.call({
            method: "dinext_common.workflow_approval.deadlines.metadata.get_options",
            args: {doctype: frm.doc.document_type},
        });
        frm.deadline_options = result.message || {};
        refresh(frm);
    }
    function refresh(frm) {
        const grid = frm.fields_dict.transitions?.grid;
        if (!grid) return;
        for (const row of grid.grid_rows || []) {
            for (const [field, group] of Object.entries(fields)) {
                const control = row.grid_form?.fields_dict[field];
                control?.set_data?.(frm.deadline_options?.[group] || []);
            }
            const target = (frm.doc.states || []).find(state => state.state === row.doc.next_state);
            const allowed = !!target && !target.is_optional_state;
            if (row.grid_form) {
                const section = row.grid_form.layout?.sections_dict.custom_deadline_section;
                if (section) {
                    section.df.hidden = allowed ? 0 : 1;
                    section.refresh();
                }
                row.toggle_editable("custom_deadline_enabled", allowed);
            }
        }
    }
    frappe.ui.form.on("Workflow", {onload: options, document_type: options, refresh});
    frappe.ui.form.on("Workflow Transition", {form_render: refresh, next_state: refresh});
})();
