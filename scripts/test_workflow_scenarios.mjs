import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const route = ["Form", "Issue", "A"];
const definitions = {
  Alpha: { name: "Alpha", document_type: "Issue", workflow_state_field: "approval_a",
    override_status: 0, states: [{ state: "Waiting A", allow_edit: "Editor A", doc_status: 0 }], transitions: [] },
  Beta: { name: "Beta", document_type: "Issue", workflow_state_field: "approval_b",
    override_status: 0, states: [{ state: "Waiting B", allow_edit: "Editor B", doc_status: 0 }], transitions: [] },
};
const envelope = (workflow, process, state) => ({
  context: { workflow, process_id: process, process_status: "Prepared", state_field: definitions[workflow].workflow_state_field,
    state, definition_revision: `${workflow}-revision` }, definition: definitions[workflow],
});
const docs = Object.fromEntries([["A", "Alpha", "P-A", "Waiting A"], ["B", "Beta", "P-B", "Waiting B"]].map(
  ([name, workflow, process, state]) => [name, { name, doctype: "Issue", docstatus: 0,
    [definitions[workflow].workflow_state_field]: state,
    __onload: { dinext_workflow_context: envelope(workflow, process, state).context,
      dinext_workflow_definition: definitions[workflow] } }]
));
let batchResponse;
let resolveBatch;
const contextBatchSizes = [];
class Form {
  constructor() { this.doctype = "Issue"; this.docname = "A"; this.doc = docs.A; this.states = { update_fields: [] }; }
  refresh(name) {
    this.docname = name || this.docname;
    this.doc = docs[this.docname];
    this.read_only = frappe.workflow.is_read_only(this.doctype, this.docname);
    return this.read_only;
  }
}
class ListView {
  constructor() { this.doctype = "Issue"; this.data = [docs.A, docs.B]; this.rendered = []; }
  render() { this.rendered = this.data.map(doc => frappe.get_indicator(doc, this.doctype)); }
}
class States {
  constructor(frm) { this.frm = frm; }
  get_state() { return "wrong-native-state"; }
  refresh() { this.observed = this.get_state(); }
  set_default_state() {}
  setup_help() {}
}
const frappe = {
  boot: { enable_parallel_workflow_approval: true, workflow_state_styles: { "Waiting A": "Warning", "Waiting B": "Success" } },
  dinext: {}, session: { user: "reviewer@example.com" }, user_roles: ["Editor A"],
  get_route: () => route, get_route_str: () => route.join("/"), get_doc: (dt, name) => dt === "Issue" ? docs[name] : definitions[name],
  workflow: { get_state_fieldname: () => "wrong_native_field", is_read_only: () => false,
    get_state: () => "wrong-native-state", workflows: {}, state_fields: {}, avoid_status_override: {} },
  model: { has_workflow: () => true }, ui: { form: { Form, States, on() {} } }, views: { ListView },
  get_indicator: doc => [doc.status || "Native", "gray", "status,=,Native"], has_indicator: () => true,
  router: { on() {} }, utils: { escape_html: value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;") },
  call: async options => {
    if (options.method === "frappe.desk.reportview.get_list") return { message: [{ name: "POSITION-1", status: "Legacy status" }] };
    contextBatchSizes.push(options.args.names.length);
    if (options.args.names.length > 500) throw new Error("Context request exceeds the server batch limit");
    if (options.method === "dinext_common.workflow_approval.api.get_my_source_transitions")
      return { message: Object.fromEntries(options.args.names.map(name => [name, []])) };
    return batchResponse ?? new Promise(resolve => { resolveBatch = resolve; });
  },
  xcall: async () => "legacy response",
};
const context = { frappe, locals: { Issue: docs, Workflow: { ...definitions,
  StatusWorkflow: { name: "StatusWorkflow", document_type: "Issue", workflow_state_field: "status" } } }, cur_frm: null, window: { frappe },
  document: { addEventListener() {} }, __: value => value, console, setTimeout, clearTimeout,
  $: () => ({ on() {}, bind() {} }), cint: Number };
const source = new URL("../dinext_common/public/js/workflow_scenarios.js", import.meta.url);
if (fs.existsSync(source)) vm.runInNewContext(fs.readFileSync(source, "utf8"), context);
assert.equal(typeof frappe.dinext.getWorkflowContext, "function", "Document-aware context adapter is missing");

const form = new Form();
context.cur_frm = form;
assert.equal(form.refresh("A"), false, "A permits Editor A before native refresh");
assert.equal(form.state_fieldname, "approval_a");
assert.equal(form.states.state_fieldname, "approval_a");
route[2] = "B";
assert.equal(form.refresh("B"), true, "B must be readonly for Editor A on the first native refresh");
assert.equal(form.state_fieldname, "approval_b");
assert.equal(form.states.state_fieldname, "approval_b");
assert.equal(frappe.workflow.get_state(docs.B), "Waiting B");
assert.deepEqual(Array.from(frappe.get_indicator(docs.A)), ["Waiting A", "orange", "approval_a,=,Waiting A"]);
assert.deepEqual(Array.from(frappe.get_indicator(docs.B)), ["Waiting B", "green", "approval_b,=,Waiting B"]);
assert.equal(frappe.workflow.workflows.Issue, undefined, "Selecting B must not write a global DocType schema");
const unmatched = { doctype: "Issue", name: "C", status: "Open",
  __onload: { dinext_workflow_context: { workflow: null, state_field: null } } };
assert.equal(frappe.get_indicator(unmatched)[0], "Open", "No matching schema must preserve the domain status indicator");
docs.C = unmatched;
route[2] = "C";
form.refresh("C");
assert.equal(frappe.model.has_workflow("Issue"), false, "An unmatched form must retain ordinary document actions");
route[2] = "A";
assert.equal(form.refresh("A"), false, "Returning to A must restore its permissions");
definitions.Alpha.states.push({ state: "Cancelled A", doc_status: 2 });
definitions.Alpha.transitions.push({ state: "Waiting A", next_state: "Cancelled A" });
definitions.Beta.states.push({ state: "Cancelled B", doc_status: 2 });
assert.equal(await frappe.xcall("frappe.model.workflow.can_cancel_document", { doctype: "Issue" }), false,
  "A configured cancellation transition must suppress native Cancel for this schema");
route[2] = "B";
form.refresh("B");
assert.equal(await frappe.xcall("frappe.model.workflow.can_cancel_document", { doctype: "Issue" }), true,
  "A schema without a cancellation transition must retain native Cancel");
assert.equal(await frappe.xcall("frappe.model.workflow.can_cancel_document", { doctype: "Task" }), "legacy response");
route[2] = "A";
form.refresh("A");

assert.equal(typeof frappe.dinext.paintWorkflowRoutingError, "function", "Recorded setup failures need a targeted form message");
const messages = [{ classes: new Set(["form-message", "other-banner"]), text: "Existing pending banner", color: "blue" }];
const host = { length: 1, children(selector) {
  const selected = messages.filter(row => !selector || row.classes.has(selector.slice(1)));
  return { length: selected.length,
    remove() { for (const row of selected) messages.splice(messages.indexOf(row), 1); },
    last() { return { addClass(name) { selected.at(-1).classes.add(name); } }; } };
} };
form.layout = { message: host };
form.dashboard = { add_comment(text, color) { messages.push({ classes: new Set(["form-message"]), text, color }); } };
docs.A.__onload.dinext_workflow_error = "Invalid next entry <script>bad</script>";
frappe.dinext.paintWorkflowRoutingError(form);
frappe.dinext.paintWorkflowRoutingError(form);
assert.equal(messages.length, 2, "Only the owned setup message may be replaced");
assert.equal(messages[1].color, "orange");
assert.ok(messages[1].text.includes("&lt;script&gt;"), "The recorded reason must be HTML escaped");
docs.A.__onload.dinext_workflow_error = null;
frappe.dinext.paintWorkflowRoutingError(form);
assert.equal(messages.length, 1, "Resolving the error must retain unrelated banners");
const unsupported = { doctype: "ToDo", name: "TODO-1", status: "Open" };
frappe.dinext.storeWorkflowContext(unsupported, { managed: false,
  context: { workflow: null, state_field: null }, definition: null });
assert.equal(frappe.dinext.getWorkflowContext(unsupported), undefined,
  "Unsupported producer types must retain native workflow behavior");

const exactTargets = [{ name: "A", workflow: "Alpha", process_id: "P-A", task_name: "TASK-A", transition_uuid: "UUID-A" }];
assert.equal(typeof frappe.dinext.withWorkflowTargets, "function", "Timesheet actions must retain the selected transition targets");
await frappe.dinext.withWorkflowTargets({ action: "Approve", targets: exactTargets }, async () => {
  const args = frappe.dinext.prepareWorkflowRequest("dinext_timesheets.workflow_approval.apply_timesheet_position_action",
    { timesheet_name: "UT-1", action: "Approve" });
  assert.equal(args.targets, exactTargets);
  assert.equal(frappe.dinext.prepareWorkflowRequest("dinext_common.workflow_approval.api.bulk_vote",
    { action: "Approve", names: ["A"] }).targets, exactTargets,
    "The existing Timesheets row caller must retain its process target too");
  await Promise.resolve();
  assert.equal(frappe.dinext.prepareWorkflowRequest("dinext_timesheets.workflow_approval.apply_timesheet_position_action",
    { action: "Approve" }).targets, exactTargets);
});
assert.equal(frappe.dinext.prepareWorkflowRequest("dinext_timesheets.workflow_approval.apply_timesheet_position_action", { action: "Approve" }).targets,
  undefined, "Targets must leave the request scope after completion");

const list = new ListView();
delete docs.A.__onload;
delete docs.B.__onload;
list.render();
assert.equal(list.rendered.length, 0, "Rows must wait for the context batch");
resolveBatch({ message: { A: envelope("Alpha", "P-A", "Waiting A"), B: envelope("Beta", "P-B", "Waiting B") } });
await list._dinext_workflow_render_promise;
assert.equal(list.rendered[0][0], "Waiting A");
assert.equal(list.rendered[1][0], "Waiting B");

batchResponse = { message: { A: envelope("Alpha", "P-old", "Waiting A") } };
list.data = [docs.A];
list.render();
list.data = [docs.B];
await list._dinext_workflow_render_promise;
assert.equal(list.rendered.length, 2, "A stale context response must not render replaced rows");
const longList = new ListView();
longList.data = Array.from({ length: 501 }, (_, index) => ({ doctype: "Issue", name: `LONG-${index}`, status: "Open" }));
batchResponse = { message: {} };
longList.render();
await longList._dinext_workflow_render_promise;
assert.equal(longList.rendered.length, 501, "Native large list pages must render within the context batch limit");
assert.ok(contextBatchSizes.every(size => size <= 500));
const longApprovals = await frappe.call({ method: "dinext_common.workflow_approval.api.get_my_source_transitions",
  args: { doctype: "User Timesheet Position", names: longList.data.map(row => row.name) } });
assert.equal(Object.keys(longApprovals.message).length, 501,
  "A large native Timesheets page must load every personal action within the server batch limit");

route.splice(0, route.length, "Form", "User Timesheet", "UT-1");
context.cur_frm = { doctype: "User Timesheet", doc: { name: "UT-1" } };
batchResponse = { message: { "POSITION-1": envelope("Alpha", "P-POSITION", "Waiting A") } };
const positions = await frappe.call({ method: "frappe.desk.reportview.get_list",
  args: { doctype: "User Timesheet Position" } });
assert.equal(positions.message[0].status, "Waiting A", "Timesheet display must use each position's selected state");

frappe.boot.enable_parallel_workflow_approval = false;
assert.equal(frappe.workflow.get_state(docs.A), "wrong-native-state");
assert.equal(frappe.get_indicator(docs.A)[0], "Native");
console.log("Workflow scenarios: first-refresh readonly, state fields, per-row indicators, gated rendering and stale responses passed");
