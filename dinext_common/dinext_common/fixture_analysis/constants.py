from __future__ import annotations

IGNORED_FIELDNAMES = {
	"_assign",
	"_comments",
	"_liked_by",
	"_seen",
	"_user_tags",
	"amended_from",
	"creation",
	"docstatus",
	"doctype",
	"idx",
	"lft",
	"modified",
	"modified_by",
	"name",
	"owner",
	"parent",
	"parentfield",
	"parenttype",
	"rgt",
}

TEXT_FIELD_CANDIDATES = {
	"Code",
	"Data",
	"Long Text",
	"Markdown Editor",
	"Small Text",
	"Text",
	"Text Editor",
}

EMPTY_FIXTURE_WARNING = "fixture_file_empty"
FILTERS_MISSING_WARNING = "fixture_filters_missing"
FIXTURE_FILE_MISSING_WARNING = "fixture_file_missing"
HOOKS_FIXTURES_MISSING_WARNING = "hooks_fixtures_missing"
INVALID_DOCTYPE_WARNING = "invalid_doctype"
