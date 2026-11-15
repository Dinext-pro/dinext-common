import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.tests.utils import FrappeTestCase

from dinext_common.workflow_approval import retention
from dinext_common.workflow_approval.scenarios import service

TODAY = date(2000, 5, 1)
CREATED = datetime(1999, 1, 1)


class TestDataCleanupRules(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.prefix = f"retention-{frappe.generate_hash(length=10)}"
		self.rows = 0

	def _insert(self, doctype, **values):
		self.rows += 1
		doc = frappe.get_doc(
			{
				"doctype": doctype,
				"name": f"{self.prefix}-{self.rows}",
				"creation": CREATED,
				"modified": CREATED,
				"owner": "Administrator",
				"modified_by": "Administrator",
				**values,
			}
		)
		doc.db_insert()
		return doc

	def _history(self, doctype="ToDo", age=45, *, status="Completed", source=None, last=True):
		identity = {
			"reference_doctype": doctype,
			"reference_name": source.name if source else f"{self.prefix}-missing-{self.rows}",
			"source_created_at": source.creation if source else CREATED,
		}
		key = service.source_key(
			frappe._dict(
				doctype=doctype, name=identity["reference_name"], creation=identity["source_created_at"]
			)
		)
		timestamp = datetime.combine(TODAY - timedelta(days=age), time())
		process = self._insert(
			"Workflow Process",
			source_key=key,
			status=status,
			completed_at=timestamp,
			automatic_transition_count=13,
			**identity,
		)
		context = self._insert(
			"Workflow Document Context",
			name=key,
			modified=timestamp,
			last_process=process.name if last else None,
			**identity,
		)
		return process, context

	def _rule(self, doctype=None, days=30, status="Completed", enabled=1):
		return {
			"reference_doctype": doctype,
			"days": days,
			"enabled": enabled,
			"status": status,
		}

	def _save_rules(self, rows):
		rules = frappe.get_single("Data Cleanup Rules")
		rules.set("workflow_rules", rows)
		rules.save(ignore_permissions=True)

	def _cleanup(self, run=retention.cleanup_workflow_approval_rounds):
		# Fence real data and keep each worker transaction inside the test transaction.
		savepoint = "test_workflow_cleanup_item"
		frappe.db.savepoint(savepoint)
		rollback = frappe.db.rollback
		with (
			patch.object(retention, "getdate", return_value=TODAY),
			patch.object(frappe.db, "commit", side_effect=lambda: frappe.db.savepoint(savepoint)),
			patch.object(frappe.db, "rollback", side_effect=lambda: rollback(save_point=savepoint)),
		):
			return run()

	def _assert_present(self, *docs):
		for doc in docs:
			self.assertTrue(frappe.db.exists(doc.doctype, doc.name), (doc.doctype, doc.name))

	def _assert_deleted(self, *docs):
		for doc in docs:
			self.assertFalse(frappe.db.exists(doc.doctype, doc.name), (doc.doctype, doc.name))

	def test_reference_doctypes_have_independent_cutoffs(self):
		self._save_rules([self._rule("ToDo", 30), self._rule("Note", 90)])
		todo = self._history("ToDo", 45)
		note = self._history("Note", 45)
		old_note = self._history("Note", 100)
		event = self._history("Event", 100)

		self._cleanup()

		self._assert_deleted(*todo, *old_note)
		self._assert_present(*note, *event)

	def test_overlapping_rules_are_independent_of_order_and_status(self):
		rules = [
			self._rule("ToDo", 90, ""),
			self._rule("ToDo", 1, "Open"),
			self._rule("ToDo", 30),
			self._rule("ToDo", 1, enabled=0),
			self._rule("ToDo", -5),
		]
		for rows in (rules, list(reversed(rules))):
			with self.subTest(rows=rows):
				self._save_rules(rows)
				expired = self._history(age=45, status="Cancelled")
				fresh = self._history(age=20)
				boundary = self._history(age=30)
				active = self._history(age=100, status="Running")

				self._cleanup()
				self._cleanup()

				self._assert_deleted(*expired)
				self._assert_present(*fresh, *boundary, *active)

	def test_default_rule_and_doctype_rule_both_apply(self):
		self._save_rules([self._rule(days=90, status=""), self._rule("ToDo", 30)])
		expired_todo = self._history("ToDo", 45, status="Archived")
		old_note = self._history("Note", 100)
		fresh_note = self._history("Note", 45)

		self._cleanup()

		self._assert_deleted(*expired_todo, *old_note)
		self._assert_present(*fresh_note)

	def test_related_round_and_action_are_removed_before_process_and_context(self):
		self._save_rules([self._rule("ToDo")])
		process, context = self._history(age=90)
		task = self._insert(
			"Workflow Task",
			status="Completed",
			round_status="Transitioned",
			reference_doctype=process.reference_doctype,
			reference_name=process.reference_name,
			source_created_at=process.source_created_at,
			workflow_process=process.name,
			approval_round_id=self.prefix,
			completed_at=datetime(2000, 4, 15),
		)
		action = self._insert(
			"Workflow Action",
			status="Completed",
			custom_workflow_task=task.name,
			custom_notification_status="Skipped",
			reference_doctype=process.reference_doctype,
			reference_name=process.reference_name,
		)
		standalone = self._insert("Workflow Action", status="Completed", reference_doctype="ToDo")
		current_action = self._insert("Workflow Action", status="Open", reference_doctype="ToDo")

		self._cleanup()
		self._assert_present(task, action, process, context, current_action)
		self._assert_deleted(standalone)

		frappe.db.set_value("Workflow Task", task.name, "completed_at", CREATED)
		self.assertEqual(self._cleanup(), 1)
		self._assert_deleted(task, action, process, context)
		self._assert_present(current_action)

	def test_live_last_process_and_active_pointer_are_preserved(self):
		self._save_rules([self._rule("ToDo")])
		source = self._insert("ToDo", description=self.prefix)
		last, context = self._history(source=source)
		earlier = self._insert(
			"Workflow Process",
			reference_doctype=source.doctype,
			reference_name=source.name,
			source_created_at=source.creation,
			source_key=context.name,
			status="Completed",
			completed_at=CREATED,
		)
		pointed, orphan = self._history()
		frappe.db.set_value(orphan.doctype, orphan.name, "active_process", pointed.name)

		self._cleanup()

		self._assert_deleted(earlier)
		self._assert_present(last, context, pointed, orphan)
		self.assertEqual(service._cascade(source)[1], 13)

	def test_reused_source_name_does_not_keep_old_instance(self):
		self._save_rules([self._rule("ToDo")])
		source = self._insert("ToDo", description=self.prefix)
		old = self._history(source=source)
		source.creation = datetime(2000, 1, 1)
		frappe.db.set_value("ToDo", source.name, "creation", source.creation)
		current = self._history(source=source)

		self._cleanup()

		self._assert_deleted(*old)
		self._assert_present(source, *current)

	def test_failed_delete_restores_last_process(self):
		self._save_rules([self._rule("ToDo")])
		process, context = self._history()
		delete_doc = frappe.delete_doc

		def fail_process_delete(doctype, name, **kwargs):
			if (doctype, name) == (process.doctype, process.name):
				raise RuntimeError("test delete failure")
			return delete_doc(doctype, name, **kwargs)

		with patch.object(frappe, "delete_doc", side_effect=fail_process_delete):
			self._cleanup()

		self._assert_present(process, context)
		self.assertEqual(frappe.db.get_value(context.doctype, context.name, "last_process"), process.name)
		self._cleanup()
		self._assert_deleted(process, context)

	def test_context_is_preserved_while_unlinked_tasks_still_reference_its_instance(self):
		self._save_rules([self._rule("ToDo")])
		process, context = self._history()
		task = self._insert(
			"Workflow Task",
			status="Working",
			round_status="Open",
			reference_doctype=process.reference_doctype,
			reference_name=process.reference_name,
			source_created_at=process.source_created_at,
		)

		self._cleanup()

		self._assert_deleted(process)
		self._assert_present(context, task)

	def test_daily_script_enqueues_one_worker_that_cleans_history(self):
		self._save_rules([self._rule("ToDo")])
		process, context = self._history()
		path = Path(frappe.get_app_path("dinext_common", "fixtures", "server_script.json"))
		scripts = {row["name"]: row for row in json.loads(path.read_text())}
		daily = frappe.get_doc(scripts["Data Cleanup Daily"])
		worker = frappe.get_doc(scripts["Data Cleanup Workflow"])
		queued = []

		with patch(
			"frappe.utils.safe_exec.safe_enqueue", side_effect=lambda function, **_: queued.append(function)
		):
			daily.execute_scheduled_method()

		self.assertEqual(queued.count(worker.api_method), 1)
		self._assert_present(process, context)
		self._cleanup(worker.execute_method)
		self._assert_deleted(process, context)

	def test_fixture_import_preserves_saved_rules(self):
		self._save_rules([self._rule("ToDo", 27), self._rule("Note", 91, "", enabled=0)])
		with patch.dict(frappe.flags, in_fixtures=True):
			import_file_by_path(
				frappe.get_app_path("dinext_common", "fixtures", "data_cleanup_rules.json"),
				data_import=True,
				force=True,
			)
		rows = frappe.get_single("Data Cleanup Rules").workflow_rules
		self.assertEqual(
			[(row.reference_doctype, row.days, row.status or "", row.enabled) for row in rows],
			[("ToDo", 27, "Completed", 1), ("Note", 91, "", 0)],
		)
