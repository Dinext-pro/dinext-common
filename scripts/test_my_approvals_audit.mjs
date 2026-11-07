import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const escape = (s) => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
let language = 'ru';
const dictionary = {'Manual':'Вручную','Approve':'Согласовать','Reject':'Отклонить','Completed':'Выполнено','{0} voted {1}{2}':'{0} выбрал(а) {1}{2}'};
const frappe = {utils: {escape_html: escape}, ui: {}, dinext: {}};
const context = {frappe, window: {}, document: {addEventListener() {}}, __: (s,args,ctx) => {
  let text = language === 'ru' ? dictionary[s] || s : s;
  return text.replace(/\{(\d+)\}/g, (_,i) => args?.[i] ?? `{${i}}`);
}};
vm.runInNewContext(fs.readFileSync('dinext_common/public/js/workflow_approval.js','utf8'), context);
assert.equal(typeof frappe.dinext.normalizeWorkflowComment, 'function');
const normalize = frappe.dinext.normalizeWorkflowComment;
for (const value of ['', '  ', '<p>&nbsp;</p>', '\u200B\u0000', '&lt;b&gt;&lt;/b&gt;']) assert.equal(normalize(value), '');
assert.equal(normalize(' <b>Reason</b>\u0000 '), 'Reason');
assert.equal([...normalize('😀'.repeat(4000))].length, 4000);
const format = frappe.dinext.approvalReportFormatter;
const normal = value => String(value);
assert.equal(format('Manual', null, {fieldname:'completion_source'}, {}, normal), 'Вручную');
assert.equal(format('Approve, Reject', null, {fieldname:'available_actions'}, {available_transitions:[{action:'Approve'},{action:'Reject'}]}, normal), 'Согласовать, Отклонить');
const saved = '<strong>alice@example.invalid</strong> voted <strong>Approve</strong>: &lt;script&gt;';
const event = frappe.dinext.localizeApprovalEvent(saved);
assert.equal(event, '<strong>alice@example.invalid</strong> выбрал(а) <strong>Согласовать</strong>: &lt;script&gt;');
assert.equal(frappe.dinext.localizeApprovalEvent('My arbitrary note says voted Approve'), null);
assert.equal(frappe.dinext.localizeApprovalEvent('<img src=x onerror=alert(1)> voted Approve'), null);
language = 'en';
assert.equal(format('Manual', null, {fieldname:'completion_source'}, {}, normal), 'Manual');
console.log('approval normalization, localized canonical values and safe legacy events: PASS');
frappe.query_reports = {};
frappe.datetime = {add_days: () => '', get_today: () => ''};
vm.runInNewContext(fs.readFileSync('dinext_common/dinext_common/report/approval_duration/approval_duration.js','utf8'), context);
const dateFilters = frappe.query_reports['Approval Duration'].filters.filter((df) => ['from_date','to_date'].includes(df.fieldname));
for (const filter of dateFilters) {
  assert.equal(typeof filter.on_change, 'function', 'calendar changes must exit the card cutoff');
  const state = {cutoff: '2026-10-08 13:15:42', _no_refresh: true,
    get_filter_value() {return this.cutoff;}, set_filter_value(name, value) {this.cutoff = value;}, refresh() {}};
  filter.on_change(state);
  assert.notEqual(state.cutoff, '', 'route initialization retains the timestamp cutoff');
  state._no_refresh = false;
  filter.on_change(state);
  assert.equal(state.cutoff, '', 'manual calendar editing uses standalone calendar semantics');
}
console.log('duration calendar filter preserves route cutoff and clears it on user edits: PASS');
let inputChanged, shown, focused = false, disabled = false;
let value = '';
let required = true;
const dialog = {fields_dict: {comment: {$input: {on(_events, handler) {inputChanged = handler;}}, set_focus() {focused = true;}}},
  $wrapper: {on(_event, handler) {shown = handler;}}, get_value() {return value;},
  disable_primary_action() {disabled = true;}, enable_primary_action() {disabled = false;}};
const validation = frappe.dinext.bindWorkflowCommentValidation(dialog, () => required);
assert.equal(disabled, true);
shown();
assert.equal(focused, true);
for (const invalid of ['', '   ', '<p>&nbsp;</p>', '\u200b\u0000', 'x'.repeat(4001)]) {
  value = invalid; inputChanged(); assert.equal(disabled, true);
}
value = 'Valid reason'; inputChanged(); assert.equal(disabled, false);
validation.setSubmitting(true); inputChanged(); assert.equal(disabled, true);
validation.setSubmitting(false); assert.equal(disabled, false);
required = false; value = ''; inputChanged(); assert.equal(disabled, false);
value = 'x'.repeat(4001); inputChanged(); assert.equal(disabled, true);
console.log('dialog focus, normalized validity and in-flight primary-button state: PASS');
const nested = '&amp;lt;b&amp;gt;&amp;lt;/b&amp;gt;';
assert.equal(normalize(nested), '&lt;b&gt;&lt;/b&gt;');
let submitted;
frappe.ui.Dialog = class {
  constructor(options) {
    this.options = options;
    this.fields_dict = {comment: {$input: {on() {}}, set_focus() {}}};
    this.$wrapper = {on() {}};
  }
  get_value() { return nested; }
  disable_primary_action() {}
  enable_primary_action() {}
  show() {}
  hide() {}
};
const single = frappe.dinext.withWorkflowComment({action: 'Approve', comment_is_required: 1}, (raw) => {submitted = raw;});
await single.options.primary_action();
assert.equal(submitted, nested, 'single dialog must submit raw input for exactly one server normalization');
assert.equal(frappe.dinext.localizeApprovalEvent('<strong>alice@example.invalid</strong> voted <strong>Approve</strong>: It&apos;s fine'),
  '<strong>alice@example.invalid</strong> voted <strong>Approve</strong>: It\'s fine');
console.log('single raw nested-entity submission and legacy apostrophes: PASS');

const parityCases = JSON.parse(fs.readFileSync('dinext_common/tests/fixtures/approval_comment_normalization.json', 'utf8'));
assert.deepEqual(parityCases.map(({raw}) => normalize(raw)), parityCases.map(({normalized}) => normalized),
  'client matches authoritative Python normalization without joining split references');
console.log('split controls, tags, numeric and nested entities match authoritative Python: PASS');
