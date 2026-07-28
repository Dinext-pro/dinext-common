import test from "node:test";
import assert from "node:assert/strict";

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
    assert.equal(parseDateValue("19.07.2026"), "2026-07-19");
    assert.equal(parseDateValue("19/07/2026"), "2026-07-19");
    assert.equal(parseDateValue(""), null);
    assert.equal(parseDateValue(null), null);
    assert.equal(parseDateValue("not-a-date"), null);
});
