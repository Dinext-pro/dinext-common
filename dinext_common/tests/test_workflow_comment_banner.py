"""Visible required comments belong to the latest decision round, not one voter."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from dinext_common.tests.test_required_state_pending import PendingFixture
from dinext_common.workflow_approval import api


class TestWorkflowCommentBanner(PendingFixture, FrappeTestCase):

	def decision(self, actor, text, *, required=True, offset=0, source=None, completion_source="Manual"):
		task = self.task(actor, [], source=source, status="Completed")
		uuid = "comment-required" if required else "without-comment"
		frappe.db.set_value(
			"Workflow Task",
			task.name,
			{
				"transition_uuid": uuid,
				"vote_comment": text,
				"completed_at": add_to_date(now_datetime(), seconds=offset),
				"completion_source": completion_source,
				"round_manifest": json.dumps({"transitions": [{
					"transition_uuid": uuid, "comment_is_required": required,
				}]}),
			},
			update_modified=False,
		)
		return task

	def banner(self, source=None):
		self.assertTrue(hasattr(api, "get_workflow_comments"), "Required-comment banner API is missing")
		source = source or self.source
		return api.get_workflow_comments(source.doctype, source.name)

	def test_comment_is_visible_while_round_is_open(self):
		self.decision("alice@example.com", "Please correct the hours")
		self.task("bob@example.com", ["Required"])
		rows = self.banner()
		self.assertEqual([(row["author"], row["comment"]) for row in rows], [
			("alice@example.com", "Please correct the hours"),
		])

	def test_all_comment_authors_remain_after_another_action_without_comment(self):
		self.decision("alice@example.com", "Correct the dates", offset=-3)
		self.decision("bob@example.com", "Attach details", offset=-2)
		self.decision("carol@example.com", "", required=False, offset=-1)
		self.assertEqual([(row["author"], row["comment"]) for row in self.banner()], [
			("alice@example.com", "Correct the dates"),
			("bob@example.com", "Attach details"),
		])

	def test_optional_comment_is_not_included(self):
		self.decision("alice@example.com", "Optional explanation", required=False)
		self.assertEqual(self.banner(), [])

	def test_new_decision_round_without_required_comments_clears_previous_comments(self):
		self.decision("alice@example.com", "Old comment", offset=-5)
		self.round_id = frappe.generate_hash(length=40)
		self.decision("bob@example.com", "", required=False)
		self.assertEqual(self.banner(), [])

	def test_unanswered_new_round_does_not_remove_last_comments(self):
		self.decision("alice@example.com", "Still relevant", offset=-5)
		self.round_id = frappe.generate_hash(length=40)
		self.task("bob@example.com", ["Required"])
		self.assertEqual([row["comment"] for row in self.banner()], ["Still relevant"])

	def test_carried_copy_does_not_establish_a_new_decision_round(self):
		self.decision("alice@example.com", "Last real comment", offset=-5)
		self.round_id = frappe.generate_hash(length=40)
		self.decision("bob@example.com", "", required=False, completion_source="Carried")
		self.assertEqual([row["comment"] for row in self.banner()], ["Last real comment"])

	def test_finished_round_and_link_bulk_actions_are_included(self):
		for offset, source in enumerate(("Signed Link", "Bulk")):
			task = self.decision(f"actor-{offset}@example.com", source, offset=offset, completion_source=source)
			frappe.db.set_value("Workflow Task", task.name, "round_status", "Transitioned")
		self.assertEqual([row["comment"] for row in self.banner()], ["Signed Link", "Bulk"])

	def test_current_rules_do_not_override_the_recorded_required_flag(self):
		self.decision("alice@example.com", "Historical rule")
		frappe.get_doc({
			"doctype": "Workflow Transition", "parent": self.workflow.name,
			"parenttype": "Workflow", "parentfield": "transitions", "state": "Open",
			"action": "Comment", "next_state": "Optional",
			"custom_transition_uuid": "comment-required", "custom_comment_is_required": 0,
		}).db_insert()
		self.assertEqual([row["comment"] for row in self.banner()], ["Historical rule"])

	def test_unverified_or_empty_comments_are_omitted(self):
		task = self.decision("alice@example.com", "Unverified")
		frappe.db.set_value("Workflow Task", task.name, "round_manifest", "{}")
		self.decision("bob@example.com", "  \n  ")
		self.assertEqual(self.banner(), [])

	def test_selected_transition_uuid_controls_inclusion(self):
		task = self.decision("alice@example.com", "An optional comment", required=False)
		frappe.db.set_value("Workflow Task", task.name, "round_manifest", json.dumps({"transitions": [
			{"transition_uuid": "comment-required", "comment_is_required": True},
			{"transition_uuid": "without-comment", "comment_is_required": False},
		]}))
		self.assertEqual(self.banner(), [])

	def test_malformed_snapshot_is_omitted(self):
		task = self.decision("alice@example.com", "Unverified")
		for value in ('{"transitions": {}}', "[]", "{broken"):
			frappe.db.set_value("Workflow Task", task.name, "round_manifest", value)
			self.assertEqual(self.banner(), [])

	def test_user_name_falls_back_to_identity(self):
		self.decision("unknown-author@example.com", "Unchanged text")
		row = self.banner()[0]
		self.assertEqual(row["author_name"], "unknown-author@example.com")
		self.assertEqual(row["reference_name"], self.source.name)

	def test_source_permission_is_required(self):
		self.decision("alice@example.com", "Private comment")
		with patch.object(self.source, "check_permission", side_effect=frappe.PermissionError):
			with patch.object(api.frappe, "get_doc", return_value=self.source):
				with self.assertRaises(frappe.PermissionError):
					self.banner()

	def test_no_decisions_gives_no_comment_banner(self):
		self.task("alice@example.com", ["Required"])
		self.assertEqual(self.banner(), [])

	def test_archived_source_decisions_are_not_exposed_on_a_recreated_document(self):
		task = self.decision("alice@example.com", "Archived source")
		frappe.db.set_value("Workflow Task", task.name, "source_deleted_at", now_datetime())
		self.assertEqual(self.banner(), [])

	def timesheet(self):
		parent = frappe.get_doc({"doctype": "User Timesheet", "name": "_Test Comments " + frappe.generate_hash()})
		parent.db_insert()
		positions = []
		for index in range(2):
			position = frappe.get_doc({
				"doctype": "User Timesheet Position", "user_timesheet": parent.name,
				"name": f"_Test Comments Position {index} " + frappe.generate_hash(),
			})
			position.db_insert()
			positions.append(position)
		return parent, positions

	def test_timesheet_combines_each_positions_latest_comment_round(self):
		parent, positions = self.timesheet()
		self.decision("alice@example.com", "First position", source=positions[0])
		self.round_id = frappe.generate_hash(length=40)
		self.decision("bob@example.com", "Second position", source=positions[1])
		self.assertEqual({row["comment"] for row in self.banner(parent)}, {"First position", "Second position"})
		self.round_id = frappe.generate_hash(length=40)
		self.decision("alice@example.com", "", required=False, source=positions[0], offset=5)
		self.assertEqual([row["comment"] for row in self.banner(parent)], ["Second position"])

	def test_timesheet_does_not_expose_unreadable_position_comments(self):
		parent, positions = self.timesheet()
		self.decision("alice@example.com", "Private", source=positions[0])
		self.decision("bob@example.com", "Visible", source=positions[1])

		def permissions(rows, user, cache):
			cache.update({("User Timesheet Position", position.name): index == 1
				for index, position in enumerate(positions)})

		with patch.object(api, "prepare_source_permissions", side_effect=permissions):
			self.assertEqual([row["comment"] for row in self.banner(parent)], ["Visible"])
