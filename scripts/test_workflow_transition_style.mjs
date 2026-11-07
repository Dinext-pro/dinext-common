import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const localStates = {};
const labels = [];
let transitions = [];
const legacyAction = () => "original callback";
class States {
  setup_btn() {}
}
class ListView {
  toggle_workflow_actions() {
    return "legacy visibility";
  }
  get_workflow_action_menu_items() {
    return [{ name: "Approve", label: "Approve", action: legacyAction }];
  }
}
const element = () => ({
  classes: new Set(),
  attributes: {},
  addClass(value) {
    this.classes.add(value);
    return this;
  },
  attr(key, value) {
    this.attributes[key] = value;
    return this;
  },
  on() {
    return this;
  },
  off() {
    return this;
  },
  text() {
    return this;
  },
  removeClass(value) {
    this.classes.delete(value);
    return this;
  },
  toggle(visible) {
    this.visible = visible;
    return this;
  },
  closest() {
    return this;
  },
});
const frappe = {
  boot: {
    enable_parallel_workflow_approval: false,
    workflow_action_icons: { Approve: "check", Reject: "close" },
    workflow_state_styles: {},
  },
  get_doc: (_doctype, name) => localStates[name],
  utils: {
    escape_html: (text) =>
      String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;"),
    icon: (name) => `<svg data-icon="${name}"><use href="#icon-${name}"></use></svg>`,
  },
  session: { user: "reviewer@example.com" },
  user_roles: ["Manager"],
  ui: { form: { States, on() {} } },
  views: { ListView },
  router: { on() {} },
  model: { has_workflow: () => true },
  workflow: {
    workflows: {},
    get_all_transitions: () => transitions,
    get_transitions: () => Promise.resolve(transitions),
  },
};
const document = {
  getElementById: (id) => ["icon-check", "icon-close", "icon-close-alt"].includes(id),
  addEventListener() {},
};
const context = {
  frappe,
  document,
  window: { frappe },
  cur_frm: null,
  __: (text) => text,
  $: (value) => (value === document || typeof value === "string" ? element() : value),
};
vm.runInNewContext(
  fs.readFileSync(
    new URL("../dinext_common/public/js/workflow_approval.js", import.meta.url),
    "utf8"
  ),
  context
);
const {
  workflowTransitionStyle: style,
  workflowTransitionLabel: label,
  decorateWorkflowTransition: decorate,
} = frappe.dinext;

for (const name of [
  "Primary",
  "Info",
  "Success",
  "Warning",
  "Danger",
  "Inverse",
]) {
  frappe.boot.workflow_state_styles.Target = name;
  assert.equal(
    style({ action: "Unrelated wording", next_state: "Target" }),
    name.toLowerCase()
  );
}
frappe.boot.workflow_state_styles = {
  Green: "Success",
  Red: "Danger",
  Missing: "unsupported",
  OtherGreen: "Success",
};
assert.equal(style({ action: "Approve", next_state: "Red" }), "danger");
assert.equal(style({ action: "Reject", next_state: "Green" }), "success");
assert.match(label({ action: "Reject", next_state: "Red" }), /href="#icon-close-alt"/);
assert.match(frappe.dinext.workflowActionLabel("Reject"), /href="#icon-close"/);
assert.equal(style({ action: "Approve", next_state: "Unknown" }), "");
assert.equal(style({ action: "Approve", next_state: "Missing" }), "");
assert.equal(
  style({
    action: "Approve",
    positions: [{ next_state: "Green" }, { next_state: "OtherGreen" }],
  }),
  "success"
);
assert.equal(
  style({
    action: "Approve",
    positions: [{ next_state: "Green" }, { next_state: "Red" }],
  }),
  ""
);
assert.equal(style({ action: "Approve", positions: [] }), "");
localStates.Green = { style: "" };
assert.equal(style({ next_state: "Green" }), "");
localStates.Green.style = "Warning";
assert.equal(style({ next_state: "Green" }), "warning");
delete localStates.Green;
assert.match(
  label({ action: "Approve", next_state: "Red" }),
  /data-workflow-style="danger".*data-icon="check"/
);
assert.match(
  label({ action: '<img src=x onerror="bad">', next_state: "Green" }),
  /&lt;img/
);
assert.doesNotMatch(
  label({ action: "<img src=x>", next_state: "Green" }),
  /<img/
);
const option = element();
decorate(option, { next_state: "Red" });
assert.equal(option.attributes["data-workflow-style"], "danger");
assert.ok(option.classes.has("dinext-workflow-transition"));
decorate(option, { next_state: "Unknown" });
assert.equal(option.attributes["data-workflow-style"], "");

