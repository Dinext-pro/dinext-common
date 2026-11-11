"""Keep existing approvals while introducing per-document Workflow scenarios."""


def execute():
	from dinext_common.workflow_approval.scenarios.migration import execute as migrate

	return migrate()
