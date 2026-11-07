"""Custom fields extending Frappe-owned Workflow metadata."""


def extend_email_fields(fields):
	parent = fields["Workflow"]
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
