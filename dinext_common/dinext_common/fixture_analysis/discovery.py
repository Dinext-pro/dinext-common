from __future__ import annotations

import importlib
import json
from pathlib import Path

import frappe

from .constants import HOOKS_FIXTURES_MISSING_WARNING

UNSUPPORTED_FIXTURE_DECLARATION_WARNING = "unsupported_fixture_declaration"


def discover_fixture_catalog(site: str | None = None) -> list[dict]:
	del site
	app_catalog: list[dict] = []
	for app in frappe.get_installed_apps():
		app_info = discover_app_fixtures(app)
		if app_info["entries"] or app_info["warnings"]:
			app_catalog.append(app_info)
	return app_catalog


def discover_app_fixtures(app: str) -> dict:
	app_path = Path(frappe.get_app_path(app))
	fixtures_dir = app_path / "fixtures"
	hooks_module = importlib.import_module(f"{app}.hooks")
	declared_fixtures = getattr(hooks_module, "fixtures", None)
	app_warnings: list[str] = []
	entries: dict[str, dict] = {}

	if declared_fixtures:
		for fixture in declared_fixtures:
			entry = normalize_fixture_entry(app, app_path, fixture)
			if not entry:
				app_warnings.append(UNSUPPORTED_FIXTURE_DECLARATION_WARNING)
				continue
			entries[entry["doctype"]] = entry
	else:
		if fixtures_dir.exists():
			app_warnings.append(HOOKS_FIXTURES_MISSING_WARNING)

	for file_entry in discover_fixture_files(app, fixtures_dir):
		entries.setdefault(file_entry["doctype"], file_entry)

	return {
		"app": app,
		"app_path": str(app_path),
		"warnings": app_warnings,
		"entries": sorted(entries.values(), key=lambda entry: entry["doctype"]),
	}


def normalize_fixture_entry(app: str, app_path: Path, fixture) -> dict | None:
	if isinstance(fixture, str):
		doctype = fixture
		filters = []
	elif isinstance(fixture, dict):
		doctype = fixture.get("doctype") or fixture.get("dt")
		if not doctype:
			return None
		filters = fixture.get("filters") or []
	else:
		return None

	return {
		"app": app,
		"doctype": doctype,
		"filters": filters,
		"fixture_path": str(app_path / "fixtures" / f"{frappe.scrub(doctype)}.json"),
		"source": "hooks",
	}


def discover_fixture_files(app: str, fixtures_dir: Path) -> list[dict]:
	if not fixtures_dir.exists():
		return []

	entries = []
	for path in sorted(fixtures_dir.glob("*.json")):
		try:
			content = json.loads(path.read_text(encoding="utf-8") or "[]")
		except json.JSONDecodeError:
			continue

		docs = [content] if isinstance(content, dict) else list(content or [])
		doctype = next((doc.get("doctype") for doc in docs if isinstance(doc, dict) and doc.get("doctype")), None)
		if not doctype:
			doctype = path.stem.replace("_", " ").title()

		entries.append(
			{
				"app": app,
				"doctype": doctype,
				"filters": [],
				"fixture_path": str(path),
				"source": "file_scan",
			}
		)
	return entries
