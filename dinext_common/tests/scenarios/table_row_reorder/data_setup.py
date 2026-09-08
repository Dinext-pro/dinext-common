"""In-memory trees for DinextTable row-reorder.

No Frappe DocTypes. Reset = clone fixture again in the JS runner.
Prefix is documentation-only so live-site helpers stay consistent
if a later UI smoke starts creating Task rows.
"""

from __future__ import annotations

NAME_PREFIX = "TEST RR"
SCENARIO_SLUG = "table_row_reorder"

# Owned: none. Dependencies: none.
# JS source of the same trees:
# dinext_common/public/js/table/@tests/helpers/row-reorder-fixtures.mjs


def flat_abc():
    return [{"id": "a"}, {"id": "b"}, {"id": "c"}]


def flat_abcd():
    return [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]


def tree_two_roots_one_child():
    return [
        {"id": "a", "children": [{"id": "a1"}]},
        {"id": "b", "children": [{"id": "b1"}]},
    ]


def tree_parent_with_two_children():
    return [
        {"id": "p", "children": [{"id": "c1"}, {"id": "c2"}]},
        {"id": "z"},
    ]


def tree_deep_three_levels():
    return [
        {
            "id": "a",
            "children": [
                {
                    "id": "a1",
                    "children": [{"id": "a1x"}, {"id": "a1y"}],
                },
                {"id": "a2"},
            ],
        },
        {
            "id": "b",
            "children": [{"id": "b1", "children": [{"id": "b1x"}]}],
        },
        {"id": "c"},
    ]


def tree_expanded_branch_pair():
    return [
        {"id": "p", "children": [{"id": "pc1"}, {"id": "pc2"}]},
        {"id": "q", "children": [{"id": "qc1"}]},
        {"id": "r"},
    ]


def tree_self_nest_guard():
    return [
        {
            "id": "p",
            "children": [{"id": "c", "children": [{"id": "g"}]}],
        }
    ]


def merge_head_tail_plus_plain():
    return [
        {"id": "a"},
        {
            "id": "h",
            "mergeGroupId": "g1",
            "mergeGroupIndex": 0,
            "mergeGroupSize": 2,
        },
        {
            "id": "t",
            "mergeGroupId": "g1",
            "mergeGroupIndex": 1,
            "mergeGroupSize": 2,
        },
        {"id": "z"},
    ]


OWNED_ENTITIES: list[str] = []
DEPENDENCIES: list[str] = []
RESET_SCOPE: list[str] = []


def setup() -> dict:
    """Idempotent. Returns fixture catalog. Does not touch the site."""
    return {
        "prefix": NAME_PREFIX,
        "owned_entities": list(OWNED_ENTITIES),
        "dependencies": list(DEPENDENCIES),
        "reset_scope": list(RESET_SCOPE),
        "fixtures": [
            "flat_abc",
            "flat_abcd",
            "tree_two_roots_one_child",
            "tree_parent_with_two_children",
            "tree_deep_three_levels",
            "tree_expanded_branch_pair",
            "tree_self_nest_guard",
            "merge_head_tail_plus_plain",
        ],
        "strategy": "reuse in-memory clone per test",
    }


def reset() -> dict:
    """No site documents to delete. JS tests clone fixtures per case."""
    return setup()
