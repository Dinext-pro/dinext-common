"""Install the editable Workflow fingerprint exclusion table."""

from dinext_common.workflow_approval.metadata import ensure_workflow_fingerprint_fields


def execute():
	ensure_workflow_fingerprint_fields()
