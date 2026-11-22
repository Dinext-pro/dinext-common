"""Serve Workflow reports with the viewer's current access."""
import frappe
from frappe.core.doctype.file.file import File

from dinext_common.workflow_approval.permissions import WORKFLOW_SERVICE_DOCTYPES, WorkflowReadBlocked


def _is_workflow_report(report):
	seen = set()
	while report and report not in seen:
		seen.add(report)
		details = frappe.db.get_value("Report", report, ["ref_doctype", "reference_report"], as_dict=True)
		if not details:
			return False
		if details.ref_doctype in WORKFLOW_SERVICE_DOCTYPES:
			return True
		report = details.reference_report
	return False


class WorkflowReportAttachment(File):
	# File uses the standard database loader and can be constructed from a full row.
	supports_batched_source_reads = True

	def is_downloadable(self):
		return not _is_workflow_report_attachment(self) and super().is_downloadable()


def _is_workflow_report_attachment(doc):
	if doc.attached_to_doctype != "Prepared Report" or not doc.attached_to_name:
		return False
	report = frappe.db.get_value("Prepared Report", doc.attached_to_name, "report_name")
	return _is_workflow_report(report)


def _throw_stale_workflow_result():
	frappe.throw(
		frappe._("Run this Workflow report again to use your current access."), WorkflowReadBlocked,
	)


def _reject_prepared_workflow_result(report):
	if _is_workflow_report(report):
		_throw_stale_workflow_result()


def require_live_workflow_report(doc, method=None):
	if doc.ref_doctype in WORKFLOW_SERVICE_DOCTYPES or _is_workflow_report(doc.reference_report):
		doc.prepared_report = 0
		doc.disable_prepared_report_automation = 1


def stop_prepared_workflow_result(doc, method=None):
	_reject_prepared_workflow_result(doc.report_name)


def has_prepared_report_permission(doc, ptype="read", user=None, debug=False):
	if ptype in {"read", "select", "report", "export", "print", "email", "share"}:
		_reject_prepared_workflow_result(doc.report_name)


def has_report_attachment_permission(doc, ptype="read", user=None, debug=False):
	if _is_workflow_report_attachment(doc):
		_throw_stale_workflow_result()


def ensure_live_workflow_reports():
	for report in frappe.get_all(
		"Report", fields=["name", "ref_doctype", "reference_report", "prepared_report",
			"disable_prepared_report_automation"],
	):
		if report.disable_prepared_report_automation and not report.prepared_report:
			continue
		if report.ref_doctype in WORKFLOW_SERVICE_DOCTYPES or _is_workflow_report(report.reference_report):
			frappe.db.set_value(
				"Report", report.name, {"prepared_report": 0, "disable_prepared_report_automation": 1},
				update_modified=False,
			)
			frappe.clear_document_cache("Report", report.name)