transitions = [
  {
    action: "Approve",
    next_state: "Red",
    allowed: "Manager",
    custom_transition_uuid: "uuid-red",
    allow_self_approval: 1,
  },
];
const state = new States();
state.frm = {
  doc: { owner: "other@example.com" },
  page: {
    clear_actions_menu: () => labels.splice(0),
    add_action_item: (text, callback) => labels.push({ text, callback }),
  },
};
state.show_actions();
await Promise.resolve();
assert.match(labels[0].text, /data-workflow-style="danger"/);
let items = new ListView().get_workflow_action_menu_items();
assert.match(items[0].label, /data-workflow-style="danger"/);
assert.equal(items[0].action, legacyAction);
assert.equal(
  await new ListView().toggle_workflow_actions(),
  "legacy visibility"
);
frappe.boot.enable_parallel_workflow_approval = true;
state.show_actions();
await Promise.resolve();
assert.match(labels[0].text, /data-workflow-style="danger"/);
assert.equal(new ListView().get_workflow_action_menu_items().length, 0,
  "parallel workflow actions must not be created before looking up the selection");

const actions = [];
const lookup = [];
const actionsMenu = element();
actionsMenu.find = () => ({ remove() { actions.length = 0; } });
actionsMenu.prepend = () => {};
const list = new ListView();
list.doctype = "Example";
list.get_checked_items = () => ["one", "two"];
list.page = {
  actions: actionsMenu,
  actions_btn_group: element(),
  add_actions_menu_item(label, action) {
    actions.push({ label, action });
    return element();
  },
};
frappe.get_route_str = () => "List/Example";
frappe.call = async ({ method, args }) => {
  lookup.push({ method, args });
  return { message: [{ action: "Approve", transition_uuid: "uuid-red", next_state: "Red" }] };
};
await list.toggle_workflow_actions();
assert.equal(lookup.length, 1);
assert.equal(lookup[0].method, "dinext_common.workflow_approval.api.get_common_list_transitions");
assert.equal(lookup[0].args.names.join(","), "one,two");
assert.equal(actions.length, 1);
assert.match(actions[0].label, /data-workflow-style="danger"/);

list.view_name = "List";
list.$result = { find: () => [{ dataset: { name: "raw%20name" } }] };
await list.toggle_workflow_actions();
assert.equal(lookup.at(-1).args.names[0], "raw%20name");
let finishLookup;
frappe.call = () => new Promise((resolve) => {
  finishLookup = resolve;
});
const staleMenu = list.toggle_workflow_actions();
list.$result = { find: () => [{ dataset: { name: "new selection" } }] };
finishLookup({ message: [{ action: "Approve", transition_uuid: "uuid-red", next_state: "Red" }] });
await staleMenu;
assert.equal(actions.length, 0, "late results do not populate actions for a different selection");

const keys = new Map();
document.addEventListener = (name, handler) => keys.set(name, handler);
document.removeEventListener = (name) => keys.delete(name);
frappe.dom = {
  freeze() {},
  unfreeze() {},
};
const page = { wrapper: [element()] };
page.wrapper[0].inert = false;
page.wrapper[0].getAttribute = (name) => page.wrapper[0].attributes[name] || null;
page.wrapper[0].setAttribute = (name, value) => { page.wrapper[0].attributes[name] = value; };
page.wrapper[0].removeAttribute = (name) => { delete page.wrapper[0].attributes[name]; };
let release;
const run = frappe.dinext.runWorkflowOperation(page, () => new Promise((resolve) => {
  release = resolve;
}));
assert.equal(page.wrapper[0].inert, true);
assert.ok(keys.has("keydown"));
let duplicate = false;
await frappe.dinext.runWorkflowOperation(page, () => { duplicate = true; });
assert.equal(duplicate, false);
release();
await run;
assert.equal(page.wrapper[0].inert, false);
assert.equal(keys.size, 0);
const events = new Map();
const counts = [];
frappe.realtime = {
  on(name, handler) { events.set(name, handler); },
  off(name) { events.delete(name); },
};
frappe.show_progress = (_title, count, total) => {
  counts.push([count, total]);
  frappe.cur_progress ||= {
    no_cancel() {},
    $wrapper: { 0: { addEventListener() {} }, remove() {} },
  };
  return frappe.cur_progress;
};
frappe.hide_progress = () => { frappe.cur_progress = null; };
let finishBatch;
const batch = frappe.dinext.runWorkflowOperation(page, () => new Promise((resolve) => {
  finishBatch = resolve;
}), { count: 2, title: "Approve", requestId: "this-batch" });
const onProgress = events.get("dinext_workflow_progress");
onProgress({ request_id: "different-batch", count: 1, total: 2 });
onProgress({ request_id: "this-batch", count: 1, total: 3 });
onProgress({ request_id: "this-batch", count: 3, total: 3 });
assert.deepEqual(counts, [[0, 2], [1, 3], [3, 3]]);
assert.equal(page.wrapper[0].inert, true, "progress is not the completion signal");
finishBatch();
await batch;
assert.equal(frappe.cur_progress, null);
assert.equal(page.wrapper[0].inert, false);
assert.equal(events.size, 0);
console.log(
  "Workflow style: six styles, neutral/aggregate/local metadata, escaping, icons and both form/list modes passed."
);
