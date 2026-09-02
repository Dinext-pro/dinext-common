import test from "node:test";
import assert from "node:assert/strict";

import { dateValueParser } from "../core/edit/date-editor.js";
import { parseBooleanValue, parseDateValue, parseLocaleNumber } from "../core/edit/editors.js";

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
