"""Build workflow attachments from the recipient's document projection."""

from copy import copy

import frappe
from frappe import _
from frappe.utils import cint, scrub_urls
from frappe.www.printview import get_print_style, make_layout, standard_format

from dinext_common.workflow_approval.email_access import recipient_user, visible_document
from dinext_common.workflow_approval.email_presentation import language_context


def attach_workflow_print(source, recipient):
	with recipient_user(recipient), language_context(recipient):
		visible = visible_document(source, recipient)
		settings = frappe.get_single("Print Settings").as_dict()
		if source.meta.is_submittable:
			if source.docstatus.is_draft() and not cint(settings.get("allow_print_for_draft")):
				frappe.throw(_("Not allowed to print draft documents"), frappe.PermissionError)
			if source.docstatus.is_cancelled() and not cint(settings.get("allow_print_for_cancelled")):
				frappe.throw(_("Not allowed to print cancelled documents"), frappe.PermissionError)

		# Use the Standard layout without loading linked titles or running configurable print templates.
		meta = copy(visible.meta)
		meta.fields = [copy(field) for field in meta.fields if field.fieldtype != "HTML"]
		for child in visible.get_all_children():
			for field in child.meta.fields:
				if field.fieldtype == "HTML":
					child.set(field.fieldname, None)
		visible.print_heading = None
		visible.sub_heading = None
		body = frappe.get_template(standard_format).render(
			doc=visible, layout=make_layout(visible, meta), print_settings=settings, no_letterhead=True,
		)
		html = scrub_urls(f'<html><head><style>{get_print_style()}</style></head>'
			f'<body><main class="print-format">{body}</main></body></html>')
		ignore_print_permissions = frappe.flags.ignore_print_permissions
		try:
			attachment = frappe.attach_print(source.doctype, source.name, file_name=source.name, html=html)
		finally:
			frappe.flags.ignore_print_permissions = ignore_print_permissions
		if isinstance(attachment["fcontent"], str):
			attachment["fcontent"] = attachment["fcontent"].encode()
		return attachment
