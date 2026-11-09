"""Workflow transition policy fields and server-side validation."""

from datetime import datetime

import frappe

from dinext_common.workflow_approval.deadlines.policy import positive_amount
from dinext_common.workflow_approval.email_settings import checked, normalize_send_times, value


def transition_fields():
	enabled = "eval:doc.custom_deadline_enabled"
	grouped = enabled + " && doc.custom_deadline_email_mode=='Digest'"
	definitions = [
		("section", "Section Break", "Approval Deadline", {}),
		("enabled", "Check", "Enable Approval Deadline", {"default": "0"}),
		("value", "Float", "Deadline Interval", {"depends_on": enabled, "mandatory_depends_on": enabled}),
		(
			"unit",
			"Autocomplete",
			"Deadline Interval Type",
			{"default": "Hours", "depends_on": enabled, "mandatory_depends_on": enabled},
		),
		(
			"recipient_type",
			"Autocomplete",
			"Deadline Recipient Type",
			{"default": "User", "depends_on": enabled, "mandatory_depends_on": enabled},
		),
		(
			"recipient_user",
			"Link",
			"Deadline Recipient",
			{"options": "User", "depends_on": enabled + " && doc.custom_deadline_recipient_type=='User'"},
		),
		(
			"recipient_role",
			"Link",
			"Deadline Recipient Role",
			{"options": "Role", "depends_on": enabled + " && doc.custom_deadline_recipient_type=='Role'"},
		),
		(
			"email_mode",
			"Select",
			"Deadline Notification Mode",
			{"options": "Immediate\nDigest", "default": "Digest", "depends_on": enabled},
		),
		(
			"email_template",
			"Link",
			"Deadline Email Template",
			{"options": "Email Template", "depends_on": enabled},
		),
		(
			"interval_unit",
			"Autocomplete",
			"Deadline Digest Interval Type",
			{"default": "Days", "depends_on": grouped},
		),
		("interval_value", "Int", "Deadline Digest Interval", {"default": "1", "depends_on": grouped}),
		(
			"send_times",
			"Data",
			"Deadline Digest Send Times",
			{
				"default": "08:00, 17:00",
				"depends_on": grouped + " && doc.custom_deadline_interval_unit!='Hours'",
			},
		),
		("schedule_anchor", "Datetime", "Deadline Schedule Anchor", {"hidden": 1, "read_only": 1}),
	]
	rows = []
	previous = "custom_auto_complete_unchanged"
	for suffix, fieldtype, label, extra in definitions:
		fieldname = "custom_deadline_" + suffix
		rows.append(
			dict(
				fieldname=fieldname,
				fieldtype=fieldtype,
				label=label,
				insert_after=previous,
				module="Dinext Common",
				**extra,
			)
		)
		previous = fieldname
	return rows


def _schedule(row):
	return tuple(
		value(row, key)
		for key in (
			"custom_deadline_email_mode",
			"custom_deadline_interval_unit",
			"custom_deadline_interval_value",
			"custom_deadline_send_times",
		)
	)


def prepare_settings(workflow, previous=None, *, extensions=None, now=None):
	if not any(checked(value(row, "custom_deadline_enabled")) for row in value(workflow, "transitions", [])):
		return
	if extensions is None:
		from dinext_common.workflow_approval.deadlines.extensions import get_extensions

		extensions = get_extensions(value(workflow, "document_type"))
	now = now or frappe.utils.now_datetime
	states = {value(row, "state"): row for row in value(workflow, "states", [])}
	old = {value(row, "custom_transition_uuid"): row for row in value(previous, "transitions", [])}
	for row in value(workflow, "transitions", []):
		if not checked(value(row, "custom_deadline_enabled")):
			continue
		target = states.get(value(row, "next_state"))
		if not target or checked(value(target, "is_optional_state")):
			raise ValueError("Approval deadlines require a mandatory target state")
		unit = value(row, "custom_deadline_unit")
		if unit not in ("Hours", "Days") and unit not in extensions.get("deadline_intervals", {}):
			raise ValueError("Unknown deadline interval: " + str(unit))
		integer = unit == "Days" or extensions.get("deadline_intervals", {}).get(unit, {}).get(
			"integer", False
		)
		row.custom_deadline_value = positive_amount(value(row, "custom_deadline_value"), integer=integer)
		receiver = value(row, "custom_deadline_recipient_type")
		if receiver not in ("User", "Role") and receiver not in extensions.get("recipients", {}):
			raise ValueError("Unknown deadline recipient type: " + str(receiver))
		if receiver == "User" and not value(row, "custom_deadline_recipient_user"):
			raise ValueError("Deadline recipient is required")
		if receiver == "Role" and not value(row, "custom_deadline_recipient_role"):
			raise ValueError("Deadline recipient role is required")
		mode = value(row, "custom_deadline_email_mode")
		if mode not in ("Immediate", "Digest"):
			raise ValueError("Choose an immediate notification or digest")
		if mode == "Digest":
			interval_unit = value(row, "custom_deadline_interval_unit")
			if interval_unit not in ("Hours", "Days") and interval_unit not in extensions.get(
				"sending_intervals", {}
			):
				raise ValueError("Unknown deadline sending interval: " + str(interval_unit))
			row.custom_deadline_interval_value = positive_amount(
				value(row, "custom_deadline_interval_value"), integer=True
			)
			row.custom_deadline_send_times = (
				normalize_send_times(value(row, "custom_deadline_send_times"))
				if interval_unit != "Hours"
				else ""
			)
		prior = old.get(value(row, "custom_transition_uuid"))
		row.custom_deadline_schedule_anchor = (
			value(prior, "custom_deadline_schedule_anchor")
			if prior
			and _schedule(row) == _schedule(prior)
			and value(prior, "custom_deadline_schedule_anchor")
			else now()
		)


def ensure_metadata():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Workflow Transition": transition_fields()}, ignore_validate=True, update=True)


@frappe.whitelist()
def get_options(doctype: str) -> dict:
	if not frappe.has_permission("Workflow", "read"):
		raise frappe.PermissionError
	from dinext_common.workflow_approval.deadlines.extensions import options

	return options(doctype)
