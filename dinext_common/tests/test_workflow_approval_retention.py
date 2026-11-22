import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestWorkflowApprovalRetention(unittest.TestCase):
	def retention(self):
		from dinext_common.workflow_approval import retention

		return retention

	def test_open_cleanup_rule_never_selects_active_workflow_tasks(self):
		retention = self.retention()
		rule = {"status": "Open"}
		with patch.object(retention.frappe, "get_all") as get_all:
			self.assertEqual(retention._candidate_round_ids(rule, "2026-01-01"), [])
			get_all.assert_not_called()

	def test_terminal_round_is_kept_while_reuse_lineage_references_it(self):
		retention = self.retention()
		task = SimpleNamespace(
			name="WT-1",
			status="Completed",
			round_status="Transitioned",
			finalization_status="Finished",
		)
		mock_frappe = MagicMock()
		mock_frappe.db.exists.return_value = True
		with patch.object(retention, "frappe", mock_frappe):
			self.assertTrue(retention._round_is_protected([task]))

	def test_terminal_round_is_deletable_only_after_delivery_is_terminal(self):
		retention = self.retention()
		task = SimpleNamespace(
			name="WT-1",
			status="Completed",
			round_status="Transitioned",
			finalization_status="Finished",
		)
		mock_frappe = MagicMock()
		mock_frappe.db.exists.return_value = False
		mock_frappe.get_all.return_value = [
			SimpleNamespace(
				status="Completed",
				custom_notification_status="Enqueued",
				custom_delivery_key=None,
			)
		]
		with patch.object(retention, "frappe", mock_frappe):
			self.assertFalse(retention._round_is_protected([task]))

		mock_frappe.get_all.return_value[0].custom_notification_status = "Pending"
		with patch.object(retention, "frappe", mock_frappe):
			self.assertTrue(retention._round_is_protected([task]))
