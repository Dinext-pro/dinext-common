import test from "node:test";
import assert from "node:assert/strict";

import { ROW_REORDER_POSITIONS, ROW_REORDER_TREE_MODES } from "../core/row-reorder/constants.js";
import {
    collectDraggedRowIds,
    collectLocalRowIds,
    isSelfOrDescendantId,
    remapPathIdSet,
    resolveDropTarget,
    resolveReorderContext,
    restoreCrossParentOrders
} from "../core/row-reorder/ops.js";
import { findSourceRowInData } from "../core/tree/model.js";
import {
    isDraggedPreviewRowId,
    resolveNestParentHit,
    resolveVerticalIntent
} from "../core/row-reorder/preview.js";
import {
    NEST_SHIFT_PX,
    SWAP_EDGE_PX,
    childIds,
    clone,
    expandedSet,
    flatAbc,
    flatAbcd,
    flattenVisible,
    hitY,
    hitsFromVisible,
    localIds,
    mergeHeadTailPlusPlain,
    simulateRowReorder,
    treeDeepThreeLevels,
    treeExpandedBranchPair,
    treeParentWithTwoChildren,
    treeSelfNestGuard,
    treeTwoRootsOneChild
} from "./helpers/row-reorder-fixtures.mjs";

function assertCommit(result) {
    assert.equal(result.kind, "commit", JSON.stringify({
        kind: result.kind,
        intent: result.intent,
        drop: result.drop
    }));
}

function previewById(preview) {
    return Object.fromEntries((preview || []).map((item) => [item.rowId, item]));
}

// --- Flat sibling reorder ---

test("TC-01 flat drag a after b → b,a,c and payload order", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["b", "a", "c"]);
    assert.equal(result.payload.rowId, "a");
    assert.equal(result.payload.newRowId, "a");
    assert.equal(result.payload.fromParentRowId, null);
    assert.equal(result.payload.toParentRowId, null);
    assert.deepEqual(result.payload.orderedLocalRowIds, ["b", "a", "c"]);
    assert.deepEqual(result.payload.orderedRowIds, ["b", "a", "c"]);
    assert.deepEqual(result.payload.fromOrderedLocalRowIds, ["b", "a", "c"]);
});

test("TC-02 flat drag c before a → c,a,b", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "c",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "a",
        hoverEdge: "swapUp"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["c", "a", "b"]);
    assert.deepEqual(result.payload.orderedLocalRowIds, ["c", "a", "b"]);
});

test("TC-03 flat drag b after c → a,c,b", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "b",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["a", "c", "b"]);
});

test("TC-04 flat drag last before first of four → d,a,b,c", () => {
    const result = simulateRowReorder({
        data: flatAbcd(),
        draggedId: "d",
        visibleIds: ["a", "b", "c", "d"],
        hoverRowId: "a",
        hoverEdge: "swapUp"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["d", "a", "b", "c"]);
});

test("TC-05 same slot a before b is home/noop", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "homeDown"
    });
    assert.equal(result.kind, "home");
    assert.deepEqual(localIds(result.data), ["a", "b", "c"]);
});

test("TC-06 pointer still on dragged row is home", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "b",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "mid"
    });
    assert.equal(result.kind, "home");
});

test("TC-07 gap between mapped rows yields no vertical intent", () => {
    const hits = [
        { rowId: "a", top: 0, bottom: 28, height: 28, isDragged: true },
        { rowId: "c", top: 56, bottom: 84, height: 28 }
    ];
    const vertical = resolveVerticalIntent({
        hits,
        clientY: 40,
        draggedIds: ["a"]
    });
    assert.equal(vertical, null);
});

// --- Pointer / nest intent ---

