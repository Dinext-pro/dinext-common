"""Recipient permissions for workflow mail rendering and queued delivery."""

import hashlib
import json
from contextlib import contextmanager
from urllib.parse import quote

import frappe
from frappe.utils import get_datetime

SCOPE_HEADER = "X-Dinext-Workflow-Delivery"
SENDER_ADDRESS = "ikhmel@dinext.ru"


@contextmanager
def recipient_user(user):
	previous = frappe.session.user
	frappe.session.user = user
	try:
		yield
	finally:
		frappe.session.user = previous


def restricted_fields(source, recipient):
	with recipient_user(recipient):
		levels = source.get_permlevel_access("read") if recipient != "Administrator" else None
		fields = [("", df) for df in source.meta.fields]
		for table in source.meta.get_table_fields():
			fields.extend((table.fieldname, df) for df in frappe.get_meta(table.options).fields)
	return sorted(
		(table, df.fieldname) for table, df in fields
		if df.fieldtype == "Password" or (levels is not None and df.permlevel and df.permlevel not in levels)
	)


def visible_document(source, recipient):
	doc = frappe.get_doc(source.as_dict(no_private_properties=True))
	for table, fieldname in restricted_fields(source, recipient):
		for record in (doc.get(table) or []) if table else (doc,):
			if fieldname in record.__dict__:
				delattr(record, fieldname)
	return doc


def authorized_source(task, recipient):
	from dinext_common.workflow_approval.notifications import recipient_can_read

	try:
		source = frappe.get_doc(task.reference_doctype, task.reference_name)
	except frappe.DoesNotExistError:
		return None
	if task.source_created_at and get_datetime(source.creation) != get_datetime(task.source_created_at):
		return None
	return source if recipient_can_read(task, source, recipient) else None


def authorization_signature(recipient, sources):
	from dinext_common.workflow_approval.engine import _has_source_read_permission

	entries = {}
	for source in sources:
		entries[(source.doctype, source.name)] = _source_permission_record(source, recipient)
		for path in frappe.get_hooks("workflow_approval_email_dependencies") or []:
			for doctype, name in frappe.get_attr(path)(source) or ():
				if (doctype, name) in entries:
					continue
				try:
					linked = frappe.get_doc(doctype, name)
				except frappe.DoesNotExistError:
					linked = None
				entries[(doctype, name)] = (
					_source_permission_record(linked, recipient)
					if linked and _has_source_read_permission(linked, recipient) else None
				)
	data = [(doctype, name, entries[(doctype, name)]) for doctype, name in sorted(entries)]
	return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()


def _source_permission_record(source, recipient):
	return str(source.creation), restricted_fields(source, recipient)


def delivery_scope(recipient, sources_by_task):
	signature = authorization_signature(recipient, sources_by_task.values())
	return " ".join(("1", quote(recipient, safe=""), signature, *(quote(name, safe="") for name in sources_by_task)))
