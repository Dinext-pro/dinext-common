import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
const root = process.argv[2] || fileURLToPath(new URL("..", import.meta.url));
const source = fs.readFileSync(root + "/dinext_common/public/js/workflow_fingerprint_settings.js", "utf8");
const f = (fieldname, fieldtype = "Data", extra = {}) => ({ fieldname, label: fieldname, fieldtype, ...extra });
const meta = {
    Source: { fields: [f("title"), f("amount"), f("status"), f("workflow_state"), f("modified"),
        f("secret", "Password"), f("virtual", "Float", { virtual: 1 }),
        f("table", "Table", { options: "Child" })] },
    Child: { fields: [f("hours"), f("utilized_hours"), f("name"), f("__unsaved"), f("secret", "Password")] },
    Other: { fields: [f("title")] },
};
const handlers = {};
const context = {
    Set, Promise,
    __: (value, args) => args ? value.replace(/\{(\d+)\}/g, (_all, i) => args[i]) : value,
    frappe: {
        model: { with_doctype: async () => {} },
        get_meta: (doctype) => meta[doctype],
        ui: { form: { on(doctype, events) { handlers[doctype] = events; } } },
    },
};
vm.runInNewContext(source, context);
function form(doctype) {
    const props = {};
    return {
        doc: { document_type: doctype, workflow_state_field: "workflow_state",
            states: [{ update_field: "status" }], custom_fingerprint_excluded_fields: [{ field_path: "amount" }] },
        perm: [{ write: 1 }],
        fields_dict: { custom_fingerprint_excluded_fields: { grid: {
            update_docfield_property(name, key, value) { props[key] = value; },
        } } },
        refresh_field() {},
        props,
    };
}
const one = form("Source");
await handlers.Workflow.refresh(one);
assert.deepEqual(Array.from(one.props.options, (row) => row.value).sort(),
    ["amount", "table", "table.hours", "table.utilized_hours", "title"]);
assert.ok(one.props.options.find((row) => row.value === "table").label.includes("entire table"));
assert.equal(one.props.ignore_validation, true);
one.doc.document_type = "Other";
await handlers.Workflow.document_type(one);
assert.deepEqual(Array.from(one.props.options, (row) => row.value), ["title"]);
assert.equal(one.doc.custom_fingerprint_excluded_fields[0].field_path, "amount");
const two = form("Source");
await handlers.Workflow.refresh(two);
assert.equal(one.props.options.length, 1);
assert.ok(two.props.options.length > 1);
two.perm = [{ write: 0 }];
context.frappe.model.with_doctype = () => { throw Error("Read-only form loaded source metadata"); };
await handlers.Workflow.refresh(two);
console.log("Workflow choices: persisted paths, whole tables, invalid-row retention, form isolation and read-only access passed.");