test("TC-08 swap down only after SWAP_EDGE_PX into neighbor", () => {
    const hits = hitsFromVisible(["a", "b"], ["a"]);
    const home = resolveVerticalIntent({
        hits,
        clientY: hitY(hits, "b", "homeDown"),
        draggedIds: ["a"]
    });
    assert.equal(home.home, true);
    const swap = resolveVerticalIntent({
        hits,
        clientY: hitY(hits, "b", "swapDown"),
        draggedIds: ["a"]
    });
    assert.equal(swap.position, ROW_REORDER_POSITIONS.AFTER);
    assert.equal(swap.hoverRowId, "b");
});

test("TC-09 swap up is symmetric to swap down", () => {
    const hits = hitsFromVisible(["b", "a"], ["a"]);
    const home = resolveVerticalIntent({
        hits,
        clientY: hitY(hits, "b", "homeUp"),
        draggedIds: ["a"]
    });
    assert.equal(home.home, true);
    const swap = resolveVerticalIntent({
        hits,
        clientY: hitY(hits, "b", "swapUp"),
        draggedIds: ["a"]
    });
    assert.equal(swap.position, ROW_REORDER_POSITIONS.BEFORE);
    assert.equal(swap.hoverRowId, "b");
});

test("TC-10 right shift below nest threshold stays sibling after", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "swapDown",
        shiftX: NEST_SHIFT_PX - 1
    });
    assertCommit(result);
    assert.equal(result.intent.position, ROW_REORDER_POSITIONS.AFTER);
    assert.deepEqual(localIds(result.data), ["b", "a", "c"]);
});

test("TC-11 drag a after b plus right nests a under b", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "swapDown",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.equal(result.intent.position, ROW_REORDER_POSITIONS.INSIDE);
    assert.equal(result.intent.hoverRowId, "b");
    assert.deepEqual(localIds(result.data), ["b", "c"]);
    assert.deepEqual(childIds(result.data, "b"), ["a"]);
    assert.equal(result.payload.newRowId, "b:a");
    assert.equal(result.payload.toParentRowId, "b");
    assert.deepEqual(result.payload.orderedLocalRowIds, ["a"]);
    assert.deepEqual(result.payload.orderedRowIds, ["b:a"]);
    assert.deepEqual(result.payload.fromOrderedLocalRowIds, ["b", "c"]);
});

test("TC-12 c onto b plus right nests under a not b", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "c",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "swapUp",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.equal(result.intent.hoverRowId, "a");
    assert.equal(result.intent.position, ROW_REORDER_POSITIONS.INSIDE);
    assert.deepEqual(localIds(result.data), ["a", "b"]);
    assert.deepEqual(childIds(result.data, "a"), ["c"]);
    assert.equal(result.payload.newRowId, "a:c");
});

test("TC-13 home plus right nests under the row above", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "c",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.equal(result.intent.hoverRowId, "b");
    assert.deepEqual(childIds(result.data, "b"), ["c"]);
    assert.deepEqual(localIds(result.data), ["a", "b"]);
    assert.equal(result.payload.newRowId, "b:c");
});

test("TC-14 top row home plus right cannot nest", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "a",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assert.equal(result.kind, "home");
});

test("TC-15 allowNest off ignores right shift", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "c",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX,
        allowTree: ROW_REORDER_TREE_MODES.SIBLINGS
    });
    assert.equal(result.kind, "home");
});

test("TC-16 nest parent for AFTER is hover, for BEFORE is previous", () => {
    const hits = hitsFromVisible(["a", "b", "c"], ["c"]);
    const afterB = { home: false, hoverRowId: "b", position: ROW_REORDER_POSITIONS.AFTER };
    const beforeB = { home: false, hoverRowId: "b", position: ROW_REORDER_POSITIONS.BEFORE };
    assert.equal(resolveNestParentHit(hits, afterB, ["c"])?.rowId, "b");
    assert.equal(resolveNestParentHit(hits, beforeB, ["c"])?.rowId, "a");
    assert.equal(resolveNestParentHit(hits, { home: true }, ["c"])?.rowId, "b");
});

// --- Tree mode: siblings vs off ---

