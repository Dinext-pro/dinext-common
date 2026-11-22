(() => {
	const suggestOrder = async (frm, initialLoad = false) => {
		if (!frm.is_new() || !frm.doc.document_type) return;
		if (initialLoad && frm._dinext_scenario_order_initial_doc === frm.doc) return;
		if (initialLoad) frm._dinext_scenario_order_initial_doc = frm.doc;
		const initial = Number(frm.doc.custom_selection_order) || 0;
		const suggestion = frm._dinext_scenario_order;
		if (!initialLoad && initial > 0 && initial !== suggestion?.value) return;
		if (suggestion?.doctype === frm.doc.document_type && initial === suggestion.value) return;
		const doc = frm.doc;
		const doctype = doc.document_type;
		const generation = frm._dinext_scenario_order_generation = (frm._dinext_scenario_order_generation || 0) + 1;
		const response = await frappe.call({
			method: "dinext_common.workflow_approval.scenarios.metadata.get_next_selection_order",
			args: { doctype }, silent: true,
		});
		if (frm.doc !== doc || !frm.is_new() || doc.document_type !== doctype ||
			frm._dinext_scenario_order_generation !== generation ||
			(Number(doc.custom_selection_order) || 0) !== initial) return;
		const value = Number(response.message);
		if (!Number.isInteger(value) || value <= 0) return;
		frm._dinext_scenario_order = { doctype, value };
		await frm.set_value("custom_selection_order", value);
	};
	frappe.ui.form.on("Workflow", { onload: frm => suggestOrder(frm, true),
		document_type: frm => suggestOrder(frm) });
})();
