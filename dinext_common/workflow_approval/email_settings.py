"""Workflow email profiles, with explicit state overrides and legacy-time support."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time

PROFILE_FIELDS = (
	"custom_group_workflow_action_emails", "custom_attach_document_pdf",
	"custom_group_interval_unit", "custom_group_interval_value", "custom_group_send_times",
	"custom_group_email_template", "next_action_email_template",
)
SCHEDULE_FIELDS = PROFILE_FIELDS[:1] + PROFILE_FIELDS[2:5]
DEFAULT_TEMPLATE = "Dinext Workflow Action"


def value(row, key, default=None):
	return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def assign(row, key, item):
	if isinstance(row, dict):
		row[key] = item
	else:
		setattr(row, key, item)


def checked(item) -> bool:
	return item is True or str(item or "").strip() == "1"


def normalize_send_times(raw: str | None) -> str:
	if not raw or not str(raw).strip():
		return ""
	times = set()
	for item in str(raw).split(","):
		item = item.strip()
		if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item):
			raise ValueError("Digest times must be comma-separated HH:MM values")
		times.add(item)
	return ", ".join(sorted(times))


def _times(row) -> str:
	raw = value(row, "custom_group_send_times")
	if raw:
		return normalize_send_times(raw)
	legacy = str(value(row, "custom_group_send_time") or "")
	if legacy:
		parts = legacy.split(":")
		return normalize_send_times(f"{int(parts[0]):02d}:{int(parts[1]):02d}")
	return ""


def _profile_values(row, *, parent=False) -> dict:
	return {
		"custom_group_workflow_action_emails": int(checked(value(row, "custom_group_workflow_action_emails"))),
		"custom_attach_document_pdf": int(checked(value(row, "custom_attach_document_pdf"))),
		"custom_group_interval_unit": value(row, "custom_group_interval_unit") or "Days",
		"custom_group_interval_value": int(value(row, "custom_group_interval_value") or 0),
		"custom_group_send_times": _times(row),
		"custom_group_email_template": value(row, "custom_group_email_template") or "",
		"next_action_email_template": value(row, "custom_workflow_action_email_template" if parent else "next_action_email_template") or "",
	}


@dataclass(frozen=True)
class EmailProfile:
	enabled: bool
	mode: str
	template: str
	digest_template: str
	attach_pdf: bool
	interval_unit: str
	interval_value: int
	send_times: tuple[time, ...]
	anchor: object


def profile_for_state(workflow, state) -> EmailProfile:
	if isinstance(state, str):
		state = next((r for r in value(workflow, "states", []) if value(r, "state") == state), None)
	override = checked(value(state, "custom_email_settings_override"))
	row = state if override else workflow
	profile = _profile_values(row, parent=not override)
	grouped = bool(profile["custom_group_workflow_action_emails"])
	return EmailProfile(
		enabled=checked(value(workflow, "send_email_alert")) and checked(value(state, "send_email")),
		mode="Digest" if grouped else "Immediate",
		template=profile["next_action_email_template"] or value(workflow, "custom_workflow_action_email_template") or DEFAULT_TEMPLATE,
		digest_template=profile["custom_group_email_template"] or value(workflow, "custom_group_email_template") or "",
		attach_pdf=not grouped and bool(profile["custom_attach_document_pdf"]),
		interval_unit=profile["custom_group_interval_unit"],
		interval_value=profile["custom_group_interval_value"],
		send_times=tuple(time.fromisoformat(t.strip()) for t in profile["custom_group_send_times"].split(",") if t.strip()),
		anchor=value(row, "custom_group_schedule_anchor") or value(workflow, "custom_group_schedule_anchor") or value(workflow, "modified"),
	)


def _validate(profile: dict, *, enabled: bool):
	if not enabled or not profile["custom_group_workflow_action_emails"]:
		return
	if profile["custom_group_interval_unit"] not in {"Hours", "Days"}:
		raise ValueError("Digest interval unit must be Hours or Days")
	if profile["custom_group_interval_value"] <= 0:
		raise ValueError("Digest interval must be a positive integer")
	if profile["custom_group_interval_unit"] == "Days" and not profile["custom_group_send_times"]:
		raise ValueError("Digest send time is required for daily delivery")


def prepare_email_profiles(workflow, previous=None, *, now):
	"""Materialize inherited previews, detect edits, and re-anchor changed schedules.

	The hidden override flag also supports explicit API updates and reset. Client
	preview refreshes copy the full effective profile without setting that flag.
	"""
	parent = _profile_values(workflow, parent=True)
	_validate(parent, enabled=checked(value(workflow, "send_email_alert")))
	for key, item in parent.items():
		assign(workflow, "custom_workflow_action_email_template" if key == "next_action_email_template" else key, item)
	old_parent = _profile_values(previous, parent=True) if previous else None
	if parent["custom_group_workflow_action_emails"] and checked(value(workflow, "send_email_alert")) and (
		not value(workflow, "custom_group_schedule_anchor") or
		(old_parent and any(parent[k] != old_parent[k] for k in SCHEDULE_FIELDS))
	):
		assign(workflow, "custom_group_schedule_anchor", now() if callable(now) else now)
	old_rows = {value(r, "state"): r for r in value(previous, "states", []) or []}
	for row in value(workflow, "states", []) or []:
		old = old_rows.get(value(row, "state"))
		own = checked(value(row, "custom_email_settings_override"))
		current = _profile_values(row)
		# Only a changed state profile (not a changed global profile) opts in.
		if not own and old and not checked(value(old, "custom_email_settings_override")):
			prior = _profile_values(old)
			if current != prior and current != parent:
				own = True
		assign(row, "custom_email_settings_override", int(own))
		if not own:
			for key, item in parent.items():
				assign(row, key, item)
			assign(row, "custom_group_schedule_anchor", value(workflow, "custom_group_schedule_anchor"))
		else:
			_validate(current, enabled=checked(value(workflow, "send_email_alert")) and checked(value(row, "send_email")))
			for key, item in current.items():
				assign(row, key, item)
			old_profile = _profile_values(old) if old else None
			if not value(row, "custom_group_schedule_anchor") or not old_profile or any(
				current[k] != old_profile[k] for k in SCHEDULE_FIELDS
			):
				assign(row, "custom_group_schedule_anchor", now() if callable(now) else now)
		assign(row, "custom_email_settings_source", "State settings" if own else "From Workflow")
