from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.core.doctype.submission_queue.submission_queue import SubmissionQueue

from dinext_common.workflow_approval import lifecycle
from dinext_common.workflow_approval.queued_submission import DinextSubmissionQueue


class TestWorkflowSiteSchemaCompatibility(TestCase):
    def test_deleting_a_document_on_legacy_site_does_not_query_new_task_fields(self):
        source = SimpleNamespace(doctype="Issue", name="LEGACY-ISSUE")

        with (
            patch.object(frappe.db, "get_db_table_columns", return_value=["name", "doc", "wt_docname"]),
            patch("dinext_common.workflow_approval.scenarios.service.archive_source"),
            patch.object(frappe, "get_all") as get_all,
        ):
            lifecycle.on_source_trash(source)

        get_all.assert_not_called()

    def test_native_background_submission_on_legacy_site_uses_frappe_worker(self):
        queue = DinextSubmissionQueue({"doctype": "Submission Queue", "name": "LEGACY-QUEUE"})
        doc = SimpleNamespace(doctype="Issue", name="LEGACY-ISSUE")

        with (
            patch.object(frappe.db, "get_value", return_value="Queued"),
            patch.object(frappe.db, "get_db_table_columns", return_value=["name", "doc", "wt_docname"]),
            patch.object(frappe, "get_all", return_value=[]) as get_all,
            patch.object(SubmissionQueue, "background_submission", autospec=True) as native,
        ):
            queue.background_submission(doc, "Submit")

        get_all.assert_not_called()
        native.assert_called_once_with(queue, doc, "Submit")
