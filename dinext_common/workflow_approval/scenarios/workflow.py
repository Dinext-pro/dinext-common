"""Support active peer scenarios while retaining native Workflow validation."""

from frappe.workflow.doctype.workflow.workflow import Workflow

from dinext_common.workflow_approval.scenarios.metadata import validate_selection_settings


class DinextWorkflow(Workflow):
	def validate(self) -> None:
		validate_selection_settings(self)
		super().validate()

	def set_active(self) -> None:
		"""Activation no longer deactivates other schemas of the same DocType."""

	def update_default_workflow_status(self) -> None:
		"""Document selection initializes one source, never a whole DocType."""
