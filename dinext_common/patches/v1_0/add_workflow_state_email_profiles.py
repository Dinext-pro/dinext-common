"""Install state email schema before fixture import and profile migration."""


def execute():
	from dinext_common.workflow_approval.email_metadata import ensure_workflow_email_fields
	ensure_workflow_email_fields()
