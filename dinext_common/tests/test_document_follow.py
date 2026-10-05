import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from jinja2 import Environment

from dinext_common import document_follow as follow
from dinext_common.overrides.scheduled_job_type import FOLLOW_METHODS, DinextScheduledJobType

NOW = datetime(2026, 10, 5, 12)
READER = "reader@example.test"
AUTHOR = "author@example.test"


class FollowFixture:
	def setUp(self):
		self.session = frappe._dict(user="Administrator", sid="unchanged-session")
		self.settings = frappe._dict(enabled=1, document_follow_notify=1, document_follow_frequency="Hourly")
		self.follows = [frappe._dict(ref_doctype="Task", ref_docname="TASK-READABLE")]
		self.comments = {}
		self.versions = []
		self.db_versions = []
		self.mentions = set()
		self.denied = set()
		self.deleted = set()
		self.permlevels = {0}
		self.meta = MagicMock()
		fields = {
			"subject": frappe._dict(fieldtype="Data", permlevel=0),
			"items": frappe._dict(fieldtype="Table", options="Task Item", permlevel=0),
			"secret-field": frappe._dict(fieldtype="Data", permlevel=1),
			"secret-table": frappe._dict(fieldtype="Table", options="Task Item", permlevel=1),
		}
		self.meta.get_field.side_effect = fields.get
		self.child_meta = MagicMock()
		self.child_meta.get_field.side_effect = {
			"description": frappe._dict(fieldtype="Data", permlevel=0),
			"child-secret": frappe._dict(fieldtype="Data", permlevel=1),
		}.get
		self.db = MagicMock()
		self.db.get_value.side_effect = self.get_value
		self.db.exists.side_effect = lambda dt, filters: (filters["parent"], filters["user"]) in self.mentions
		self.mail = self.start_patch("frappe.sendmail")
		self.start_patch("frappe.session", self.session)
		self.start_patch("frappe.db", self.db)
		self.start_patch("frappe.get_doc", side_effect=self.get_doc)
		self.query = self.start_patch("frappe.get_all", side_effect=self.get_all)
		self.permission = self.start_patch("frappe.has_permission", side_effect=self.has_permission)
		self.start_patch("frappe.get_meta", return_value=self.child_meta)
		self.start_patch("frappe.utils.now_datetime", return_value=NOW)
		self.start_patch("frappe.utils.nowdate", return_value=NOW.date().isoformat())
		self.start_patch("dinext_common.document_follow._", side_effect=lambda value: value)
		self.start_patch(
			"dinext_common.document_follow.get_url_to_form", side_effect=lambda dt, name: f"/{dt}/{name}"
		)
		self.start_patch("dinext_common.document_follow.core.get_user_list", return_value=[READER])
		self.start_patch(
			"dinext_common.document_follow.core.get_document_followed_by_user",
			side_effect=lambda user: self.follows,
		)
		self.original_get_version = follow.core.get_version
		self.version_query = self.start_patch(
			"dinext_common.document_follow.core.get_version", side_effect=lambda *args: self.versions
		)

	def start_patch(self, target, *args, **kwargs):
		patcher = patch(target, *args, **kwargs)
		value = patcher.start()
		self.addCleanup(patcher.stop)
		return value

	def get_value(self, doctype, name, fields, **kwargs):
		self.assertEqual(doctype, "User")
		return self.settings

	def get_doc(self, doctype, name):
		if name in self.deleted:
			raise frappe.DoesNotExistError(name)
		return SimpleNamespace(
			doctype=doctype, name=name, meta=self.meta, get_permlevel_access=lambda ptype: self.permlevels
		)

	def has_permission(self, doctype, permission, *, doc, user):
		self.assertEqual(permission, "read")
		self.assertEqual(self.session.user, user)
		return doc.name not in self.denied

	def get_all(self, doctype, *, filters, **kwargs):
		if doctype == "Version":
			return self.db_versions
		self.assertEqual(doctype, "Comment")
		if isinstance(filters, dict):
			comment = self.comments.get(filters["name"])
			return [comment] if comment else []
		result = []
		for comment in self.comments.values():
			allowed = True
			for field, operator, value in filters:
				actual = comment[field]
				if field == "modified":
					value = frappe.utils.get_datetime(value)
				if not {
					"=": lambda: actual == value,
					"!=": lambda: actual != value,
					">": lambda: actual > value,
					"<": lambda: actual < value,
				}[operator]():
					allowed = False
					break
			if allowed:
				result.append(comment)
		return result

	def comment(self, name, visibility="Visible to everyone", **kwargs):
		row = frappe._dict(
			name=name,
			owner=AUTHOR,
			content=f"CONTENT-{name}",
			modified=NOW - timedelta(minutes=5),
			modified_by="editor@example.test",
			comment_type="Comment",
			reference_doctype="Task",
			reference_name="TASK-READABLE",
			custom_visibility=visibility,
			custom_reply_to="",
		)
		row.update(kwargs)
		self.comments[name] = row
		return row

	def contents(self, user=READER):
		message, _docinfo = follow.get_message_for_user("Hourly", user)
		return {item["data"]["comment"].strip() for item in message if item["type"] == "comment"}

	def assert_no_disclosure(self, forbidden):
		for call in self.mail.call_args_list:
			payload = call.kwargs
			template = Path(follow.core.__file__).parents[2] / "templates/emails/document_follow.html"
			html = Environment(autoescape=True).from_string(template.read_text()).render(**payload["args"])
			for surface in (
				json.dumps(payload, default=str),
				payload["subject"],
				html,
				follow.html2text(html),
			):
				for value in forbidden:
					self.assertNotIn(value, surface)

	def change_after_collection(self, change):
		original = follow.get_message_for_user
		calls = 0

		def collect(*args):
			nonlocal calls
			result = original(*args)
			calls += 1
			if calls == 1:
				change()
			return result

		return patch.object(follow, "get_message_for_user", side_effect=collect)


