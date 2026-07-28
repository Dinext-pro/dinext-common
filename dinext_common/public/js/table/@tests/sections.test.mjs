import test from "node:test";
import assert from "node:assert/strict";

import {
    TABLE_SECTIONS,
    getRowSection,
    isSummarySectionRow,
    stampSummaryRows
} from "../core/section/sections.js";
import { findSourceRowInData } from "../core/tree/model.js";

test("getRowSection defaults to body", () => {
    assert.equal(getRowSection({ id: 1 }), TABLE_SECTIONS.BODY);
    assert.equal(getRowSection({ id: 1, _section: "body" }), TABLE_SECTIONS.BODY);
});

test("getRowSection detects summary", () => {
    assert.equal(getRowSection({ id: "t", _section: "summary" }), TABLE_SECTIONS.SUMMARY);
    assert.equal(isSummarySectionRow({ _section: "summary" }), true);
});

test("stampSummaryRows adds _section without mutating source", () => {
    const source = [{ id: "total", a: 1 }];
    const stamped = stampSummaryRows(source);
    assert.equal(source[0]._section, undefined);
    assert.equal(stamped[0]._section, TABLE_SECTIONS.SUMMARY);
});

test("findSourceRowInData resolves nested path", () => {
    const rows = [{
        id: "root",
        children: [{ id: "child", value: 5 }]
    }];
    const row = findSourceRowInData(rows, "root:child", { rowIdField: "id", childrenField: "children" });
    assert.equal(row.value, 5);
});