test("TC-17 siblings mode reorders inside the same parent", () => {
    const result = simulateRowReorder({
        data: treeParentWithTwoChildren(),
        draggedId: "p:c1",
        visibleIds: ["p", "p:c1", "p:c2", "z"],
        hoverRowId: "p:c2",
        hoverEdge: "swapDown",
        allowTree: ROW_REORDER_TREE_MODES.SIBLINGS
    });
    assertCommit(result);
    assert.deepEqual(childIds(result.data, "p"), ["c2", "c1"]);
    assert.deepEqual(result.payload.orderedRowIds, ["p:c2", "p:c1"]);
    assert.equal(result.payload.toParentRowId, "p");
});

test("TC-18 siblings mode blocks cross-parent drop", () => {
    const result = simulateRowReorder({
        data: treeTwoRootsOneChild(),
        draggedId: "a:a1",
        visibleIds: ["a", "a:a1", "b", "b:b1"],
        hoverRowId: "b:b1",
        hoverEdge: "swapUp",
        allowTree: ROW_REORDER_TREE_MODES.SIBLINGS
    });
    assert.equal(result.kind, "invalid");
});

test("TC-19 siblings mode blocks INSIDE even with right shift", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "swapDown",
        shiftX: NEST_SHIFT_PX,
        allowTree: ROW_REORDER_TREE_MODES.SIBLINGS
    });
    assertCommit(result);
    assert.equal(result.intent.position, ROW_REORDER_POSITIONS.AFTER);
    assert.deepEqual(localIds(result.data), ["b", "a", "c"]);
});

test("TC-20 tree OFF blocks nested row drag", () => {
    const data = treeParentWithTwoChildren();
    const ctx = resolveReorderContext(data, "p:c1");
    const drop = resolveDropTarget({
        sourceRows: data,
        dragCtx: ctx,
        hoverRowId: "p:c2",
        position: ROW_REORDER_POSITIONS.AFTER,
        allowTree: ROW_REORDER_TREE_MODES.OFF
    });
    assert.equal(drop, null);
});

test("TC-21 tree OFF still allows top-level sibling reorder", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "swapDown",
        allowTree: ROW_REORDER_TREE_MODES.OFF
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["b", "a", "c"]);
});

// --- Reparent nest / outdent / cross-parent ---

test("TC-22 nest into parent that already has a child appends last", () => {
    const data = [
        { id: "move" },
        { id: "p", children: [{ id: "c1" }] }
    ];
    const result = simulateRowReorder({
        data,
        draggedId: "move",
        visibleIds: ["move", "p", "p:c1"],
        hoverRowId: "p",
        hoverEdge: "swapDown",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.deepEqual(childIds(result.data, "p"), ["c1", "move"]);
    assert.deepEqual(result.payload.orderedRowIds, ["p:c1", "p:move"]);
    assert.equal(result.payload.toIndex, 1);
});

test("TC-23 reparent leaf across parents after sibling", () => {
    const result = simulateRowReorder({
        data: treeTwoRootsOneChild(),
        draggedId: "a:a1",
        visibleIds: ["a", "a:a1", "b", "b:b1"],
        hoverRowId: "b:b1",
        hoverEdge: "swapDown",
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    });
    assertCommit(result);
    assert.deepEqual(childIds(result.data, "a"), []);
    assert.deepEqual(childIds(result.data, "b"), ["b1", "a1"]);
    assert.equal(result.payload.newRowId, "b:a1");
    assert.equal(result.payload.fromParentRowId, "a");
    assert.equal(result.payload.toParentRowId, "b");
    assert.deepEqual(result.payload.orderedLocalRowIds, ["b1", "a1"]);
    assert.deepEqual(result.payload.fromOrderedLocalRowIds, []);
});

test("TC-24 outdent first child onto parent lands before parent", () => {
    const result = simulateRowReorder({
        data: treeParentWithTwoChildren(),
        draggedId: "p:c1",
        visibleIds: ["p", "p:c1", "p:c2", "z"],
        hoverRowId: "p",
        hoverEdge: "swapUp",
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    });
    assertCommit(result);
    assert.equal(result.drop.toParentRowId, null);
    assert.equal(result.payload.newRowId, "c1");
    assert.deepEqual(localIds(result.data), ["c1", "p", "z"]);
    assert.deepEqual(childIds(result.data, "p"), ["c2"]);
});

test("TC-25 outdent last child onto next root lands after that root", () => {
    const result = simulateRowReorder({
        data: treeParentWithTwoChildren(),
        draggedId: "p:c2",
        visibleIds: ["p", "p:c1", "p:c2", "z"],
        hoverRowId: "z",
        hoverEdge: "swapDown",
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["p", "z", "c2"]);
    assert.deepEqual(childIds(result.data, "p"), ["c1"]);
    assert.equal(result.payload.newRowId, "c2");
    assert.equal(result.payload.toParentRowId, null);
});

test("TC-26 cannot nest row into itself", () => {
    const data = treeSelfNestGuard();
    const ctx = resolveReorderContext(data, "p");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx: ctx,
        hoverRowId: "p",
        position: ROW_REORDER_POSITIONS.INSIDE,
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    }), null);
});