class TestDocumentFollow(FollowFixture, unittest.TestCase):
	def test_public_and_legacy_comments_match_standard_timeline(self):
		self.comment("public", content="<b>Public</b>")
		legacy = self.comment("legacy", "")
		legacy.pop("custom_visibility")
		message, docinfo = follow.get_message_for_user("Hourly", READER)
		standard = follow.core.get_comments("Task", "TASK-READABLE", "Hourly", READER)
		self.assertEqual(message, sorted(standard, key=lambda item: item["time"], reverse=True))
		self.assertEqual(len(docinfo), 1)

	def test_author_only_uses_owner_and_administrator(self):
		self.comment("private", "Visible to only you", comment_email=READER, comment_by=READER)
		for user, expected in [
			(READER, set()),
			(AUTHOR, {"CONTENT-private"}),
			("Administrator", {"CONTENT-private"}),
		]:
			with self.subTest(user=user):
				self.assertEqual(self.contents(user), expected)

	def test_mentioned_only_requires_exact_child_membership(self):
		self.comment("mentioned", "Visible to mentioned")
		self.assertEqual(self.contents(), set())
		self.mentions.add(("mentioned", READER))
		self.assertEqual(self.contents(), {"CONTENT-mentioned"})
		self.db.exists.assert_called_with(
			"User Group Member",
			{
				"user": READER,
				"parent": "mentioned",
				"parenttype": "Comment",
				"parentfield": "custom_mentions",
			},
		)
		self.assertEqual(self.contents(AUTHOR), {"CONTENT-mentioned"})
		self.assertEqual(self.contents("Administrator"), {"CONTENT-mentioned"})

	def test_unknown_visibility_fails_closed(self):
		self.comment("unknown", "Future private policy")
		for user in (READER, AUTHOR, "Administrator"):
			with self.subTest(user=user):
				self.assertEqual(self.contents(user), set())

	def test_public_reply_under_hidden_old_parent_is_absent(self):
		self.comment("old-parent", "Visible to only you", modified=NOW - timedelta(days=3))
		self.comment("reply", custom_reply_to="old-parent")
		self.assertEqual(self.contents(), set())
		self.assertEqual(self.contents(AUTHOR), {"CONTENT-reply"})

	def test_all_ancestors_require_visibility(self):
		self.comment("root", "Visible to mentioned", modified=NOW - timedelta(days=3))
		self.comment("middle", custom_reply_to="root", modified=NOW - timedelta(days=2))
		self.comment("leaf", custom_reply_to="middle")
		self.assertEqual(self.contents(), set())
		self.mentions.add(("root", READER))
		self.assertEqual(self.contents(), {"CONTENT-leaf"})

	def test_hidden_reply_does_not_hide_visible_siblings(self):
		self.comment("root")
		self.comment("private-reply", "Visible to only you", custom_reply_to="root")
		self.comment("public-reply", custom_reply_to="root")
		self.assertEqual(self.contents(), {"CONTENT-root", "CONTENT-public-reply"})

	def test_broken_cyclic_and_cross_document_threads_fail_closed(self):
		self.comment("missing", custom_reply_to="nonexistent")
		self.comment("cycle-a", custom_reply_to="cycle-b")
		self.comment("cycle-b", custom_reply_to="cycle-a")
		self.comment("other-doc", reference_name="OTHER-DOC")
		self.comment("cross-doc", custom_reply_to="other-doc")
		self.comment("other-type", reference_doctype="Project")
		self.comment("cross-type", custom_reply_to="other-type")
		self.assertEqual(self.contents(), set())

	def test_unreadable_document_is_not_collected(self):
		self.comment("private-doc")
		self.denied.add("TASK-READABLE")
		self.assertEqual(follow.get_message_for_user("Hourly", READER), ([], []))
		self.query.assert_not_called()
		self.version_query.assert_not_called()

	def test_deleted_document_and_permission_error_fail_closed(self):
		self.deleted.add("TASK-READABLE")
		self.assertEqual(self.contents(), set())
		self.deleted.clear()
		self.permission.side_effect = frappe.PermissionError
		self.assertEqual(self.contents(), set())

	def test_mixed_documents_never_expose_denied_name_values_or_author(self):
		self.follows.append(frappe._dict(ref_doctype="Task", ref_docname="DENIED-DOC-MARKER"))
		self.denied.add("DENIED-DOC-MARKER")
		self.comment("allowed")
		self.comment("denied", reference_name="DENIED-DOC-MARKER", modified_by="denied-author@example.test")
		self.assertTrue(follow.send_email_alert(READER, "Hourly"))
		self.assert_no_disclosure(["CONTENT-denied", "DENIED-DOC-MARKER", "denied-author@example.test"])

	def test_private_text_and_author_are_absent_from_all_email_surfaces(self):
		self.comment("public")
		self.comment("hidden", "Visible to only you", modified_by="hidden-author@example.test")
		self.assertTrue(follow.send_email_alert(READER, "Hourly"))
		self.assert_no_disclosure(["CONTENT-hidden", "hidden-author@example.test"])
		self.assertEqual(self.mail.call_args.kwargs["template"], "document_follow")
		self.assertEqual(self.mail.call_args.kwargs["recipients"], [READER])

	def test_hidden_only_digest_does_not_send(self):
		self.comment("hidden", "Visible to only you")
		follow.send_document_follow_mails("Hourly")
		self.mail.assert_not_called()
		self.db.commit.assert_not_called()

	def test_disabled_opted_out_missing_guest_and_frequency_mismatch_do_not_collect(self):
		for settings in (
			None,
			frappe._dict(self.settings, enabled=0),
			frappe._dict(self.settings, document_follow_notify=0),
			frappe._dict(self.settings, document_follow_frequency="Daily"),
		):
			with self.subTest(settings=settings):
				self.db.get_value.side_effect = None
				self.db.get_value.return_value = settings
				self.assertEqual(follow.get_message_for_user("Hourly", READER), ([], []))
		for user in (None, "", "Guest"):
			self.assertEqual(follow.get_message_for_user("Hourly", user), ([], []))
		self.query.assert_not_called()

	def test_recipient_context_and_session_id_are_restored_on_success_and_failure(self):
		self.comment("public")
		self.contents()
		self.assertEqual(self.session, {"user": "Administrator", "sid": "unchanged-session"})
		self.query.side_effect = RuntimeError("read failed")
		with self.assertRaisesRegex(RuntimeError, "read failed"):
			self.contents()
		self.assertEqual(self.session, {"user": "Administrator", "sid": "unchanged-session"})
		self.mail.assert_not_called()

	def test_access_revoked_after_collection_prevents_send(self):
		self.comment("stale")
		with self.change_after_collection(lambda: self.denied.add("TASK-READABLE")):
			follow.send_document_follow_mails("Hourly")
		self.mail.assert_not_called()
		self.db.commit.assert_not_called()

	def test_native_role_permission_memo_cannot_keep_revoked_access_at_send(self):
		from frappe.permissions import get_role_permissions

		self.comment("stale")
		roles = ["Follower"]
		meta = SimpleNamespace(name="Task", permissions=[frappe._dict(role="Follower", permlevel=0, read=1)])
		self.permission.side_effect = lambda dt, ptype, *, doc, user: get_role_permissions(
			meta, user=user
		).get("read")
		with (
			patch("frappe.get_roles", side_effect=lambda user: roles),
			self.change_after_collection(roles.clear),
		):
			follow.send_document_follow_mails("Hourly")
		self.mail.assert_not_called()

	def test_final_pass_uses_new_database_snapshot_after_access_revocation(self):
		self.comment("stale")
		live_access = [True]
		snapshot_access = [True]
		self.db.rollback.side_effect = lambda: snapshot_access.__setitem__(0, live_access[0])
		self.permission.side_effect = lambda *args, **kwargs: snapshot_access[0]
		with self.change_after_collection(lambda: live_access.__setitem__(0, False)):
			follow.send_document_follow_mails("Hourly")
		self.assertEqual(self.db.rollback.call_count, 2)
		self.mail.assert_not_called()

	def test_recipient_cache_maps_are_fresh_and_restored_even_after_failure(self):
		names = ("cache", "role_permissions", "request_cache")
		originals = {name: getattr(frappe.local, name, None) for name in names}
		try:
			seeded = {name: {"stale": True} for name in names}
			for name, cache in seeded.items():
				setattr(frappe.local, name, cache)
			with self.assertRaisesRegex(RuntimeError, "failed"):
				with follow._as_recipient(READER):
					for name in names:
						self.assertEqual(getattr(frappe.local, name), {})
					raise RuntimeError("failed")
			for name, cache in seeded.items():
				self.assertIs(getattr(frappe.local, name), cache)
			self.assertEqual(self.session.user, "Administrator")
		finally:
			for name, cache in originals.items():
				if cache is None:
					delattr(frappe.local, name)
				else:
					setattr(frappe.local, name, cache)

	def test_visibility_and_mention_revocation_before_send_are_rechecked(self):
		self.comment("public")
		private = self.comment("was-public")
		self.comment("was-mentioned", "Visible to mentioned")
		self.mentions.add(("was-mentioned", READER))

		def revoke():
			private.custom_visibility = "Visible to only you"
			self.mentions.clear()

		with self.change_after_collection(revoke):
			follow.send_document_follow_mails("Hourly")
		self.mail.assert_called_once()
		self.db.commit.assert_called_once()
		self.assert_no_disclosure(["CONTENT-was-public", "CONTENT-was-mentioned"])

	def test_parent_visibility_revoked_before_send_hides_reply(self):
		parent = self.comment("parent", modified=NOW - timedelta(days=3))
		self.comment("reply", custom_reply_to="parent")
		with self.change_after_collection(lambda: parent.update(custom_visibility="Visible to only you")):
			follow.send_document_follow_mails("Hourly")
		self.mail.assert_not_called()

	def test_unsubscription_and_user_settings_are_fresh_at_send(self):
		self.comment("public")
		for revoke in (
			lambda: self.follows.clear(),
			lambda: self.settings.update(enabled=0),
			lambda: self.settings.update(document_follow_notify=0),
		):
			with self.subTest(revoke=revoke):
				self.follows[:] = [frappe._dict(ref_doctype="Task", ref_docname="TASK-READABLE")]
				self.settings.update(enabled=1, document_follow_notify=1)
				with self.change_after_collection(revoke):
					follow.send_document_follow_mails("Hourly")
		self.mail.assert_not_called()

	def test_decisions_do_not_cross_recipient_boundaries(self):
		self.comment("public")
		self.comment("private", "Visible to only you")
		with patch.object(follow.core, "get_user_list", return_value=[AUTHOR, READER]):
			follow.send_document_follow_mails("Hourly")
		self.assertEqual(self.mail.call_count, 2)
		first, second = [call.kwargs for call in self.mail.call_args_list]
		self.assertIn("CONTENT-private", json.dumps(first, default=str))
		self.assertNotIn("CONTENT-private", json.dumps(second, default=str))
		self.assertEqual(self.session.user, "Administrator")

	def test_parent_child_and_added_row_versions_respect_field_read_permissions(self):
		def version(kind, **data):
			return {
				"type": kind,
				"data": data,
				"time": NOW - timedelta(minutes=3),
				"doctype": "Task",
				"doc_name": "TASK-READABLE",
				"by": "editor@example.test",
			}

		self.versions = [
			version("field changed", field="subject", **{"from": "old", "to": "new"}),
			version("field changed", field="secret-field", **{"from": "OLD-SECRET", "to": "NEW-SECRET"}),
			version(
				"row changed",
				table_field="items",
				field="description",
				**{"from": "old row", "to": "new row"},
			),
			version(
				"row changed",
				table_field="items",
				field="child-secret",
				**{"from": "CHILD-SECRET", "to": "other"},
			),
			version("row added", to="items"),
			version("row added", to="secret-table"),
		]
		message, _docinfo = follow.get_message_for_user("Hourly", READER)
		self.assertEqual(message, [self.versions[0], self.versions[2], self.versions[4]])
		follow.send_email_alert(READER, "Hourly")
		self.assert_no_disclosure(
			["secret-field", "OLD-SECRET", "NEW-SECRET", "child-secret", "CHILD-SECRET", "secret-table"]
		)
		self.child_meta.get_field.assert_any_call("child-secret")

	def test_shared_document_level_zero_table_changes_are_preserved(self):
		self.permlevels.clear()
		self.versions = [
			{
				"type": "row added",
				"data": {"to": "items"},
				"time": NOW,
				"doctype": "Task",
				"doc_name": "TASK-READABLE",
			}
		]
		message, _docinfo = follow.get_message_for_user("Hourly", READER)
		self.assertEqual(message, self.versions)

	def test_real_standard_version_builders_and_timeline_order_are_preserved(self):
		self.version_query.side_effect = self.original_get_version
		for offset, data in enumerate(
			(
				{"changed": [["subject", "old subject", "new subject"]]},
				{"row_changed": [["items", 1, "ROW-1", [["description", "old row", "new row"]]]]},
				{"added": [["items", {}]]},
			)
		):
			self.db_versions.append(
				frappe._dict(
					data=json.dumps(data), modified=NOW - timedelta(minutes=offset + 2), modified_by=AUTHOR
				)
			)
		self.comment("public", modified=NOW - timedelta(minutes=1))
		expected = self.original_get_version(
			"Task", "TASK-READABLE", "Hourly", READER
		) + follow.core.get_comments("Task", "TASK-READABLE", "Hourly", READER)
		message, _docinfo = follow.get_message_for_user("Hourly", READER)
		self.assertEqual(message, sorted(expected, key=lambda item: item["time"], reverse=True))
		self.assertEqual(
			{item["type"] for item in message}, {"comment", "field changed", "row changed", "row added"}
		)

	def test_granted_higher_permlevel_and_administrator_keep_visible_field_changes(self):
		self.versions = [
			{
				"type": "field changed",
				"data": {"field": "secret-field", "from": "old", "to": "new"},
				"time": NOW,
				"doctype": "Task",
				"doc_name": "TASK-READABLE",
			}
		]
		self.permlevels.add(1)
		self.assertEqual(follow.get_message_for_user("Hourly", READER)[0], self.versions)
		self.permlevels.clear()
		self.assertEqual(follow.get_message_for_user("Hourly", "Administrator")[0], self.versions)

	def test_standard_frequency_filters_and_own_changes_are_preserved(self):
		self.comment("own", modified_by=READER)
		self.comment("recent")
		self.comment("yesterday", modified=NOW - timedelta(days=1))
		self.comment("last-week", modified=NOW - timedelta(days=4))
		for frequency, expected in [
			("Hourly", {"CONTENT-recent"}),
			("Daily", {"CONTENT-yesterday"}),
			("Weekly", {"CONTENT-yesterday", "CONTENT-last-week"}),
		]:
			with self.subTest(frequency=frequency):
				self.settings.document_follow_frequency = frequency
				message, _docinfo = follow.get_message_for_user(frequency, READER)
				self.assertEqual({item["data"]["comment"].strip() for item in message}, expected)
				self.assertEqual(
					self.query.call_args.kwargs["filters"][2:], follow.core._get_filters(frequency, READER)
				)


