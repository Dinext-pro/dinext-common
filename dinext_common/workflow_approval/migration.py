"""Lossless inventory and cutover guards for legacy approval artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frappe

_SHARED_LEGACY_RECORDS = {'Client Script': ('Workflow_Task_Route',),
 'Legacy API': ('Workflow_Task_Processing',
                'Workflow_Task_Processing_After_Save',
                'Get_my_working_WT',
                'Get_my_completed_WT'),
 'Server Script': ('Workflow Task Processing After Save V2',
                   'Get my approved WT',
                   'Workflow Task Processing',
                   'Get my working WT V2')}

CUTOVER_STATE_VERSION = 1
CUTOVER_PHASES = (
	"preflight",
	"drain_queues",
	"migrate_settings",
	"disable_retained_consumers",
	"delete_records",
	"smoke",
	"enable_engine",
)

REQUIRED_SCHEMA_FIELDS = {
	"Workflow Task": (
		"reference_doctype",
		"reference_name",
		"approval_round_id",
		"round_manifest",
		"approver",
		"round_status",
		"finalization_status",
	),
	"Available Workflow Transitions": (
		"transition_uuid",
		"transition_semantic_hash",
		"eligible_approvers",
		"send_email_to_creator",
	),
	"Workflow Transition": (
		"custom_transition_uuid",
		"custom_parallel_approval_policy",
		"custom_comment_is_required",
	),
	"Workflow": (
		"custom_approval_monitor_roles",
		"custom_group_workflow_action_emails",
		"custom_group_interval_unit",
	),
	"Workflow Action": (
		"custom_workflow_task",
		"custom_approval_round_id",
		"custom_delivery_key",
	),
}

SYSTEM_RECORD_NOISE_FIELDS = {
	"creation",
	"docstatus",
	"idx",
	"modified",
	"modified_by",
	"owner",
}


class CutoverBlockedError(RuntimeError):
	"""Raised when preflight cannot prove a lossless cutover."""


def system_record_hash(record: Mapping[str, Any]) -> str:
	"""Hash behavior-bearing system record content without runtime noise."""
	payload = {
		key: value
		for key, value in record.items()
		if key not in SYSTEM_RECORD_NOISE_FIELDS
	}
	serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(serialized.encode()).hexdigest()


def _task_value(task: object, field: str) -> Any:
	if isinstance(task, dict):
		return task.get(field)
	return getattr(task, field, None)


def _source_key(task: object) -> tuple[str, str, str]:
	return (
		str(_task_value(task, "reference_doctype") or _task_value(task, "doc") or ""),
		str(_task_value(task, "reference_name") or _task_value(task, "wt_docname") or ""),
		str(_task_value(task, "workflow_state") or _task_value(task, "state") or ""),
	)


def detect_ambiguous_open_rounds(tasks: Iterable[object]) -> list[dict[str, Any]]:
	"""Return open legacy cohorts that cannot map to one deterministic round."""
	groups: dict[tuple[str, str, str], list[object]] = defaultdict(list)
	for task in tasks:
		if _task_value(task, "status") == "Working":
			groups[_source_key(task)].append(task)

	ambiguous = []
	for source, rows in groups.items():
		approvers = [
			str(_task_value(row, "approver") or _task_value(row, "user") or "")
			for row in rows
		]
		round_ids = {
			str(_task_value(row, "approval_round_id"))
			for row in rows
			if _task_value(row, "approval_round_id")
		}
		has_blank_round = any(not _task_value(row, "approval_round_id") for row in rows)
		reasons = []
		if any(not approver for approver in approvers):
			reasons.append("missing approver")
		if len(approvers) != len(set(approvers)):
			reasons.append("duplicate approver")
		if len(round_ids) > 1 or (round_ids and has_blank_round):
			reasons.append("mixed round identity")
		if reasons:
			ambiguous.append(
				{
					"reference_doctype": source[0],
					"reference_name": source[1],
					"state": source[2],
					"tasks": sorted(str(_task_value(row, "name") or "") for row in rows),
					"reasons": reasons,
				}
			)
	return ambiguous


def assert_cutover_ready(report: Mapping[str, Any]) -> None:
	"""Fail closed when a preflight report contains unresolved blockers."""
	blockers = {
		"ambiguous_open_rounds": report.get("ambiguous_open_rounds") or [],
		"unclassified": report.get("unclassified") or [],
		"missing_schema": report.get("missing_schema") or [],
		"repository_leftovers": report.get("repository_leftovers") or [],
		"legacy_consumers": report.get("legacy_consumers") or [],
	}
	active = {key: value for key, value in blockers.items() if value}
	if active:
		raise CutoverBlockedError(
			"Workflow approval cutover is blocked: "
			+ json.dumps(active, ensure_ascii=False, sort_keys=True, default=str)
		)


def _cutover_providers():
	return [
		frappe.get_attr(provider)()
		for provider in frappe.get_hooks("workflow_approval_cutover_providers")
	]


def cutover_records(decision):
	records = defaultdict(list)
	if decision == "remove":
		for doctype, names in _SHARED_LEGACY_RECORDS.items():
			records[doctype].extend(names)
	for provider in _cutover_providers():
		for doctype, names in provider.get(decision, {}).items():
			records[doctype].extend(names)
	return {doctype: tuple(dict.fromkeys(names)) for doctype, names in records.items()}


def _cutover_values(key):
	return tuple(dict.fromkeys(value for provider in _cutover_providers() for value in provider.get(key, ())))


def _run_cutover_extensions(phase):
	steps = [provider[phase] for provider in _cutover_providers() if phase in provider]
	for _, run in sorted(steps, key=lambda step: step[0]):
		run()


def _app_path(app: str) -> Path:
	return Path(frappe.get_app_path(app))


def collect_repository_leftovers(app_path=None) -> list[dict[str, str]]:
	"""Find classified artifacts that would be restored from fixtures or standard files."""
	resolver = app_path or _app_path
	leftovers: list[dict[str, str]] = []
	for app, relative, doctype in _cutover_values("fixture_files"):
		path = resolver(app) / relative
		if not path.exists():
			continue
		rows = json.loads(path.read_text())
		blocked = set(cutover_records("remove").get(doctype, ()))
		for row in rows:
			name = str(row.get("name") or "")
			if name in blocked:
				leftovers.append(
					{
						"app": app,
						"path": relative,
						"doctype": doctype,
						"name": name,
					}
				)
	for app, relative, name in _cutover_values("notification_files"):
		path = resolver(app) / relative
		if path.exists() and any(path.glob("*.json")):
			leftovers.append(
				{
					"app": app,
					"path": relative,
					"doctype": "Notification",
					"name": name,
				}
			)
	return leftovers


def lossless_matrix() -> list[dict[str, str]]:
	"""Return the classified replacement matrix used as the cutover contract."""
	return [
		{
			"doctype": doctype,
			"name": name,
			"decision": "remove",
			"replacement": "dinext_common.workflow_approval",
		}
		for doctype, names in cutover_records("remove").items()
		for name in names
	] + [
		{
			"doctype": doctype,
			"name": name,
			"decision": "retain",
			"replacement": "typed adapter + retained record",
		}
		for doctype, names in cutover_records("retain").items()
		for name in names
	]


def _live_records(doctype: str, names: tuple[str, ...]) -> list[dict[str, Any]]:
	if not frappe.db.table_exists(doctype):
		return []
	return frappe.get_all(
		doctype,
		filters={"name": ("in", names)},
		fields=["*"],
		order_by="name asc",
	)


def collect_live_preflight() -> dict[str, Any]:
	"""Collect live target records and open-round ambiguity for cutover."""
	records = {}
	for doctype, names in cutover_records("remove").items():
		if doctype == "Legacy API":
			continue
		rows = _live_records(doctype, names)
		records[doctype] = [
			{
				"name": row.name,
				"hash": system_record_hash(row),
				"record": dict(row),
			}
			for row in rows
		]

	task_fields = [
		"name",
		"status",
		"doc",
		"wt_docname",
		"state",
		"user",
		"reference_doctype",
		"reference_name",
		"workflow_state",
		"approver",
		"approval_round_id",
	]
	tasks = (
		frappe.get_all("Workflow Task", fields=task_fields)
		if frappe.db.table_exists("Workflow Task")
		else []
	)
	missing_schema = []
	for doctype, fields in REQUIRED_SCHEMA_FIELDS.items():
		if not frappe.db.exists("DocType", doctype):
			missing_schema.append({"doctype": doctype, "field": None})
			continue
		meta = frappe.get_meta(doctype)
		for field in fields:
			if not meta.has_field(field):
				missing_schema.append({"doctype": doctype, "field": field})
	blocking, retained = _split_consumers(collect_legacy_consumers())
	return {
		"records": records,
		"ambiguous_open_rounds": detect_ambiguous_open_rounds(tasks),
		"unclassified": [],
		"missing_schema": missing_schema,
		"repository_leftovers": collect_repository_leftovers(),
		"legacy_consumers": blocking,
		"disableable_consumers": retained,
	}


def summarize_live_preflight() -> dict[str, Any]:
	"""Return a compact operator-facing summary of the live preflight."""
	report = collect_live_preflight()
	return {
		"record_counts": {
			doctype: len(rows)
			for doctype, rows in report["records"].items()
		},
		"ambiguous_open_rounds": report["ambiguous_open_rounds"],
		"unclassified": report["unclassified"],
		"missing_schema": report["missing_schema"],
		"repository_leftovers": report.get("repository_leftovers") or [],
		"legacy_consumers": report.get("legacy_consumers") or [],
	}


def summarize_live_hashes() -> dict[str, dict[str, str]]:
	report = collect_live_preflight()
	hashes = {
		doctype: {row["name"]: row["hash"] for row in rows}
		for doctype, rows in report["records"].items()
	}
	for doctype, names, disabled in (
		("Client Script", _cutover_values("retained_client_scripts"), lambda row: not row.enabled),
		("Server Script", _cutover_values("retained_server_scripts"), lambda row: row.disabled),
	):
		hashes.setdefault(doctype, {}).update(
			{row.name: system_record_hash(row) for row in _live_records(doctype, names) if not disabled(row)}
		)
	return hashes


def _verify_reviewed_records() -> None:
	"""Require explicit behavioral evidence for records that are still to be changed."""
	reviewed = frappe.conf.get("parallel_workflow_cutover_reviewed_hashes") or {}
	drift = [
		f"{doctype}: {name}"
		for doctype, records in summarize_live_hashes().items()
		for name, digest in records.items()
		if reviewed.get(doctype, {}).get(name) != digest
	]
	if drift:
		raise CutoverBlockedError("Unreviewed Workflow cutover records: " + ", ".join(drift))


def collect_legacy_consumers() -> list[dict[str, str]]:
	"""Find runtime metadata that still invokes one of the five bare APIs."""
	targets = cutover_records("remove")["Legacy API"]
	search_fields = {
		"Server Script": ("api_method", "script", "disabled"),
		"Client Script": ("script", "enabled"),
		"Number Card": ("method", "filters_json"),
		"Custom HTML Block": ("html", "script"),
	}
	consumers = []
	for doctype, fields in search_fields.items():
		if not frappe.db.table_exists(doctype):
			continue
		meta = frappe.get_meta(doctype)
		available = [field for field in fields if meta.has_field(field)]
		if not available:
			continue
		for row in frappe.get_all(doctype, fields=["name", *available]):
			if row.name in cutover_records("remove").get(doctype, ()):
				continue
			if doctype == "Client Script" and not row.get("enabled"):
				continue
			if doctype == "Server Script" and row.get("disabled"):
				continue
			for field in available:
				value = str(row.get(field) or "")
				for target in targets:
					if target in value:
						consumers.append(
							{
								"doctype": doctype,
								"name": row.name,
								"field": field,
								"target": target,
							}
						)
	return consumers


def _split_consumers(consumers: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
	disableable = set(_cutover_values("retained_client_scripts"))
	retained = [row for row in consumers if row["name"] in disableable]
	blocking = [row for row in consumers if row["name"] not in disableable]
	return blocking, retained


def _cutover_state() -> dict[str, Any]:
	state = frappe.conf.get("parallel_workflow_cutover_state") or {}
	return {
		"version": state.get("version"),
		"completed": list(state.get("completed") or []),
		"receipt": state.get("receipt") or {},
	}


def _store_cutover_state(state: Mapping[str, Any]) -> None:
	from frappe.installer import update_site_config

	checkpoint = dict(state)
	update_site_config("parallel_workflow_cutover_state", checkpoint)
	frappe.local.conf.parallel_workflow_cutover_state = checkpoint


def _require_cutover_operator() -> None:
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		raise frappe.PermissionError("System Manager role is required")
	if not frappe.conf.get("maintenance_mode") or not frappe.conf.get("pause_scheduler"):
		raise CutoverBlockedError(
			"Maintenance mode and pause_scheduler are required for cutover"
		)


def assert_cutover_compatibility() -> None:
	from dinext_common.workflow_approval.permissions import supports_final_task_permission_queries

	if not supports_final_task_permission_queries():
		raise CutoverBlockedError("Update Dinext Platform before enabling parallel Workflow approval")
	installed = set(frappe.get_installed_apps())
	for app in _cutover_values("canonical_status_consumers"):
		if app in installed and 1 not in frappe.get_hooks("workflow_approval_canonical_statuses", app_name=app):
			raise CutoverBlockedError(f"Update {app} before enabling canonical approval statuses")


def _phase_preflight() -> dict[str, Any]:
	assert_cutover_compatibility()
	report = collect_live_preflight()
	blocking, retained = _split_consumers(report.get("legacy_consumers") or [])
	report["legacy_consumers"] = blocking
	report["disableable_consumers"] = retained
	assert_cutover_ready(report)
	_verify_reviewed_records()
	_run_cutover_extensions("preflight")
	return {
		"record_counts": {
			doctype: len(rows) for doctype, rows in report["records"].items()
		},
		"disableable_consumers": retained,
	}


def _phase_drain_queues() -> dict[str, Any]:
	from frappe.utils.background_jobs import get_jobs

	doctypes = set(frappe.get_all("Workflow", filters={"is_active": 1}, pluck="document_type"))
	doctypes.update(_cutover_values("queue_doctypes"))
	job_modules = ("dinext_common.workflow_approval.", *_cutover_values("queue_job_modules"))
	site = frappe.local.site
	has_workflow_job = any(
		(getattr(method, "__module__", "") + "." if callable(method) else str(method)).startswith(job_modules)
		for key in ("method", "job_type")
		for method in get_jobs(site=site, key=key).get(site, [])
	)
	queue_health = {
		"rq_jobs": int(has_workflow_job),
		"email_queue": frappe.db.count("Email Queue", {
			"status": ("in", ("Not Sent", "Sending", "Partially Sent")),
			"reference_doctype": ("in", sorted(doctypes | {"Workflow Action", "Workflow Task"})),
		}),
		"submission_queue": frappe.db.count("Submission Queue", {
			"status": "Queued", "ref_doctype": ("in", sorted(doctypes)),
		}),
		"finalizing_rounds": frappe.db.count("Workflow Task", {"round_status": "Finalizing"}),
	}
	if any(queue_health.values()):
		raise CutoverBlockedError("Resolve pending Workflow work before cutover: " + json.dumps(queue_health))
	return queue_health


def _phase_migrate_settings() -> dict[str, Any]:
	from dinext_common.workflow_approval.metadata import (
		ensure_workflow_approval_custom_fields,
		ensure_workflow_approval_desk_records,
		ensure_workflow_approval_email_templates,
	)

	ensure_workflow_approval_custom_fields()
	ensure_workflow_approval_email_templates()
	ensure_workflow_approval_desk_records()
	_run_cutover_extensions("migrate_settings")
	return {"configured": True}


def _phase_disable_retained_consumers() -> dict[str, Any]:
	_verify_reviewed_records()
	disabled: list[str] = []
	for name in _cutover_values("retained_client_scripts"):
		if frappe.db.exists("Client Script", name):
			frappe.db.set_value(
				"Client Script",
				name,
				"enabled",
				0,
				update_modified=False,
			)
			disabled.append(name)
	for name in _cutover_values("retained_server_scripts"):
		if frappe.db.exists("Server Script", name):
			frappe.db.set_value("Server Script", name, "disabled", 1, update_modified=False)
			disabled.append(name)
	if disabled:
		frappe.cache.delete_value("server_script_map")
	return {"disabled": disabled}


def _phase_delete_records() -> dict[str, int]:
	_verify_reviewed_records()
	deleted: dict[str, int] = {}
	for doctype, names in cutover_records("remove").items():
		if doctype == "Legacy API":
			continue
		deleted[doctype] = 0
		for name in names:
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(
					doctype,
					name,
					force=True,
					ignore_permissions=True,
					ignore_missing=True,
				)
				deleted[doctype] += 1
	return deleted


def _phase_enable_engine(backup_receipt: str, deleted: Mapping[str, int]) -> dict[str, Any]:
	from frappe.installer import update_site_config

	receipt = {
		"completed_at": datetime.now(timezone.utc).isoformat(),
		"backup": str(backup_receipt),
		"deleted": dict(deleted),
	}
	update_site_config("enable_parallel_workflow_approval", 1)
	update_site_config("parallel_workflow_cutover_receipt", receipt)
	frappe.local.conf.enable_parallel_workflow_approval = True
	return receipt


def _phase_smoke() -> dict[str, Any]:
	remaining = {
		doctype: [
			name
			for name in names
			if doctype != "Legacy API" and frappe.db.exists(doctype, name)
		]
		for doctype, names in cutover_records("remove").items()
	}
	remaining = {key: value for key, value in remaining.items() if value}
	consumers = collect_legacy_consumers()
	_run_cutover_extensions("smoke")
	if remaining or consumers:
		raise CutoverBlockedError(
			"Post-cutover smoke failed: "
			+ json.dumps(
				{"remaining": remaining, "consumers": consumers},
				ensure_ascii=False,
				sort_keys=True,
			)
		)
	return {"remaining": remaining, "consumers": consumers}


PHASE_HANDLERS = {
	"preflight": lambda receipt, state: _phase_preflight(),
	"drain_queues": lambda receipt, state: _phase_drain_queues(),
	"migrate_settings": lambda receipt, state: _phase_migrate_settings(),
	"disable_retained_consumers": lambda receipt, state: _phase_disable_retained_consumers(),
	"delete_records": lambda receipt, state: _phase_delete_records(),
	"enable_engine": lambda receipt, state: _phase_enable_engine(
		receipt,
		(state.get("receipt") or {}).get("delete_records") or {},
	),
	"smoke": lambda receipt, state: _phase_smoke(),
}


def cutover_complete() -> bool:
	state = _cutover_state()
	return (
		bool(frappe.conf.get("parallel_workflow_cutover_receipt"))
		and state["version"] == CUTOVER_STATE_VERSION
		and set(CUTOVER_PHASES).issubset(state["completed"])
	)


def execute_cutover(
	backup_receipt: str,
	*,
	inject_fault: str | None = None,
) -> dict[str, Any]:
	"""Run restartable cutover phases and enable the engine."""
	from frappe.utils.synchronization import filelock

	_require_cutover_operator()
	if not str(backup_receipt or "").strip():
		raise CutoverBlockedError("A database/files backup receipt is required")

	with filelock("parallel_workflow_cutover", timeout=0):
		return _resume_cutover(backup_receipt, inject_fault)


def _resume_cutover(backup_receipt: str, inject_fault: str | None) -> dict[str, Any]:
	state = _cutover_state()
	completed = set(state["completed"])
	receipt = dict(state.get("receipt") or {})
	if state.get("version") != CUTOVER_STATE_VERSION and completed:
		completed.clear()
		receipt = {"previous_checkpoint": receipt}
	receipt["backup"] = str(backup_receipt)

	def checkpoint():
		_store_cutover_state({"version": CUTOVER_STATE_VERSION, "completed": sorted(completed), "receipt": receipt})

	for phase in CUTOVER_PHASES:
		if phase in completed:
			continue
		if inject_fault == phase:
			checkpoint()
			raise CutoverBlockedError(f"Injected fault before phase {phase}")
		receipt[phase] = PHASE_HANDLERS[phase](backup_receipt, {"receipt": receipt})
		if phase in {"migrate_settings", "disable_retained_consumers", "delete_records"}:
			frappe.db.commit()
		completed.add(phase)
		checkpoint()

	frappe.db.commit()
	return receipt
