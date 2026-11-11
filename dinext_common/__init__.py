__version__ = "v26.07.20-02"

# Native calls in CLI/tests also need document-scoped Workflow resolution.
from dinext_common.workflow_approval.scenarios.compat import install as _install_workflow_compatibility

_install_workflow_compatibility()
