import test from "node:test";
import assert from "node:assert/strict";

import {
    normalizeToolbarItem,
    getPersistStorageKey,
    resolveToolbarValue
} from "../core/toolbar/utils.js";
import { findAgGridRootElement, findGridMountElement } from "../core/shared/utils.js";

function makeElement({ className = "", children = [], querySelectorResult = null } = {}) {
    return {
        classList: {
            contains(name) {
                return className.split(/\s+/).filter(Boolean).includes(name);
            }
        },
        matches(selector) {
            if (selector.includes("ag-root-wrapper") && className.includes("ag-root-wrapper")) {
                return true;
            }
            if (selector.includes("ag-root") && className.includes("ag-root")) {
                return true;
            }
            return false;
        },
        querySelector() {
            return querySelectorResult;
        },
        children
    };
}

test("findGridMountElement skips table chrome and returns direct grid child", () => {
    const gridMount = makeElement({ className: "ag-root-wrapper" });
    const container = {
        children: [
            makeElement({ className: "dinext-table-status-bar" }),
            gridMount
        ]
    };

    assert.equal(findGridMountElement(container), gridMount);
});

test("findGridMountElement prefers wrapper child over nested ag-root-wrapper", () => {
    const nestedGrid = makeElement({ className: "ag-root-wrapper" });
    const gridMount = makeElement({
        className: "ag-grid-host",
        querySelectorResult: nestedGrid
    });
    const container = { children: [gridMount] };

    assert.equal(findGridMountElement(container), gridMount);
    assert.equal(findAgGridRootElement(container), nestedGrid);
});

test("normalizeToolbarItem maps button fields with stable id fallback", () => {
    assert.deepEqual(normalizeToolbarItem({ label: "Export" }, 0), {
        type: "button",
        id: "item-0",
        label: "Export",
        title: "Export",
        icon: null,
        iconSvg: null,
        align: null,
        zone: null,
        disabled: undefined,
        hidden: undefined,
        active: undefined,
        onClick: undefined
    });
});

test("normalizeToolbarItem preserves explicit id and title", () => {
    const onClick = () => {};
    assert.deepEqual(
        normalizeToolbarItem({
            id: "refresh",
            label: "Refresh",
            title: "Reload rows",
            icon: "icon-refresh",
            disabled: true,
            onClick
        }, 3),
        {
            type: "button",
            id: "refresh",
            label: "Refresh",
            title: "Reload rows",
            icon: "icon-refresh",
            iconSvg: null,
            align: null,
            zone: null,
            disabled: true,
            hidden: undefined,
            active: undefined,
            onClick
        }
    );
});

test("normalizeToolbarItem maps separator with id fallback", () => {
    assert.deepEqual(normalizeToolbarItem({ type: "separator" }, 2), {
        type: "separator",
        id: "sep-2",
        zone: null
    });
    assert.deepEqual(normalizeToolbarItem(null, 1), {
        type: "separator",
        id: "sep-1",
        zone: null
    });
});

test("normalizeToolbarItem maps checkbox fields", () => {
    const onChange = () => {};
    const checked = () => true;
    assert.deepEqual(
        normalizeToolbarItem({
            type: "checkbox",
            id: "select-all-rows",
            title: "Select all rows",
            checked,
            indeterminate: false,
            onChange
        }, 0),
        {
            type: "checkbox",
            id: "select-all-rows",
            label: "",
            title: "Select all rows",
            align: null,
            zone: null,
            disabled: undefined,
            hidden: undefined,
            checked,
            indeterminate: false,
            onChange
        }
    );
});

test("normalizeToolbarItem maps custom panel fields", () => {
    const render = () => {};
    const element = { nodeName: "DIV" };
    assert.deepEqual(
        normalizeToolbarItem({
            type: "custom",
            id: "domain-actions",
            align: "end",
            zone: "custom",
            element,
            render,
            hidden: false
        }, 2),
        {
            type: "custom",
            id: "domain-actions",
            align: "end",
            zone: "custom",
            hidden: false,
            element,
            render
        }
    );
    assert.equal(normalizeToolbarItem({ type: "custom" }, 1).id, "custom-1");
});

test("getPersistStorageKey returns namespaced key or null", () => {
    assert.equal(getPersistStorageKey(null), null);
    assert.equal(getPersistStorageKey(""), null);
    assert.equal(getPersistStorageKey("we-v2"), "dinext-table:toolbar:we-v2");
});

test("resolveToolbarValue resolves functions and statics", () => {
    assert.equal(resolveToolbarValue("Select all", {}, ""), "Select all");
    assert.equal(
        resolveToolbarValue(({ table }) => (table.all ? "Clear" : "Select"), { table: { all: true } }, ""),
        "Clear"
    );
    assert.equal(resolveToolbarValue(null, {}, "fallback"), "fallback");
});
