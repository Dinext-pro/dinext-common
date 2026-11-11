"""Document lifecycle adapters for the parallel approval engine."""

from __future__ import annotations

from typing import Any

import frappe

SERVICE_DOCTYPES = {
	"Workflow Document Context",
	"Workflow Process",
	"Workflow Task",
	"Workflow Action",
	"ToDo",
	"Email Queue",
	"Submission Queue",
}


def is_engine_enabled() -> bool:
	"""Return the site-scoped rollout flag for the new engine."""
	return bool(frappe.conf.get("enable_parallel_workflow_approval", False))


def _should_handle(doc: Any) -> bool:
	doctype = getattr(doc, "doctype", None)
	if (
		not is_engine_enabled()
		or getattr(frappe.flags, "in_migrate", False)
		or getattr(frappe.flags, "in_install", False)
		or not doctype
		or doctype in SERVICE_DOCTYPES
		or getattr(frappe.flags, "in_dinext_workflow_finalization", False)
	):
		return False
	from dinext_common.workflow_approval.scenarios import service
	if service.is_ready():
		return service.supports_doctype(doctype)
	from frappe.model.workflow import get_workflow_name
	return bool(get_workflow_name(doctype))


def validate_source(doc: Any, method: str | None = None) -> None:
	"""Guard direct state changes when the feature is enabled."""
	if not _should_handle(doc):
		return
	from dinext_common.workflow_approval.engine import validate_source_change

	validate_source_change(doc)


def after_source_insert(doc: Any, method: str | None = None) -> None:
	"""Create the first round after a source document is inserted."""
	if not _should_handle(doc):
		return
	from dinext_common.workflow_approval.engine import reconcile_source

	reconcile_source(doc)


def on_source_update(doc: Any, method: str | None = None) -> None:
	"""Reconcile active approval state after a normal save."""
	if not _should_handle(doc):
		return
	from dinext_common.workflow_approval.engine import reconcile_source

	reconcile_source(doc)


def on_source_update_after_submit(doc: Any, method: str | None = None) -> None:
	"""Reconcile queued finalization after submitted-document updates."""
	if not _should_handle(doc):
		return
	from dinext_common.workflow_approval.engine import reconcile_source

	reconcile_source(doc)


def on_source_cancel(doc: Any, method: str | None = None) -> None:
	"""Reconcile a source cancellation."""
	if not _should_handle(doc):
		return
	from dinext_common.workflow_approval.engine import reconcile_source

	reconcile_source(doc)


def on_source_trash(doc: Any, method: str | None = None) -> None:
	"""Close saved approvals even after the engine or Workflow was disabled."""
	if not getattr(doc, "doctype", None) or doc.doctype in SERVICE_DOCTYPES:
		return
	from dinext_common.workflow_approval.engine import archive_source

	archive_source(doc)
