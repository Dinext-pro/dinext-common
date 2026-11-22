def execute():
	from dinext_common.workflow_approval.deadlines.metadata import ensure_metadata
	from dinext_common.workflow_approval.email_preferences import migrate_preferences
	from dinext_common.workflow_approval.metadata import ensure_workflow_approval_email_templates

	ensure_metadata()
	migrate_preferences()
	ensure_workflow_approval_email_templates()
