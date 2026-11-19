import frappe
from frappe.desk.form.load import getdoc
from frappe.desk.query_report import get_report_doc


@frappe.whitelist()
def get_report_document(doctype: str, name: str | int):
	if doctype != "Report" or name not in {"Approval Monitoring", "My Approvals"}:
		return getdoc(doctype, name)
	try:
		report = frappe.get_doc("Report", name)
	except frappe.DoesNotExistError:
		return getdoc(doctype, name)
	if (
		report.has_permission("read")
		or report.is_standard != "Yes"
		or report.module != "Dinext Common"
		or report.ref_doctype != "Workflow Task"
		or report.report_type != "Script Report"
	):
		return getdoc(doctype, name)

	# Desk loads metadata before running a report, even for users with report-only access.
	report = get_report_doc(name)
	metadata = {
		field: report.get(field)
		for field in ("doctype", "name", "is_standard", "ref_doctype", "report_name", "report_type")
	}
	if frappe.response.docs is None:
		frappe.response.docs = []
	frappe.response.docs.append(metadata)
