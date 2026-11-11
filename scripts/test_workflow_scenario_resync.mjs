import assert from "node:assert/strict";

globalThis.window = globalThis;
const oldContext = { workflow: "Alpha", process_id: "P-A", state_field: "state_a", state: "Waiting A" };
const newContext = { workflow: "Beta", process_id: "P-B", state_field: "state_b", state: "Waiting B" };
const serverDoc = { doctype: "Issue", name: "A", docstatus: 0, state_a: "Waiting A", state_b: "Waiting B",
  __onload: { dinext_workflow_context: newContext, dinext_workflow_definition: { name: "Beta" } } };
let request;
globalThis.frappe = { boot: { enable_parallel_workflow_approval: true },
  workflow: { get_state_fieldname: () => "wrong_legacy_field" },
  dinext: { getWorkflowContext: doc => doc.__onload?.dinext_workflow_context },
  call(options) { request = options; options.callback({ message: serverDoc }); },
};
globalThis.locals = { Issue: {} };
const { detect_form_control_changes, resync_form_after_server_apply } = await import(
  "../dinext_common/public/js/form_conflict_merge/form_resync.js");
const { fetch_server_doc } = await import("../dinext_common/public/js/form_conflict_merge/merge_engine.js");
let refreshed;
const frm = { doctype: "Issue", docname: "A", doc: { doctype: "Issue", name: "A", docstatus: 0, state_a: "Waiting A",
  __onload: { dinext_workflow_context: oldContext } },
  is_new: () => false, refresh() { refreshed = frappe.dinext.getWorkflowContext(this.doc); } };
locals.Issue.A = frm.doc;
assert.equal(await fetch_server_doc(frm), serverDoc);
assert.equal(request.method, "dinext_common.workflow_approval.scenarios.api.get_workflow_document",
  "Server merge fetch must supply the new authoritative context");
const cfg = { form_resync_on_server_apply: true };
const changed = detect_form_control_changes(frm, serverDoc, { cfg });
assert.ok(changed.length, "A changed process/state field must trigger form control resync");
resync_form_after_server_apply(frm, serverDoc, { cfg }, changed);
assert.equal(refreshed.workflow, "Beta");
assert.equal(refreshed.state_field, "state_b");
assert.equal(frm.doc.state_b, "Waiting B");
frm.doc.__onload.dinext_workflow_error = "Old routing failure";
serverDoc.__onload.dinext_workflow_error = null;
const clearedError = detect_form_control_changes(frm, serverDoc, { cfg });
assert.ok(clearedError.length, "Clearing a routing failure must refresh its targeted message");
resync_form_after_server_apply(frm, serverDoc, { cfg }, clearedError);
assert.equal(frm.doc.__onload.dinext_workflow_error, null);
console.log("Workflow form resync: server context fetch, changed schema and new state field passed");
