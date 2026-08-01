import test from "node:test";
import assert from "node:assert/strict";

import {
    getPersistStorageKey,
    parseUiPersistRaw,
    serializeUiPersist
} from "../core/toolbar/persist.js";

test("getPersistStorageKey namespaces persistKey", () => {
    assert.equal(getPersistStorageKey(null), null);
    assert.equal(getPersistStorageKey(""), null);
    assert.equal(getPersistStorageKey("we:PROJ"), "dinext-table:toolbar:we:PROJ");
});

test("parseUiPersistRaw legacy 1/0", () => {
    assert.deepEqual(parseUiPersistRaw("1"), { pinned: true, filter: null });
    assert.deepEqual(parseUiPersistRaw("0"), { pinned: false, filter: null });
    assert.deepEqual(parseUiPersistRaw(null), { pinned: null, filter: null });
});

test("parseUiPersistRaw JSON v2", () => {
    const raw = serializeUiPersist({
        pinned: true,
        filter: { active: true, state: { name: "  Foo  ", empty: "" } }
    });
    assert.deepEqual(parseUiPersistRaw(raw), {
        pinned: true,
        filter: {
            active: true,
            state: { name: "Foo" }
        }
    });
});

test("parseUiPersistRaw ignores junk", () => {
    assert.deepEqual(parseUiPersistRaw("{"), { pinned: null, filter: null });
    assert.deepEqual(parseUiPersistRaw("[]"), { pinned: null, filter: null });
});

test("serializeUiPersist always writes filter object", () => {
    assert.equal(
        serializeUiPersist({ pinned: false }),
        JSON.stringify({ pinned: false, filter: { active: false, state: {} } })
    );
});
