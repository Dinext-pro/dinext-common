# Copyright (c) 2026, Dinext
"""Syntax guard for client-only AG Grid tree-cell modules (no Frappe runtime hook)."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[2]
_PUBLIC_JS = _APP_ROOT / "public" / "js"

_TREE_CELL_JS = [
    _PUBLIC_JS / "ag-grid" / "tree-cell.js",
    _PUBLIC_JS / "presets" / "work-efforts-column-helpers.js",
]


class TestAgGridTreeCellSyntax(unittest.TestCase):
    """Load tree-cell.js via node --check only — behavior is manual/UI (see test-cases.md)."""

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("node not on PATH")

    def test_tree_cell_js_syntax(self):
        for path in _TREE_CELL_JS:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"missing: {path}")
                result = subprocess.run(
                    [self.node, "--check", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    msg=f"node --check failed for {path}:\n{result.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
