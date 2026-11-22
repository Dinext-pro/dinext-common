"""Translate expected comment policy failures at the Frappe boundary."""

import frappe
from frappe import _

from dinext_common.workflow_approval import policy


class WorkflowCommentValidationError(frappe.ValidationError):
	"""An expected required/length error suitable for a user-facing response."""


def normalize_comment(value: object, *, required: bool = False,
	max_codepoints: int = policy.MAX_COMMENT_CODEPOINTS) -> str:
	try:
		return policy.normalize_comment(value, required=required, max_codepoints=max_codepoints)
	except ValueError as exc:
		if str(exc) == "A comment is required for this workflow action":
			message = _("A comment is required for this workflow action")
		elif str(exc) == f"Workflow comments cannot exceed {max_codepoints} characters":
			message = _("Workflow comments cannot exceed {0} characters").format(max_codepoints)
		else:
			raise
		frappe.throw(message, exc=WorkflowCommentValidationError)


def discard_collected_comment_messages(error: Exception, previous_count: int) -> None:
	"""Bulk returns this error in its item result, so avoid a second popup."""
	if isinstance(error, WorkflowCommentValidationError):
		del frappe.local.message_log[previous_count:]
