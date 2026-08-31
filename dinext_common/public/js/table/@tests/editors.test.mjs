import test from "node:test";
import assert from "node:assert/strict";

import { parseBooleanValue, parseDateValue, parseLocaleNumber, parseSelectValue } from "../core/edit/editors.js";
import { formatSelectValue, resolveSelectSpec } from "../core/edit/select-utils.js";
import { selectValueFormatter, selectValueParser } from "../core/edit/select-editor.js";

test("parseBooleanValue accepts booleans and common literals", () => {
    assert.equal(parseBooleanValue(true), true);
    assert.equal(parseBooleanValue(false), false);
    assert.equal(parseBooleanValue("true"), true);
    assert.equal(parseBooleanValue("FALSE"), false);
    assert.equal(parseBooleanValue("1"), true);
    assert.equal(parseBooleanValue("0"), false);
    assert.equal(parseBooleanValue("да"), true);
    assert.equal(parseBooleanValue("нет"), false);
});

test("parseBooleanValue returns null for empty or unknown input", () => {
    assert.equal(parseBooleanValue(""), null);
    assert.equal(parseBooleanValue(null), null);
    assert.equal(parseBooleanValue("maybe"), null);
    assert.equal(parseBooleanValue(2), null);
});

test("parseLocaleNumber still parses decimals", () => {
    assert.equal(parseLocaleNumber("1,5"), 1.5);
    assert.equal(parseLocaleNumber("2"), 2);
});

test("parseDateValue normalizes to ISO YYYY-MM-DD", () => {
    assert.equal(parseDateValue("2026-07-19"), "2026-07-19");
    assert.equal(parseDateValue("2026-07-19T12:00:00"), "2026-07-19");
    assert.equal(parseDateValue("19.07.2026"), "2026-07-19");
    assert.equal(parseDateValue("19/07/2026"), "2026-07-19");
    assert.equal(parseDateValue(""), null);
    assert.equal(parseDateValue(null), null);
    assert.equal(parseDateValue("not-a-date"), null);
});

const PRIORITY = ["High", "Medium", "Low"];
const PRIORITY_LABELS = { High: "Высокий", Medium: "Средний", Low: "Низкий" };

test("parseSelectValue maps key or label to option key", () => {
    assert.equal(parseSelectValue("High", PRIORITY), "High");
    assert.equal(parseSelectValue("high", PRIORITY), "High");
    assert.equal(parseSelectValue("  Medium  ", PRIORITY), "Medium");
    assert.equal(parseSelectValue("Высокий", PRIORITY, { labels: PRIORITY_LABELS }), "High");
});

test("parseSelectValue unknown or empty becomes null, never raw", () => {
    assert.equal(parseSelectValue("Urgent", PRIORITY), null);
    assert.equal(parseSelectValue("not-an-option", PRIORITY), null);
    assert.equal(parseSelectValue("", PRIORITY), null);
    assert.equal(parseSelectValue(null, PRIORITY), null);
    assert.equal(parseSelectValue("High", []), null);
});

test("selectValueParser reads cellEditorParams.values; unknown → null", () => {
    const params = {
        newValue: "Medium",
        colDef: { cellEditorParams: { values: PRIORITY } }
    };
    assert.equal(selectValueParser(params), "Medium");
    assert.equal(selectValueParser({ ...params, newValue: "Nope" }), null);
    assert.equal(
        selectValueParser({
            newValue: "Высокий",
            colDef: { cellEditorParams: { values: PRIORITY, labels: PRIORITY_LABELS } }
        }),
        "High"
    );
});

test("selectValueParser accepts values as function", () => {
    const params = {
        newValue: "Low",
        data: { allowed: PRIORITY },
        colDef: {
            cellEditorParams: {
                values: (p) => p.data.allowed
            }
        }
    };
    assert.equal(selectValueParser(params), "Low");
});

test("formatSelectValue uses labels map when present", () => {
    assert.equal(formatSelectValue("High", { labels: PRIORITY_LABELS }), "Высокий");
    assert.equal(formatSelectValue("High"), "High");
    assert.equal(formatSelectValue(null), "");
    assert.equal(
        selectValueFormatter({
            value: "Low",
            colDef: { cellEditorParams: { values: PRIORITY, labels: PRIORITY_LABELS } }
        }),
        "Низкий"
    );
});

test("parseSelectValue matches frappe __ label via globalThis", () => {
    const prev = globalThis.__;
    globalThis.__ = (key) => (key === "High" ? "Высокий" : key);
    try {
        assert.equal(parseSelectValue("Высокий", PRIORITY), "High");
        assert.equal(formatSelectValue("High"), "Высокий");
    } finally {
        if (prev === undefined) {
            delete globalThis.__;
        } else {
            globalThis.__ = prev;
        }
    }
});

test("resolveSelectSpec reads function cellEditorParams", () => {
    const spec = resolveSelectSpec({
        colDef: {
            cellEditorParams: () => ({ values: PRIORITY, labels: PRIORITY_LABELS })
        }
    });
    assert.deepEqual(spec.values, PRIORITY);
    assert.equal(spec.labels.High, "Высокий");
});
