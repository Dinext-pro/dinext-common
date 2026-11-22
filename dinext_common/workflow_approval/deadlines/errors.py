"""Localized standard deadline diagnostics with preserved historical originals."""

from frappe import _


def display_deadline_error(error):
	"""Translate standard diagnostics without changing stored/custom audit text."""
	if not error:
		return error
	templates = (
		"Original assignment time is unknown",
		"Deadline policy snapshot is missing",
		"Deadline interval must be positive",
		"Deadline interval must be a positive whole number",
		"Deadline extension must return a timezone-aware datetime",
		"Worker calendar does not cover the deadline start",
		"Worker calendar does not cover the deadline",
		"Worker holiday calendar is missing",
		"Worker calendar does not cover the notification schedule",
		"Worker is missing for user {0}",
		"Unknown deadline interval: {0}",
		"Unknown deadline recipient type: {0}",
		"Unknown deadline sending interval: {0}",
		"Duplicate workflow deadline extension: {0}",
	)
	for template in templates:
		for language in ("en", "ru"):
			stored = _(template, lang=language)
			if "{0}" not in stored:
				if error == stored:
					return _(template)
				continue
			prefix, suffix = stored.split("{0}")
			if error.startswith(prefix) and (not suffix or error.endswith(suffix)):
				argument = error[len(prefix):len(error) - len(suffix) if suffix else None]
				return _(template).format(argument)
	return error
