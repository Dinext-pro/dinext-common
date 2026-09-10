"""Generic task-based approval services for Frappe Workflows."""

from dinext_common.workflow_approval.fingerprint import FINGERPRINT_VERSION
from dinext_common.workflow_approval.policy import PARALLEL_POLICIES

__all__ = ["FINGERPRINT_VERSION", "PARALLEL_POLICIES"]
