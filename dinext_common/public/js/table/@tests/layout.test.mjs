import test from "node:test";
import assert from "node:assert/strict";

import {
    parseLayoutSizePx,
    resolveDesiredLayoutHeight,
    resolveLayoutHeightMode,
    resolveLayoutMaxPx,
    sumLayoutChromePx
} from "../core/layout.js";

test("resolveLayoutHeightMode defaults to host", () => {
    assert.equal(resolveLayoutHeightMode({}), "host");
    assert.equal(resolveLayoutHeightMode({ layout: {} }), "host");
    assert.equal(resolveLayoutHeightMode({ layout: { height: "host" } }), "host");
    assert.equal(resolveLayoutHeightMode({ layout: { height: "auto" } }), "auto");
});

test("parseLayoutSizePx keeps numbers and px, leaves CSS strings", () => {
    assert.equal(parseLayoutSizePx(null), null);
    assert.equal(parseLayoutSizePx(""), null);
    assert.equal(parseLayoutSizePx(672), 672);
    assert.equal(parseLayoutSizePx("280px"), 280);
    assert.equal(parseLayoutSizePx("min(60vh, 672px)"), "min(60vh, 672px)");
});

test("sumLayoutChromePx adds chrome + slack", () => {
    assert.equal(sumLayoutChromePx({
        toolbarPx: 36,
        headerPx: 44,
        bodyPx: 56,
        summaryPx: 58,
        slackPx: 2
    }), 36 + 44 + 56 + 58 + 2);
});

test("resolveDesiredLayoutHeight hugs content under max", () => {
    assert.equal(resolveDesiredLayoutHeight({
        contentPx: 220,
        maxPx: 672
    }), 220);
});

test("resolveDesiredLayoutHeight caps at maxHeight", () => {
    assert.equal(resolveDesiredLayoutHeight({
        contentPx: 2000,
        maxPx: 672
    }), 672);
});

test("resolveDesiredLayoutHeight honors minHeight only when set", () => {
    assert.equal(resolveDesiredLayoutHeight({
        contentPx: 120,
        minPx: 280,
        maxPx: 672
    }), 280);
    assert.equal(resolveDesiredLayoutHeight({
        contentPx: 120,
        minPx: 0,
        maxPx: 672
    }), 120);
});

test("resolveLayoutMaxPx uses host viewport in fullscreen, option max otherwise", () => {
    assert.equal(resolveLayoutMaxPx({
        fullscreen: false,
        availablePx: 900,
        optionMaxPx: 672
    }), 672);
    assert.equal(resolveLayoutMaxPx({
        fullscreen: true,
        availablePx: 900,
        optionMaxPx: 672
    }), 900);
    assert.equal(resolveLayoutMaxPx({
        fullscreen: true,
        availablePx: null,
        optionMaxPx: 672
    }), null);
});

test("resolveDesiredLayoutHeight in FS hugs short content under viewport", () => {
    assert.equal(resolveDesiredLayoutHeight({
        contentPx: 220,
        maxPx: resolveLayoutMaxPx({
            fullscreen: true,
            availablePx: 900,
            optionMaxPx: 672
        })
    }), 220);
});

test("resolveDesiredLayoutHeight in FS caps tall content at viewport not option max", () => {
    assert.equal(resolveDesiredLayoutHeight({
        contentPx: 2000,
        maxPx: resolveLayoutMaxPx({
            fullscreen: true,
            availablePx: 900,
            optionMaxPx: 672
        })
    }), 900);
});