test("TC-27 cannot nest ancestor into descendant", () => {
    const data = treeSelfNestGuard();
    const ctx = resolveReorderContext(data, "p");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx: ctx,
        hoverRowId: "p:c",
        position: ROW_REORDER_POSITIONS.INSIDE,
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    }), null);
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx: ctx,
        hoverRowId: "p:c:g",
        position: ROW_REORDER_POSITIONS.BEFORE,
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    }), null);
});

test("TC-28 nest top-level into deep grandchild path", () => {
    const result = simulateRowReorder({
        data: treeDeepThreeLevels(),
        draggedId: "c",
        visibleIds: ["a", "a:a1", "a:a1:a1x", "a:a2", "b", "c"],
        hoverRowId: "a:a1:a1x",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    const a1 = findSourceRowInData(result.data, "a:a1");
    assert.deepEqual(localIds(a1.children), ["a1x", "a1y", "c"]);
    assert.equal(result.payload.newRowId, "a:a1:c");
    assert.equal(result.payload.toParentRowId, "a:a1");
});

test("TC-29 move level-2 leaf after another level-2 sibling", () => {
    const result = simulateRowReorder({
        data: treeDeepThreeLevels(),
        draggedId: "a:a1:a1x",
        visibleIds: ["a", "a:a1", "a:a1:a1x", "a:a1:a1y", "b", "b:b1", "b:b1:b1x"],
        hoverRowId: "b:b1:b1x",
        hoverEdge: "swapDown",
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    });
    assertCommit(result);
    const a1 = findSourceRowInData(result.data, "a:a1");
    const b1 = findSourceRowInData(result.data, "b:b1");
    assert.deepEqual(localIds(a1.children), ["a1y"]);
    assert.deepEqual(localIds(b1.children), ["b1x", "a1x"]);
    assert.equal(result.payload.newRowId, "b:b1:a1x");
    assert.deepEqual(result.payload.fromOrderedLocalRowIds, ["a1y"]);
});

test("TC-30 lift level-2 leaf to top-level after root", () => {
    const result = simulateRowReorder({
        data: treeDeepThreeLevels(),
        draggedId: "a:a1:a1y",
        visibleIds: ["a", "a:a1", "a:a1:a1x", "a:a1:a1y", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "swapDown",
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    });
    assertCommit(result);
    assert.ok(localIds(result.data).includes("a1y"));
    assert.equal(result.payload.newRowId, "a1y");
    assert.equal(result.payload.toParentRowId, null);
    const a1 = findSourceRowInData(result.data, "a:a1");
    assert.deepEqual(localIds(a1.children), ["a1x"]);
});

test("TC-31 home plus right nests top-level under the level-2 row above", () => {
    const result = simulateRowReorder({
        data: treeDeepThreeLevels(),
        draggedId: "c",
        visibleIds: ["a", "a:a1", "b", "b:b1", "c"],
        hoverRowId: "c",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    const b1 = findSourceRowInData(result.data, "b:b1");
    assert.ok(localIds(b1.children).includes("c"));
    assert.equal(result.payload.newRowId, "b:b1:c");
    assert.equal(result.intent.hoverRowId, "b:b1");
});

test("TC-32 reorder siblings at deepest level", () => {
    const result = simulateRowReorder({
        data: treeDeepThreeLevels(),
        draggedId: "a:a1:a1x",
        visibleIds: ["a", "a:a1", "a:a1:a1x", "a:a1:a1y"],
        hoverRowId: "a:a1:a1y",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    const a1 = findSourceRowInData(result.data, "a:a1");
    assert.deepEqual(localIds(a1.children), ["a1y", "a1x"]);
    assert.equal(result.payload.sameParent ?? result.drop.sameParent, true);
});

test("TC-33 nest under last of three roots", () => {
    const result = simulateRowReorder({
        data: treeDeepThreeLevels(),
        draggedId: "a:a2",
        visibleIds: ["a", "a:a1", "a:a2", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.deepEqual(childIds(result.data, "c"), ["a2"]);
    assert.equal(result.payload.newRowId, "c:a2");
});

// --- Expanded / collapsed branches ---

test("TC-34 drag expanded branch after next root keeps children on the node", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "p",
        visibleIds: ["p", "p:pc1", "p:pc2", "q", "q:qc1", "r"],
        hoverRowId: "q",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["q", "p", "r"]);
    assert.deepEqual(childIds(result.data, "p"), ["pc1", "pc2"]);
    assert.deepEqual(result.draggedIds, ["p"]);
    const byId = previewById(result.preview);
    assert.ok(byId.p.isDragged);
    assert.ok(byId["p:pc1"].isDragged);
    assert.ok(byId["p:pc2"].isDragged);
    assert.equal(byId.p.y < byId["p:pc1"].y, true);
    assert.equal(byId["p:pc1"].y < byId["p:pc2"].y, true);
});

test("TC-35 drag expanded branch under another root remaps descendant ids", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "p",
        visibleIds: ["p", "p:pc1", "p:pc2", "q", "q:qc1", "r"],
        hoverRowId: "q",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["q", "r"]);
    const nested = findSourceRowInData(result.data, "q:p");
    assert.ok(nested);
    assert.deepEqual(localIds(nested.children), ["pc1", "pc2"]);
    assert.equal(result.payload.newRowId, "q:p");
    assert.ok(result.remappedIds.includes("q:p"));
    assert.ok(result.remappedIds.includes("q:p:pc1"));
    assert.ok(result.remappedIds.includes("q:p:pc2"));
    assert.equal(result.remappedIds.includes("p:pc1"), false);
});

test("TC-36 drag expanded branch before another expanded branch", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "q",
        visibleIds: ["p", "p:pc1", "p:pc2", "q", "q:qc1", "r"],
        hoverRowId: "p",
        hoverEdge: "swapUp"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["q", "p", "r"]);
    assert.deepEqual(childIds(result.data, "q"), ["qc1"]);
    assert.deepEqual(childIds(result.data, "p"), ["pc1", "pc2"]);
});

test("TC-37 collapsed parent still moves hidden children in data", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "p",
        visibleIds: ["p", "q", "r"],
        hoverRowId: "q",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["q", "p", "r"]);
    assert.deepEqual(childIds(result.data, "p"), ["pc1", "pc2"]);
});

test("TC-38 drag leaf out of expanded branch leaves siblings", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "p:pc1",
        visibleIds: ["p", "p:pc1", "p:pc2", "q", "r"],
        hoverRowId: "r",
        hoverEdge: "swapDown",
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    });
    assertCommit(result);
    assert.deepEqual(childIds(result.data, "p"), ["pc2"]);
    assert.deepEqual(localIds(result.data), ["p", "q", "r", "pc1"]);
    assert.equal(result.payload.newRowId, "pc1");
});

