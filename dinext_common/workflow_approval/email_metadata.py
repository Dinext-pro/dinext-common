"""Custom fields extending Frappe-owned Workflow metadata."""


def extend_email_fields(fields):
	fields["Workflow Action"].append({"fieldname": "custom_notification_suppressed", "fieldtype": "Check", "label": "Notification Suppressed", "default": "0", "hidden": 1, "read_only": 1, "insert_after": "custom_notification_status"})
	parent = fields["Workflow"]
	parent.append({"fieldname": "custom_email_profile_version", "fieldtype": "Int", "label": "Email Profile Version", "default": "0", "hidden": 1, "read_only": 1, "insert_after": "send_email_alert"})
	for row in parent:
		if row["fieldname"] == "custom_group_send_time":
			row.update(hidden=1, mandatory_depends_on="")
		if row["fieldname"] == "custom_group_email_template":
			row["insert_after"] = "custom_group_send_times"
	parent.append({
		"fieldname": "custom_group_send_times", "fieldtype": "Data",
		"label": "Digest Send Times", "insert_after": "custom_group_send_time",
		"description": "Recipient-local times, for example: 08:00, 17:00",
		"depends_on": "eval:doc.send_email_alert && doc.custom_group_workflow_action_emails && doc.custom_group_interval_unit=='Days'",
		"mandatory_depends_on": "eval:doc.send_email_alert && doc.custom_group_workflow_action_emails && doc.custom_group_interval_unit=='Days'",
	})
	enabled = "eval:doc.send_email"
	grouped = "eval:doc.send_email && doc.custom_group_workflow_action_emails"
	daily = grouped + " && doc.custom_group_interval_unit=='Days'"
	immediate = "eval:doc.send_email && !doc.custom_group_workflow_action_emails"
	state = [
		{"fieldname": "custom_workflow_approval_email_section", "fieldtype": "Section Break", "label": "Workflow Approval Email", "insert_after": "send_email", "depends_on": enabled},
		{"fieldname": "custom_email_settings_source", "fieldtype": "Select", "label": "Email Settings Source", "options": "From Workflow\nState settings", "read_only": 1, "depends_on": enabled},
		{"fieldname": "custom_email_settings_override", "fieldtype": "Check", "label": "Override Workflow Email Settings", "default": "0", "hidden": 1},
		{"fieldname": "custom_email_settings_reset", "fieldtype": "Button", "label": "Use Workflow Settings", "depends_on": "eval:doc.send_email && doc.custom_email_settings_override"},
		{"fieldname": "custom_group_workflow_action_emails", "fieldtype": "Check", "label": "Group Workflow Action Emails", "default": "0", "depends_on": enabled},
		{"fieldname": "custom_attach_document_pdf", "fieldtype": "Check", "label": "Attach Document PDF", "default": "0", "depends_on": immediate},
		{"fieldname": "custom_group_interval_unit", "fieldtype": "Select", "label": "Digest Interval Unit", "options": "Hours\nDays", "depends_on": grouped, "mandatory_depends_on": grouped},
		{"fieldname": "custom_group_interval_value", "fieldtype": "Int", "label": "Digest Interval", "depends_on": grouped, "mandatory_depends_on": grouped, "non_negative": 1},
		{"fieldname": "custom_group_send_times", "fieldtype": "Data", "label": "Digest Send Times", "depends_on": daily, "mandatory_depends_on": daily, "description": "Recipient-local times, for example: 08:00, 17:00"},
		{"fieldname": "custom_group_email_template", "fieldtype": "Link", "label": "Digest Email Template", "options": "Email Template", "depends_on": grouped},
		{"fieldname": "custom_group_schedule_anchor", "fieldtype": "Datetime", "label": "Digest Schedule Anchor", "hidden": 1, "read_only": 1},
	]
	for previous, row in zip(state, state[1:]):
		row["insert_after"] = previous["fieldname"]
	fields["Workflow Document State"] = state


def ensure_state_email_properties():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	make_property_setter(
		"Workflow Document State", "next_action_email_template", "depends_on",
		"eval:doc.send_email && !doc.custom_group_workflow_action_emails", "Data",
		for_doctype=False, validate_fields_for_doctype=False,
	)


def ensure_workflow_email_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from dinext_common.workflow_approval.metadata import get_workflow_approval_custom_fields
	all_fields = get_workflow_approval_custom_fields()
	global_names = {"custom_email_profile_version", "custom_group_send_times", "custom_group_send_time", "custom_group_email_template"}
	fields = {
		"Workflow": [row for row in all_fields["Workflow"] if row["fieldname"] in global_names],
		"Workflow Document State": all_fields["Workflow Document State"],
		"Workflow Action": [row for row in all_fields["Workflow Action"] if row["fieldname"] == "custom_notification_suppressed"],
	}
	create_custom_fields(fields, ignore_validate=True, update=True)
	ensure_state_email_properties()