class TestFollowScheduler(FollowFixture, unittest.TestCase):
	def setUp(self):
		# Resolve the native controller from real installed app hooks. Bypass only
		# shared Redis hook caches in this process; no site setting is persisted.
		self.jobs = {}
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			registered = frappe.get_hooks("scheduler_events", app_name="frappe")
			controllers = frappe.controllers.setdefault(frappe.local.site, {})
			previous = controllers.pop("Scheduled Job Type", None)
			try:
				for method in FOLLOW_METHODS:
					event = next(event for event, methods in registered.items() if method in methods)
					job = frappe.get_doc(
						{
							"doctype": "Scheduled Job Type",
							"method": method,
							"frequency": event.replace("_", " ").title(),
						}
					)
					self.assertIsInstance(job, DinextScheduledJobType)
					self.jobs[method] = job
			finally:
				controllers.pop("Scheduled Job Type", None)
				if previous:
					controllers["Scheduled Job Type"] = previous
		super().setUp()

	def get_doc(self, doctype, name):
		if doctype == "Scheduled Job Type":
			return self.jobs[name["method"]]
		return super().get_doc(doctype, name)

	def test_all_real_scheduler_follow_paths_render_only_authorized_activity(self):
		from frappe.core.doctype.scheduled_job_type.scheduled_job_type import run_scheduled_job

		self.comment("public")
		self.comment("hidden", "Visible to only you", modified_by="hidden-author@example.test")
		for frequency, method in zip(("Hourly", "Daily", "Weekly"), FOLLOW_METHODS, strict=True):
			with self.subTest(frequency=frequency):
				self.settings.document_follow_frequency = frequency
				for comment in self.comments.values():
					comment.modified = NOW - (
						timedelta(minutes=5) if frequency == "Hourly" else timedelta(days=1)
					)
				job = self.jobs[method]
				with patch.object(job, "log_status") as log, patch.dict(frappe.conf, {"maintenance_mode": 0}):
					run_scheduled_job(method)
					self.assertEqual([call.args[0] for call in log.call_args_list], ["Start", "Complete"])
				self.assertEqual(job.method, method)
		self.assertEqual(self.mail.call_count, 3)
		self.assert_no_disclosure(["CONTENT-hidden", "hidden-author@example.test"])

	def test_unrelated_jobs_and_server_scripts_keep_standard_execution(self):
		from frappe.core.doctype.scheduled_job_type.scheduled_job_type import ScheduledJobType

		job = next(iter(self.jobs.values()))
		for method, script in [("other_app.tasks.run", None), (next(iter(FOLLOW_METHODS)), "SCRIPT")]:
			with self.subTest(method=method, script=script):
				job.method, job.server_script = method, script
				seen = []
				with patch.object(
					ScheduledJobType,
					"execute",
					autospec=True,
					side_effect=lambda doc: seen.append(doc.method),
				):
					job.execute()
				self.assertEqual(seen, [method])
				self.assertEqual(job.method, method)

	def test_registered_schedules_enqueue_the_existing_job_wrapper(self):
		from frappe.core.doctype.scheduled_job_type import scheduled_job_type

		registered = frappe.get_hooks("scheduler_events", app_name="frappe")
		for method, job in self.jobs.items():
			event = job.frequency.lower().replace(" ", "_")
			self.assertIn(method, registered[event])
			with (
				patch.object(job, "is_event_due", return_value=False),
				patch.object(job, "is_job_in_queue", return_value=False),
				patch.object(scheduled_job_type, "enqueue") as enqueue,
			):
				self.assertTrue(job.enqueue(force=True))
				self.assertEqual(
					enqueue.call_args.args[0],
					"frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job",
				)
				self.assertEqual(enqueue.call_args.kwargs["job_type"], method)
				self.assertEqual(enqueue.call_args.kwargs["job_id"], f"scheduled_job::{method}")
				self.assertEqual(enqueue.call_args.kwargs["queue"], job.get_queue_name())

	def test_method_restored_when_standard_executor_raises(self):
		from frappe.core.doctype.scheduled_job_type.scheduled_job_type import ScheduledJobType

		job = next(iter(self.jobs.values()))
		method = job.method
		with patch.object(ScheduledJobType, "execute", side_effect=RuntimeError("executor failed")):
			with self.assertRaisesRegex(RuntimeError, "executor failed"):
				job.execute()
		self.assertEqual(job.method, method)