test("TC-39 cannot nest expanded parent into its visible child", () => {
    const data = treeExpandedBranchPair();
    const ctx = resolveReorderContext(data, "p");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx: ctx,
        hoverRowId: "p:pc1",
        position: ROW_REORDER_POSITIONS.INSIDE,
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    }), null);
});

test("TC-40 collectDraggedRowIds is parent only; preview marks descendants", () => {
    const data = treeExpandedBranchPair();
    const ctx = resolveReorderContext(data, "p");
    assert.deepEqual(collectDraggedRowIds(ctx), ["p"]);
    assert.equal(isDraggedPreviewRowId("p:pc1", ["p"]), true);
    assert.equal(isDraggedPreviewRowId("p:pc2", ["p"]), true);
    assert.equal(isDraggedPreviewRowId("q", ["p"]), false);
});

test("TC-41 expanded home band is parent through last visible child", () => {
    const hits = hitsFromVisible(["p", "p:pc1", "p:pc2", "q"], ["p"]);
    const onChild = resolveVerticalIntent({
        hits,
        clientY: hitY(hits, "p:pc2", "mid"),
        draggedIds: ["p"]
    });
    assert.equal(onChild.home, true);
    const intoQ = resolveVerticalIntent({
        hits,
        clientY: hitY(hits, "q", "swapDown"),
        draggedIds: ["p"]
    });
    assert.equal(intoQ.position, ROW_REORDER_POSITIONS.AFTER);
    assert.equal(intoQ.hoverRowId, "q");
});

