import test from "node:test";
import assert from "node:assert/strict";

import { TreeMixin } from "../core/tree/mixin.js";
import { normalizeColumns } from "../core/shared/utils.js";
import { makeRow } from "./helpers/fixtures.mjs";

/* Minimal DOM for createTreeCellRenderer (node has no document/HTMLElement). */
class FakeEl {
    constructor(tag) {
        this.tagName = String(tag).toUpperCase();
        this.className = "";
        this.children = [];
        this.style = {};
        this.textContent = "";
        this.onclick = null;
        const classes = new Set();
        this.classList = {
            add: (...names) => names.forEach((n) => classes.add(n)),
            toggle: (name, force) => {
                if (force === undefined) {
                    force = !classes.has(name);
                }
                force ? classes.add(name) : classes.delete(name);
                return force;
            },
            contains: (name) => classes.has(name)
        };
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    replaceChildren(...nodes) {
        this.children = [...nodes];
    }
}

globalThis.HTMLElement = FakeEl;
globalThis.document = { createElement: (tag) => new FakeEl(tag) };

class FakeBase {
    constructor(options) {
        this.options = options;
        this.columns = options.columns || [];
        this.sourceData = [];
        this.rowData = [];
        this.api = null;
        this.gridCalls = [];
        this.initFeatures();
    }

    initFeatures() {}

    buildColumnDefs() {
        return normalizeColumns(this.columns, this.options.edit);
    }

    refresh(data) {
        if (data !== undefined) {
            this.sourceData = data;
            this.options.data = data;
        }
        this.syncVisibleRows();
        this.setGridOption("rowData", this.rowData);
    }

