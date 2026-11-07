import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

let route = "Form/Issue/one";
let respond;
const nodes = [{ html: "Other message", classes: new Set(["form-message", "blue"]) }];
const select = (values) => ({
  length: values.length,
  remove() { for (const node of values) nodes.splice(nodes.indexOf(node), 1); },
  last: () => select(values.slice(-1)),
  addClass(value) { for (const node of values) node.classes.add(value); return this; },
});
const frm = {
  doc: { doctype: "Issue", name: "one" },
  is_new: () => false,
  layout: { message: {
    length: 1,
    children: (selector) => select(nodes.filter((node) => !selector || node.classes.has(selector.slice(1)))),
    addClass() {},
  } },
  dashboard: { add_comment(html, color) {
    nodes.push({ html, classes: new Set(["form-message", color]) });
  } },
};
const document = { addEventListener() {} };
const frappe = {
  boot: {}, ui: { form: {} }, router: { on() {} },
  get_route_str: () => route,
  utils: { escape_html: (value) => String(value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;") },
  call: () => new Promise((resolve) => { respond = resolve; }),
};
vm.runInNewContext(fs.readFileSync(new URL("../dinext_common/public/js/workflow_approval.js", import.meta.url), "utf8"), {
  frappe, document, window: { frappe }, cur_frm: null,
  $: () => ({ on() {} }), __: (value) => value,
});
assert.equal(typeof frappe.dinext.paintWorkflowComments, "function", "Shared orange comment renderer is missing");
const comments = [
  { task_name: "a", reference_name: "one", author: "alice", author_name: "Alice", comment: "Correct dates\nAnd hours" },
  { task_name: "b", reference_name: "one", author: "bob", author_name: "<img src=x>", comment: "<script>unsafe</script>" },
];
frappe.dinext.paintWorkflowComments(frm, comments);
frappe.dinext.paintWorkflowComments(frm, comments);
assert.equal(nodes.length, 2, "One owned comment message must preserve other messages");
assert.ok(nodes[1].classes.has("orange"));
assert.match(nodes[1].html, /Alice/);
assert.match(nodes[1].html, /Correct dates\nAnd hours/);
assert.match(nodes[1].html, /&lt;img src=x&gt;/);
assert.doesNotMatch(nodes[1].html, /<script>/);
frappe.dinext.paintWorkflowComments(frm, []);
assert.deepEqual(nodes.map((node) => node.html), ["Other message"]);

let pending = frappe.dinext.refreshWorkflowComments(frm);
route = "List/Issue";
respond({ message: comments });
await pending;
assert.equal(nodes.length, 1, "Navigation must discard an obsolete comment response");
route = "Form/Issue/one";
pending = frappe.dinext.refreshWorkflowComments(frm);
const stale = respond;
const current = frappe.dinext.refreshWorkflowComments(frm);
respond({ message: comments.slice(0, 1) });
await current;
stale({ message: comments.slice(1) });
await pending;
assert.match(nodes[1].html, /Alice/);
assert.doesNotMatch(nodes[1].html, /&lt;img/);
console.log("Workflow comment rendering and stale-response checks passed");