test("TC-42 expanded branch home plus right nests under the visible row above", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "q",
        visibleIds: ["p", "p:pc1", "p:pc2", "q", "q:qc1", "r"],
        hoverRowId: "q",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.equal(result.intent.hoverRowId, "p:pc2");
    const nested = findSourceRowInData(result.data, "p:pc2:q");
    assert.ok(nested);
    assert.deepEqual(localIds(nested.children), ["qc1"]);
    assert.equal(result.payload.newRowId, "p:pc2:q");
});

test("TC-43 drag one expanded branch after another keeps both subtrees", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "p",
        visibleIds: ["p", "p:pc1", "p:pc2", "q", "q:qc1", "r"],
        hoverRowId: "q",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.deepEqual(childIds(result.data, "q"), ["qc1"]);
    assert.deepEqual(childIds(result.data, "p"), ["pc1", "pc2"]);
    assert.deepEqual(localIds(result.data), ["q", "p", "r"]);
});

test("TC-44 nest expanded mid-level branch under another mid-level node", () => {
    const result = simulateRowReorder({
        data: treeDeepThreeLevels(),
        draggedId: "a:a1",
        visibleIds: ["a", "a:a1", "a:a1:a1x", "a:a1:a1y", "a:a2", "b", "b:b1"],
        hoverRowId: "b:b1",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.equal(result.payload.newRowId, "b:b1:a1");
    const moved = findSourceRowInData(result.data, "b:b1:a1");
    assert.deepEqual(localIds(moved.children), ["a1x", "a1y"]);
    const a = findSourceRowInData(result.data, "a");
    assert.deepEqual(localIds(a.children), ["a2"]);
    assert.ok(result.remappedIds.includes("b:b1:a1:a1x"));
});

// --- Merge ---

test("TC-45 merge head moves the whole block among siblings", () => {
    const result = simulateRowReorder({
        data: mergeHeadTailPlusPlain(),
        draggedId: "h",
        visibleIds: ["a", "h", "t", "z"],
        hoverRowId: "z",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.deepEqual(localIds(result.data), ["a", "z", "h", "t"]);
    assert.equal(result.payload.blockSize, 2);
});

test("TC-46 merge tail cannot start a drag", () => {
    const result = simulateRowReorder({
        data: mergeHeadTailPlusPlain(),
        draggedId: "t",
        visibleIds: ["a", "h", "t", "z"],
        hoverRowId: "z",
        hoverEdge: "swapDown"
    });
    assert.equal(result.kind, "blocked");
});

test("TC-47 merge block cannot nest inside another row", () => {
    const data = mergeHeadTailPlusPlain();
    const ctx = resolveReorderContext(data, "h");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx: ctx,
        hoverRowId: "z",
        position: ROW_REORDER_POSITIONS.INSIDE,
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    }), null);
});

test("TC-48 merge block cannot reparent under a tree parent", () => {
    const data = [
        { id: "h", mergeGroupId: "g1", mergeGroupIndex: 0, mergeGroupSize: 2 },
        { id: "t", mergeGroupId: "g1", mergeGroupIndex: 1, mergeGroupSize: 2 },
        { id: "p", children: [{ id: "c" }] }
    ];
    const ctx = resolveReorderContext(data, "h");
    assert.equal(resolveDropTarget({
        sourceRows: data,
        dragCtx: ctx,
        hoverRowId: "p:c",
        position: ROW_REORDER_POSITIONS.BEFORE,
        allowTree: ROW_REORDER_TREE_MODES.REPARENT
    }), null);
});

// --- Payload / undo / preview contract ---

test("TC-49 remapPathIdSet rewrites the whole moved subtree", () => {
    const ids = new Set(["p", "p:pc1", "p:pc2", "q"]);
    remapPathIdSet(ids, "p", "q:p");
    assert.deepEqual([...ids].sort(), ["q", "q:p", "q:p:pc1", "q:p:pc2"]);
});

test("TC-50 restoreCrossParentOrders undoes a reparent", () => {
    const data = treeTwoRootsOneChild();
    const fromBefore = collectLocalRowIds(data[0].children);
    const toBefore = collectLocalRowIds(data[1].children);
    const result = simulateRowReorder({
        data,
        draggedId: "a:a1",
        visibleIds: ["a", "a:a1", "b", "b:b1"],
        hoverRowId: "b:b1",
        hoverEdge: "swapUp"
    });
    assertCommit(result);
    restoreCrossParentOrders(
        result.data[0].children,
        result.data[1].children,
        fromBefore,
        toBefore
    );
    assert.deepEqual(childIds(result.data, "a"), ["a1"]);
    assert.deepEqual(childIds(result.data, "b"), ["b1"]);
});

test("TC-51 payload after nest has dest rows copies for backend", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "c",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.equal(result.payload.section, "body");
    assert.equal(result.payload.position, ROW_REORDER_POSITIONS.INSIDE);
    assert.equal(result.payload.targetRowId, "b");
    assert.equal(result.payload.parentRowId, "b");
    assert.ok(Array.isArray(result.payload.rows));
    assert.equal(result.payload.rows[0].id, "c");
    assert.ok(result.payload.orderedLocalRowIds.includes("c"));
});

