import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const handlers = {};
const responses = [];
const frappe = {
  ui: { form: { on: (doctype, events) => Object.assign(handlers, events) } },
  call: async () => new Promise(resolve => responses.push(resolve)),
};
const source = new URL("../dinext_common/public/js/workflow_scenario_settings.js", import.meta.url);
if (fs.existsSync(source)) vm.runInNewContext(fs.readFileSync(source, "utf8"), { frappe });
assert.equal(typeof handlers.document_type, "function", "New workflows need an order suggestion");
const frm = { doc: { name: "new-workflow", document_type: "Issue", custom_selection_order: 0 },
  is_new: () => true, set_value: async (field, value) => { frm.doc[field] = value; } };
const first = handlers.document_type(frm);
responses.shift()({ message: 3 });
await first;
assert.equal(frm.doc.custom_selection_order, 3);
frm.doc.document_type = "Task";
const second = handlers.document_type(frm);
frm.doc.custom_selection_order = 8;
responses.shift()({ message: 4 });
await second;
assert.equal(frm.doc.custom_selection_order, 8, "A delayed suggestion must preserve a manual edit");
frm.is_new = () => false;
await handlers.document_type(frm);
assert.equal(responses.length, 0, "Saved workflow edits must never be overwritten");
const copy = { doc: { name: "new-copied-workflow", document_type: "Issue", custom_selection_order: 2 },
  is_new: () => true, async set_value(field, value) { this.doc[field] = value; } };
const copiedLoad = handlers.onload(copy);
assert.equal(responses.length, 1, "A copied definition must receive a fresh order on its first load");
responses.shift()({ message: 5 });
await copiedLoad;
assert.equal(copy.doc.custom_selection_order, 5);
copy.doc.custom_selection_order = 18;
await handlers.onload(copy);
assert.equal(responses.length, 0, "Repeated onload must preserve a manual order on this new document");
console.log("Workflow order suggestions preserve manual edits and saved definitions");
