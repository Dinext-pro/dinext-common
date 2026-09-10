"""Re-run idempotent legacy task migration with deterministic assignee recovery."""

from dinext_common.patches.v1_0.generalize_parallel_workflow_approvals import (
	_migrate_legacy_tasks,
)


def execute() -> None:
	_migrate_legacy_tasks()
