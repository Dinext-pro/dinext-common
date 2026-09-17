import test from "node:test";
import assert from "node:assert/strict";

import { dateValueParser } from "../core/edit/date-editor.js";
import { localeNumberValueParser, parseBooleanValue, parseDateValue, parseLocaleNumber, parseSelectValue } from "../core/edit/editors.js";
import { isAllowedNumberDraft, isNumberDraft } from "../core/edit/number-utils.js";
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
    assert.equal(parseLocaleNumber("abc"), null);
});

test("localeNumberValueParser keeps old value on garbage", () => {
    assert.equal(localeNumberValueParser({ newValue: "abc", oldValue: 4 }), 4);
    assert.equal(localeNumberValueParser({ newValue: "", oldValue: 4 }), null);
    assert.equal(localeNumberValueParser({ newValue: "1,5", oldValue: 4 }), 1.5);
});

test("isNumberDraft allows locale decimals and rejects letters", () => {
    assert.equal(isNumberDraft("1"), true);
    assert.equal(isNumberDraft("1,"), true);
    assert.equal(isNumberDraft("1,5"), true);
    assert.equal(isNumberDraft(".5"), true);
    assert.equal(isNumberDraft("-"), true);
    assert.equal(isNumberDraft("ab"), false);
    assert.equal(isNumberDraft("1a"), false);
    assert.equal(isNumberDraft("1,2,3"), false);
    assert.equal(isNumberDraft("1.5", true), false);
});

test("isAllowedNumberDraft rejects inserting a letter", () => {
    assert.equal(isAllowedNumberDraft("12", "a", 2, 2), false);
    assert.equal(isAllowedNumberDraft("1", ",", 1, 1), true);
    assert.equal(isAllowedNumberDraft("1,5", ".", 1, 1), false);
});

test("parseDateValue normalizes to ISO YYYY-MM-DD", () => {
    assert.equal(parseDateValue("2026-07-19"), "2026-07-19");
    assert.equal(parseDateValue("2026-07-19T12:00:00"), "2026-07-19");
    assert.equal(parseDateValue("2026-07-19 00:00:00"), "2026-07-19");
    assert.equal(parseDateValue("19.07.2026"), "2026-07-19");
    assert.equal(parseDateValue("19/07/2026"), "2026-07-19");
    assert.equal(parseDateValue("19-07-2026"), "2026-07-19");
    assert.equal(parseDateValue(""), null);
    assert.equal(parseDateValue(null), null);
    assert.equal(parseDateValue("not-a-date"), null);
});

test("dateValueParser keeps old value when paste is unparseable", () => {
    assert.equal(dateValueParser({ newValue: "19-07-2026", oldValue: "2026-01-01" }), "2026-07-19");
    assert.equal(dateValueParser({ newValue: "not-a-date", oldValue: "2026-01-01" }), "2026-01-01");
    assert.equal(dateValueParser({ newValue: "", oldValue: "2026-01-01" }), null);
    assert.equal(dateValueParser({ newValue: "not-a-date", oldValue: null }), null);
});

test("parseDateValue reverses frappe.datetime.user_to_str formats", () => {
    const prev = globalThis.frappe;
    globalThis.frappe = {
        datetime: {
            user_to_str: (s) => (s === "19 Sep 2026" ? "2026-09-19" : "Invalid date")
        }
    };
    try {
        assert.equal(parseDateValue("19 Sep 2026"), "2026-09-19");
        assert.equal(parseDateValue("nope"), null);
    } finally {
        if (prev === undefined) {
            delete globalThis.frappe;
        } else {
            globalThis.frappe = prev;
        }
    }
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
