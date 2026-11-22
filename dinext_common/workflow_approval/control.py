"""Pure aggregates for the approvals control zone."""

from __future__ import annotations

from datetime import datetime

MANUAL_SOURCES = frozenset({"Manual", "Bulk", "Signed Link"})
AUTOMATIC_SOURCE = "Automatic Unchanged"


def hours_between(end, start) -> float:
	end_at = _as_datetime(end)
	start_at = _as_datetime(start)
	if end_at is None or start_at is None:
		return 0.0
	return max(0.0, (end_at - start_at).total_seconds() / 3600)


def longest_open_round_days(age_hours) -> float:
	values = [float(value) for value in age_hours]
	if not values:
		return 0.0
	return round(max(values) / 24, 1)


def aggregate_load(tasks, names: dict[str, str], now) -> list[dict]:
	grouped: dict[str, dict] = {}
	for task in tasks:
		approver = task.get("approver") or task.get("user") or ""
		if not approver:
			continue
		bucket = grouped.setdefault(
			approver,
			{"rounds": set(), "ages": [], "oldest": "", "oldest_age": -1.0},
		)
		round_id = task.get("approval_round_id") or ""
		if round_id:
			bucket["rounds"].add(round_id)
		age = hours_between(now, task.get("creation"))
		bucket["ages"].append(age)
		if age >= bucket["oldest_age"]:
			bucket["oldest_age"] = age
			bucket["oldest"] = task.get("source_title") or task.get("reference_name") or ""
	rows = []
	for approver, bucket in grouped.items():
		ages = bucket["ages"]
		rows.append(
			{
				"approver": approver,
				"approver_name": names.get(approver) or approver,
				"open_tasks": len(ages),
				"open_rounds": len(bucket["rounds"]),
				"avg_age_hours": round(sum(ages) / len(ages), 1) if ages else 0.0,
				"max_age_hours": round(max(ages), 1) if ages else 0.0,
				"oldest_document": bucket["oldest"],
			}
		)
	rows.sort(key=lambda row: (-row["max_age_hours"], row["approver_name"]))
	return rows


def aggregate_duration(tasks, group_by: str, names: dict[str, str]) -> list[dict]:
	grouped: dict[str, dict] = {}
	for task in tasks:
		if task.get("status") != "Completed":
			continue
		label = _group_label(task, group_by, names)
		if not label:
			continue
		bucket = grouped.setdefault(label, {"manual": [], "automatic": 0})
		source = task.get("completion_source") or ""
		if source == AUTOMATIC_SOURCE:
			bucket["automatic"] += 1
			continue
		if source not in MANUAL_SOURCES:
			continue
		bucket["manual"].append(hours_between(task.get("completed_at"), task.get("creation")))
	rows = []
	for label, bucket in grouped.items():
		manual = bucket["manual"]
		rows.append(
			{
				"group_label": label,
				"manual_count": len(manual),
				"automatic_count": bucket["automatic"],
				"avg_hours": round(sum(manual) / len(manual), 1) if manual else 0.0,
				"max_hours": round(max(manual), 1) if manual else 0.0,
			}
		)
	rows.sort(key=lambda row: (-row["max_hours"], row["group_label"]))
	return rows


def manual_total(rows) -> int:
	return sum(int(row["manual_count"]) for row in rows)


def aggregate_open_groups(rounds, group_by: str, names: dict[str, str]) -> list[dict]:
	counts: dict[str, int] = {}
	for row in rounds:
		for label in _open_group_labels(row, group_by, names):
			counts[label] = counts.get(label, 0) + 1
	return [
		{"group_label": label, "open_rounds": count}
		for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
	]


def load_chart(rows, view: str) -> dict:
	labels = [row["approver_name"] for row in rows]
	if view == "Open age":
		datasets = [
			{"name": "Average", "values": [row["avg_age_hours"] for row in rows]},
			{"name": "Maximum", "values": [row["max_age_hours"] for row in rows]},
		]
	else:
		datasets = [{"name": "Open tasks", "values": [row["open_tasks"] for row in rows]}]
	return _bar_chart(labels, datasets)


def duration_chart(rows, view: str) -> dict:
	if view == "Open rounds":
		labels = [row["group_label"] for row in rows]
		datasets = [{"name": "Open rounds", "values": [row["open_rounds"] for row in rows]}]
		return _bar_chart(labels, datasets)
	manual_rows = [row for row in rows if row["manual_count"]]
	labels = [row["group_label"] for row in manual_rows]
	datasets = [
		{"name": "Average", "values": [row["avg_hours"] for row in manual_rows]},
		{"name": "Maximum", "values": [row["max_hours"] for row in manual_rows]},
	]
	return _bar_chart(labels, datasets)


def _group_label(task, group_by: str, names: dict[str, str]) -> str:
	if group_by == "Approver":
		approver = task.get("approver") or task.get("user") or ""
		return names.get(approver) or approver
	if group_by == "Workflow":
		return task.get("workflow") or ""
	return task.get("reference_doctype") or ""


def _open_group_labels(row, group_by: str, names: dict[str, str]) -> list[str]:
	if group_by == "Approver":
		pending = row.get("pending_approvers") or ""
		labels = []
		for approver in pending.split(","):
			approver = approver.strip()
			if approver:
				labels.append(names.get(approver) or approver)
		return labels
	if group_by == "Workflow":
		label = row.get("workflow") or ""
		return [label] if label else []
	label = row.get("reference_doctype") or ""
	return [label] if label else []


def _bar_chart(labels: list[str], datasets: list[dict]) -> dict:
	return {"data": {"labels": labels, "datasets": datasets}, "type": "bar"}


def _as_datetime(value):
	if isinstance(value, datetime):
		return value
	if value is None or value == "":
		return None
	text = str(value).strip()
	for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
		try:
			return datetime.strptime(text, fmt)
		except ValueError:
			continue
	return None
