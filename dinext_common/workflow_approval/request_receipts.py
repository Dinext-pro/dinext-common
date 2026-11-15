"""Transaction-local persistence for replayable workflow requests."""

from __future__ import annotations

import hashlib
import json
from typing import NotRequired, TypedDict

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

DOCTYPE = "Workflow Request Receipt"
DEFAULT_RETENTION_DAYS = 7
RECEIPT_FIELDS = (
	"name", "initiator", "request_digest", "status", "targets", "item_results", "response", "job_id",
)


class ReceiptTarget(TypedDict):
	doctype: str
	name: str
	source_created_at: str
	task_name: str | None
	workflow: NotRequired[str]
	process_id: NotRequired[str | None]


def _digest(value: object) -> str:
	return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def request_key(operation: str, request_id: str) -> str:
	return _digest([operation, frappe.session.user, request_id])


def target(source, task_name: str | None = None) -> ReceiptTarget:
	return {
		"doctype": source.doctype,
		"name": source.name,
		"source_created_at": str(get_datetime(source.creation)),
		"task_name": task_name,
	}


def check_targets(targets: list[ReceiptTarget | None]) -> None:
	from dinext_common.workflow_approval.engine import WorkflowApprovalConflictError

	seen = set()
	for row in targets:
		if row is None:
			continue
		identity = (row["doctype"], row["name"], row["source_created_at"])
		if identity in seen:
			continue
		seen.add(identity)
		try:
			source = frappe.get_doc(row["doctype"], row["name"])
		except frappe.DoesNotExistError:
			raise WorkflowApprovalConflictError(_("The Workflow target no longer matches the selected document")) from None
		source.check_permission("read")
		if str(get_datetime(source.creation)) != row["source_created_at"]:
			raise WorkflowApprovalConflictError(_("The Workflow target no longer matches the selected document"))


def get(key: str, *, for_update: bool = False):
	return frappe.db.get_value(DOCTYPE, key, RECEIPT_FIELDS, as_dict=True, for_update=for_update)


def lock(key: str):
	from dinext_common.workflow_approval.engine import WorkflowApprovalConflictError

	receipt = get(key, for_update=True)
	if not receipt:
		raise WorkflowApprovalConflictError(_("The Workflow request has expired. Refresh the document before acting."))
	return receipt


def verify(receipt, parameters: object) -> None:
	from dinext_common.workflow_approval.engine import WorkflowApprovalConflictError

	if receipt.initiator != frappe.session.user:
		raise frappe.PermissionError
	if receipt.request_digest != _digest(parameters):
		raise WorkflowApprovalConflictError(_("This Workflow request was already used with different parameters"))


def reserve(
	operation: str,
	request_id: str,
	parameters: object,
	targets: list[ReceiptTarget | None],
	*,
	item_results: list | None = None,
	job_id: str | None = None,
):
	key = request_key(operation, request_id)
	doc = frappe.get_doc({
		"doctype": DOCTYPE,
		"name": key,
		"operation": operation,
		"initiator": frappe.session.user,
		"request_digest": _digest(parameters),
		"status": "Working",
		"targets": json.dumps(targets),
		"item_results": json.dumps(item_results) if item_results is not None else None,
		"job_id": job_id,
	})
	doc.db_insert(ignore_if_duplicate=True)
	receipt = get(key, for_update=True)
	verify(receipt, parameters)
	return receipt


def replay(receipt, parameters: object):
	verify(receipt, parameters)
	check_targets(json.loads(receipt.targets))
	return json.loads(receipt.response) if receipt.response is not None else None


def finish(key: str, response: object, *, failed: bool = False) -> None:
	values = {
		"status": "Failed" if failed else "Completed",
		"completed_at": now_datetime(),
		"response": json.dumps(response, ensure_ascii=False),
	}
	if not failed:
		values["item_results"] = None
	frappe.db.set_value(DOCTYPE, key, values)


def register_log_settings() -> None:
	settings = frappe.get_single("Log Settings")
	if any(row.ref_doctype == DOCTYPE for row in settings.logs_to_clear):
		return
	settings.register_doctype(DOCTYPE, DEFAULT_RETENTION_DAYS)
	settings.save(ignore_permissions=True)
