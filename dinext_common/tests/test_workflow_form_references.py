"""Preserve form approval results for producer-owned aggregate references."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from dinext_common.workflow_approval import api


class TestWorkflowFormReferences(TestCase):
	def setUp(self):
		self.source = SimpleNamespace(doctype="Review Bundle", name="BUNDLE-1", check_permission=Mock())
		self.enterContext(
			patch.object(api.frappe, "local", SimpleNamespace(flags=SimpleNamespace(in_test=False)))
		)
		self.enterContext(patch.object(api.frappe, "get_doc", return_value=self.source))
		self.enterContext(
			patch.object(
				api.frappe, "get_hooks", return_value={"Review Bundle": ["example.review_references"]}
			)
		)
		self.enterContext(
			patch.object(
				api.frappe, "get_attr", return_value=lambda source: ("Review Item", ["HIDDEN", "OPEN"])
			)
		)

	def test_aggregate_comments_include_only_readable_child_sources(self):
		def permissions(_references, _user, cache):
			cache.update({("Review Item", "HIDDEN"): False, ("Review Item", "OPEN"): True})

		with (
			patch.object(api.frappe, "session", SimpleNamespace(user="reader@example.com")),
			patch.object(api, "prepare_source_permissions", side_effect=permissions),
			patch.object(api, "get_latest_round_comments", side_effect=lambda doctype, names: list(names)),
		):
			self.assertEqual(api.get_workflow_comments("Review Bundle", "BUNDLE-1"), ["OPEN"])

	def test_aggregate_banner_uses_the_registered_sources(self):
		def active_rows(doctype, names):
			if doctype == "Review Item" and names == ["HIDDEN", "OPEN"]:
				return [SimpleNamespace(approval_round_id="CHILD-ROUND")]
			return []

		with (
			patch.object(api, "_active_round_rows", side_effect=active_rows),
			patch.object(api, "describe_rebuild_rounds", return_value=[]),
			patch.object(api, "get_required_state_pending_tasks", return_value=[]),
			patch.object(api, "_caller_is_system_manager", return_value=False),
		):
			self.assertEqual(
				api.get_form_approval_banner("Review Bundle", "BUNDLE-1")["round_id"], "CHILD-ROUND"
			)
