import unittest


class TestDeadlineBackfill(unittest.TestCase):
	def test_technical_rebuild_uses_original_assignment_but_revisit_starts_again(self):
		from dinext_common.workflow_approval.deadlines.backfill import original_assignment

		history = [
			dict(name="first", approver="a", workflow_state="Pending", creation="2026-11-01 10:00:00"),
			dict(name="rebuilt", approver="a", workflow_state="Pending", creation="2026-11-02 10:00:00"),
		]
		task = dict(name="rebuilt", approver="a", workflow_state="Pending", creation="2026-11-02 10:00:00")
		self.assertEqual(original_assignment(task, history)["name"], "first")
		history += [
			dict(name="editing", approver="author", workflow_state="Editing", creation="2026-11-03 10:00:00"),
			dict(name="new", approver="a", workflow_state="Pending", creation="2026-11-04 10:00:00"),
		]
		task = dict(history[-1])
		self.assertEqual(original_assignment(task, history)["name"], "new")

	def test_missing_evidence_is_unknown(self):
		from dinext_common.workflow_approval.deadlines.backfill import original_assignment

		self.assertIsNone(
			original_assignment(dict(name="missing", approver="a", workflow_state="Pending"), [])
		)
