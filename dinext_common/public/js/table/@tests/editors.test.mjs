import test from "node:test";
import assert from "node:assert/strict";

import { parseBooleanValue, parseLocaleNumber } from "../core/edit/editors.js";

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
