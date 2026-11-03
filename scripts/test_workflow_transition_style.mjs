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
    workflow_action_icons: { Approve: "check" },
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
    icon: (name) => `<svg data-icon="${name}"></svg>`,
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
  getElementById: (id) => id === "icon-check",
  addEventListener() {},
};
const context = {
  frappe,
  document,
  window: { frappe },
  cur_frm: null,
  __: (text) => text,
  $: (value) => (value === document ? element() : value),
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
items = new ListView().get_workflow_action_menu_items();
assert.equal(items[0].name, "uuid-red");
assert.match(items[0].label, /data-workflow-style="danger"/);
assert.equal(typeof items[0].action, "function");
const list = new ListView();
list.doctype = "Example";
list.get_checked_items = () => ["one", "two"];
list.workflow_action_items = { "uuid-red": element(), "uuid-other": element() };
frappe.xcall = async () =>
  ["one", "two"].map((name) => ({
    reference_doctype: "Example",
    reference_name: name,
    available_transitions: [
      { action: "Approve", transition_uuid: "uuid-red" },
      ...(name === "one"
        ? [{ action: "Approve", transition_uuid: "uuid-other" }]
        : []),
    ],
  }));
await list.toggle_workflow_actions();
assert.equal(list.workflow_action_items["uuid-red"].visible, true);
assert.equal(list.workflow_action_items["uuid-other"].visible, false);
frappe.xcall = async () => [];
await list.toggle_workflow_actions();
assert.equal(list.workflow_action_items["uuid-red"].visible, false);
console.log(
  "Workflow style: six styles, neutral/aggregate/local metadata, escaping, icons and both form/list modes passed."
);