    setGridOption(key, value) {
        this.gridCalls.push([key, value]);
    }
}

const TreeTable = TreeMixin(FakeBase);

const renderA = (params) => {
    const el = new FakeEl("span");
    el.className = "domain-content";
    el.textContent = `render:${params.value}`;
    return el;
};

const flatData = () => [makeRow("1"), makeRow("2")];
const nestedData = () => [makeRow("1", { children: [makeRow("1.1")] }), makeRow("2")];

function leafDef(defs, field) {
    for (const def of defs) {
        if (Array.isArray(def.children)) {
            const hit = leafDef(def.children, field);
            if (hit) return hit;
            continue;
        }
        if (def.field === field) return def;
    }
    return null;
}

function columnDefsCalls(table) {
    return table.gridCalls.filter(([key]) => key === "columnDefs");
}

test("flat data + render on tree column composes tree cellRenderer", () => {
    const table = new TreeTable({
        data: flatData(),
        columns: [{ field: "a", tree: true, render: renderA }, { field: "b" }]
    });

    assert.equal(table.hasNestedRows(), false);
    assert.equal(table.rowData, table.sourceData);

    const def = leafDef(table.buildColumnDefs(), "a");
    assert.equal(typeof def.cellRenderer, "function");
    assert.equal(leafDef(table.buildColumnDefs(), "b").cellRenderer, undefined);
    for (const key of ["render", "tree", "treeContentKey", "edit"]) {
        assert.equal(key in def, false, `${key} leaked into colDef`);
    }
});

test("flat data + treeContentKey only still composes tree cellRenderer", () => {
    const table = new TreeTable({
        data: flatData(),
        columns: [{ field: "a", treeContentKey: () => "k" }]
    });
    assert.equal(typeof leafDef(table.buildColumnDefs(), "a").cellRenderer, "function");
});

test("flat data without render keeps AG default (no tree cellRenderer)", () => {
    const table = new TreeTable({
        data: flatData(),
        columns: [{ field: "a" }, { field: "b" }]
    });
    assert.equal(leafDef(table.buildColumnDefs(), "a").cellRenderer, undefined);
});

test("flat data + render on opted-out column: no tree column, no renderer, warns", () => {
    const warnings = [];
    const original = console.warn;
    console.warn = (msg) => warnings.push(String(msg));
    try {
        const table = new TreeTable({
            data: flatData(),
            columns: [{ field: "a", tree: false, render: renderA }, { field: "b" }]
        });
        assert.equal(table.getTreeColumnField(), null);
        assert.equal(leafDef(table.buildColumnDefs(), "a").cellRenderer, undefined);
        assert.equal(warnings.length, 1);
        assert.match(warnings[0], /"a"/);
        assert.match(warnings[0], /tree column: none/);
    } finally {
        console.warn = original;
    }
});

test("nested data without render composes tree cellRenderer (unchanged)", () => {
    const table = new TreeTable({
        data: nestedData(),
        columns: [{ field: "a" }]
    });
    assert.equal(table.hasNestedRows(), true);
    assert.equal(typeof leafDef(table.buildColumnDefs(), "a").cellRenderer, "function");
});

test("tree cellRenderer: no toggle / indent for rows without _hasChildren, domain render mounted", () => {
    const table = new TreeTable({
        data: flatData(),
        columns: [{ field: "a", tree: true, render: renderA }]
    });
    const Renderer = leafDef(table.buildColumnDefs(), "a").cellRenderer;

    const flat = new Renderer();
    flat.init({ data: table.rowData[0], value: "1", context: { dinextTable: table } });
    assert.equal(flat.leadEl.children.length, 0);
    assert.equal(flat.eGui.style.paddingLeft, "0px");
    assert.equal(flat.contentEl.children.length, 1);
    assert.equal(flat.contentEl.children[0].className, "domain-content");
    assert.equal(flat.contentEl.children[0].textContent, "render:1");

    const parent = new Renderer();
    parent.init({
        data: { ...makeRow("3"), _rowId: "3", _level: 1, _hasChildren: true },
        value: "3",
        context: { dinextTable: table }
    });
    assert.equal(parent.leadEl.children.length, 1);
    assert.equal(parent.leadEl.children[0].className, "dinext-table-tree-toggle");
    assert.equal(parent.leadEl.children[0].classList.contains("is-collapsed"), true);
    assert.equal(parent.eGui.style.paddingLeft, "20px");
});

test("refresh rebuilds columnDefs only when hasNestedRows flips", () => {
    const table = new TreeTable({
        data: flatData(),
        columns: [{ field: "a" }]
    });
    table.buildColumnDefs();
    assert.equal(columnDefsCalls(table).length, 0);

    table.refresh(flatData());
    assert.equal(columnDefsCalls(table).length, 0);

    table.refresh(nestedData());
    assert.equal(columnDefsCalls(table).length, 1);
    assert.equal(typeof leafDef(columnDefsCalls(table)[0][1], "a").cellRenderer, "function");
    assert.deepEqual(table.rowData.map((row) => row._rowId), ["1", "2"]);

    table.refresh(nestedData());
    assert.equal(columnDefsCalls(table).length, 1);

    table.refresh(flatData());
    assert.equal(columnDefsCalls(table).length, 2);
    assert.equal(leafDef(columnDefsCalls(table)[1][1], "a").cellRenderer, undefined);
    assert.equal(table.rowData, table.sourceData);
});

test("refresh skips columnDefs rebuild on flips when tree column declares render", () => {
    const table = new TreeTable({
        data: flatData(),
        columns: [{ field: "a", tree: true, render: renderA }]
    });
    table.buildColumnDefs();
    table.refresh(nestedData());
    table.refresh(flatData());
    assert.equal(columnDefsCalls(table).length, 0);
});

test("warns once when render/treeContentKey sit on a non-tree column", () => {
    const warnings = [];
    const original = console.warn;
    console.warn = (msg) => warnings.push(String(msg));
    try {
        const table = new TreeTable({
            data: nestedData(),
            columns: [{ field: "a", tree: true }, { field: "b", render: renderA }]
        });
        table.buildColumnDefs();
        table.buildColumnDefs();
        assert.equal(warnings.length, 1);
        assert.match(warnings[0], /"b"/);
        assert.match(warnings[0], /tree column: "a"/);

        const clean = new TreeTable({
            data: nestedData(),
            columns: [{ field: "a", tree: true, render: renderA }, { field: "b" }]
        });
        clean.buildColumnDefs();
        assert.equal(warnings.length, 1);
    } finally {
        console.warn = original;
    }
});
