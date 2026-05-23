from __future__ import annotations

import json
from pathlib import Path

from .constants import EMPTY_FIXTURE_WARNING, FIXTURE_FILE_MISSING_WARNING


def load_fixture_docs(entry: dict) -> tuple[list[dict], list[str]]:
	path = Path(entry["fixture_path"])
	warnings: list[str] = []

	if not path.exists():
		return [], [FIXTURE_FILE_MISSING_WARNING]

	content = json.loads(path.read_text(encoding="utf-8") or "[]")
	if isinstance(content, dict):
		docs = [content]
	else:
		docs = list(content or [])

	if not docs:
		warnings.append(EMPTY_FIXTURE_WARNING)

	return docs, warnings
