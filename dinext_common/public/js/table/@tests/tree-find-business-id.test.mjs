import test from "node:test";
import assert from "node:assert/strict";

import { findSourceRowByBusinessId } from "../core/tree/model.js";

test("findSourceRowByBusinessId walks nested children", () => {
	const tree = [
		{
			id: "P",
			exp_end_date: "2026-01-01",
			children: [
				{ id: "C1", exp_end_date: "2026-01-02", children: [] },
				{
					id: "C2",
					exp_end_date: "2026-01-03",
					children: [{ id: "G", exp_end_date: "2026-01-04" }],
				},
			],
		},
	];

	assert.equal(findSourceRowByBusinessId(tree, "G")?.exp_end_date, "2026-01-04");
	assert.equal(findSourceRowByBusinessId(tree, "P")?.id, "P");
	assert.equal(findSourceRowByBusinessId(tree, "missing"), null);
});