test("TC-52 isSelfOrDescendantId treats path prefixes only", () => {
    assert.equal(isSelfOrDescendantId("p", "p"), true);
    assert.equal(isSelfOrDescendantId("p", "p:c"), true);
    assert.equal(isSelfOrDescendantId("p", "px"), false);
    assert.equal(isSelfOrDescendantId("p:c", "p"), false);
});

test("TC-53 preview nest bumps indent by one level", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "c",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    const byId = previewById(result.preview);
    assert.equal(byId.c.indentDelta, 20);
    assert.equal(byId.c.isDragged, true);
});

test("TC-54 preview home plus nest still plans when only indent changes", () => {
    const result = simulateRowReorder({
        data: flatAbc(),
        draggedId: "c",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "c",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.ok(result.preview);
    const byId = previewById(result.preview);
    assert.equal(byId.c.indentDelta, 20);
});

test("TC-55 preview same-parent swap moves the dragged block as a unit", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "p",
        visibleIds: ["p", "p:pc1", "p:pc2", "q", "r"],
        hoverRowId: "q",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    const byId = previewById(result.preview);
    assert.equal(byId.q.y, 0);
    assert.equal(byId.p.y, 28);
    assert.equal(byId["p:pc1"].y, 56);
    assert.equal(byId["p:pc2"].y, 84);
    assert.equal(byId.r.y, 112);
});

test("TC-56 gantt persist contract: sibling reorder has same parent and ordered ids", () => {
    const result = simulateRowReorder({
        data: treeParentWithTwoChildren(),
        draggedId: "p:c2",
        visibleIds: ["p", "p:c1", "p:c2"],
        hoverRowId: "p:c1",
        hoverEdge: "swapUp"
    });
    assertCommit(result);
    const { payload } = result;
    assert.equal(payload.fromParentRowId, payload.toParentRowId);
    assert.ok(payload.orderedLocalRowIds.includes("c2"));
    assert.equal(payload.blockSize, 1);
    assert.equal(String(payload.rowId).split(":").pop(), "c2");
});

test("TC-57 gantt persist contract: reparent sends from and to sibling orders", () => {
    const result = simulateRowReorder({
        data: treeTwoRootsOneChild(),
        draggedId: "a:a1",
        visibleIds: ["a", "a:a1", "b", "b:b1"],
        hoverRowId: "b:b1",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.notEqual(result.payload.fromParentRowId, result.payload.toParentRowId);
    assert.deepEqual(result.payload.orderedLocalRowIds, ["b1", "a1"]);
    assert.deepEqual(result.payload.fromOrderedLocalRowIds, []);
    assert.equal(String(result.payload.toParentRowId).split(":").pop(), "b");
});

test("TC-58 reorder middle of three children", () => {
    const data = [{ id: "p", children: [{ id: "c1" }, { id: "c2" }, { id: "c3" }] }];
    const result = simulateRowReorder({
        data,
        draggedId: "p:c2",
        visibleIds: ["p", "p:c1", "p:c2", "p:c3"],
        hoverRowId: "p:c3",
        hoverEdge: "swapDown"
    });
    assertCommit(result);
    assert.deepEqual(childIds(result.data, "p"), ["c1", "c3", "c2"]);
});

test("TC-59 flattenVisible respects collapsed vs expanded", () => {
    const data = treeExpandedBranchPair();
    const collapsed = flattenVisible(data, expandedSet());
    assert.deepEqual(collapsed.map((item) => item.id), ["p", "q", "r"]);
    const open = flattenVisible(data, expandedSet("p", "q"));
    assert.deepEqual(open.map((item) => item.id), ["p", "p:pc1", "p:pc2", "q", "q:qc1", "r"]);
});

test("TC-61 collapsed previous root plus right nests the next root under it", () => {
    const result = simulateRowReorder({
        data: treeExpandedBranchPair(),
        draggedId: "q",
        visibleIds: ["p", "q", "q:qc1", "r"],
        hoverRowId: "q",
        hoverEdge: "mid",
        shiftX: NEST_SHIFT_PX
    });
    assertCommit(result);
    assert.equal(result.intent.hoverRowId, "p");
    const nested = findSourceRowInData(result.data, "p:q");
    assert.deepEqual(localIds(nested.children), ["qc1"]);
    assert.equal(result.payload.newRowId, "p:q");
});

test("TC-60 clone fixture is isolated per simulate", () => {
    const fixture = flatAbc();
    simulateRowReorder({
        data: fixture,
        draggedId: "a",
        visibleIds: ["a", "b", "c"],
        hoverRowId: "b",
        hoverEdge: "swapDown"
    });
    assert.deepEqual(localIds(fixture), ["a", "b", "c"]);
    assert.deepEqual(localIds(clone(fixture)), ["a", "b", "c"]);
});
