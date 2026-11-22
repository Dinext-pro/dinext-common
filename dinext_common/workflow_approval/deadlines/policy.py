"""Deadline arithmetic independent of database and request state."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def positive_amount(amount, *, integer=False):
	try:
		number = float(amount)
	except (TypeError, ValueError):
		raise ValueError("Deadline interval must be positive") from None
	if not math.isfinite(number) or number <= 0 or (integer and not number.is_integer()):
		raise ValueError(
			"Deadline interval must be a positive whole number"
			if integer
			else "Deadline interval must be positive"
		)
	return int(number) if integer else number


def local_datetime(value: datetime, zone: str) -> datetime:
	return value.replace(tzinfo=ZoneInfo(zone)) if value.tzinfo is None else value.astimezone(ZoneInfo(zone))


def resolve_local(value: datetime) -> datetime:
	"""Preserve wall time, resolving a nonexistent DST time forward."""
	candidate = value.astimezone(timezone.utc)
	restored = candidate.astimezone(value.tzinfo)
	if restored.replace(tzinfo=None) < value.replace(tzinfo=None):
		candidate += value.replace(tzinfo=None) - restored.replace(tzinfo=None)
	return candidate


def calculate_due(
	*,
	start: datetime,
	amount,
	unit: str,
	timezone_name: str,
	approver: str = "",
	doctype: str = "",
	reference_name: str = "",
	extensions=None,
) -> datetime:
	local = local_datetime(start, timezone_name)
	if unit == "Hours":
		return local.astimezone(timezone.utc) + timedelta(hours=positive_amount(amount))
	if unit == "Days":
		return resolve_local(local + timedelta(days=positive_amount(amount, integer=True)))
	handler = (extensions or {}).get("deadline_intervals", {}).get(unit)
	if not handler or not callable(handler.get("calculate")):
		raise ValueError("Unknown deadline interval: " + str(unit))
	context = dict(
		start=local,
		amount=positive_amount(amount, integer=handler.get("integer", False)),
		timezone_name=timezone_name,
		approver=approver,
		doctype=doctype,
		reference_name=reference_name,
	)
	if validate := handler.get("validate"):
		validate(context)
	due = handler["calculate"](context)
	if not isinstance(due, datetime) or due.tzinfo is None:
		raise ValueError("Deadline extension must return a timezone-aware datetime")
	return due.astimezone(timezone.utc)


def choose_deadline(transitions, **context):
	candidates = [
		dict(row, due=calculate_due(amount=row["amount"], unit=row["unit"], **context)) for row in transitions
	]
	return min(candidates, key=lambda row: (row["due"], int(row.get("idx") or 0), row["uuid"]), default=None)
