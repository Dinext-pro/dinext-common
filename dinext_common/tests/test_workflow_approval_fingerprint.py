import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal


class TestWorkflowApprovalFingerprint(unittest.TestCase):
	def fingerprint(self):
		try:
			from dinext_common.workflow_approval import fingerprint
		except ModuleNotFoundError as exc:
			self.fail(f"workflow approval fingerprint module is missing: {exc}")
		return fingerprint

	def fields(self):
		return [
			{"fieldname": "title", "fieldtype": "Data"},
			{"fieldname": "amount", "fieldtype": "Currency"},
			{"fieldname": "attachment", "fieldtype": "Attach"},
			{"fieldname": "link_type", "fieldtype": "Link"},
			{"fieldname": "dynamic_link", "fieldtype": "Dynamic Link", "options": "link_type"},
			{"fieldname": "payload", "fieldtype": "JSON"},
			{"fieldname": "event_at", "fieldtype": "Datetime"},
			{"fieldname": "rows", "fieldtype": "Table"},
			{"fieldname": "workflow_state", "fieldtype": "Data"},
			{"fieldname": "derived_status", "fieldtype": "Data"},
			{"fieldname": "secret", "fieldtype": "Password"},
			{"fieldname": "virtual_total", "fieldtype": "Float", "virtual": 1},
		]

	def document(self):
		return {
			"name": "DOC-001",
			"owner": "owner@example.com",
			"modified": "2026-01-01 10:00:00",
			"title": "Example",
			"amount": Decimal("12.3400"),
			"attachment": "/files/example.pdf",
			"link_type": "Project",
			"dynamic_link": "PROJ-001",
			"payload": '{"b": 2, "a": [3, 1]}',
			"event_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
			"rows": [
				{"name": "ROW-1", "idx": 1, "description": "First", "hours": Decimal("1.5")},
				{"name": "ROW-2", "idx": 2, "description": "Second", "hours": Decimal("2")},
			],
			"workflow_state": "Pending",
			"derived_status": "Waiting",
			"secret": "encrypted",
			"virtual_total": 3.5,
		}

	def test_fingerprint_excludes_framework_workflow_password_and_virtual_fields(self):
		fingerprint = self.fingerprint()
		base = fingerprint.fingerprint_document(
			self.document(),
			self.fields(),
			workflow_state_field="workflow_state",
			workflow_update_field="derived_status",
		)
		changed = {
			**self.document(),
			"modified": "2027-02-03 11:22:33",
			"workflow_state": "Approved",
			"derived_status": "Done",
			"secret": "different",
			"virtual_total": 99,
		}

		self.assertEqual(
			base.digest,
			fingerprint.fingerprint_document(
				changed,
				self.fields(),
				workflow_state_field="workflow_state",
				workflow_update_field="derived_status",
			).digest,
		)

	def test_business_field_and_hook_exclusions_are_distinct(self):
		fingerprint = self.fingerprint()
		base = fingerprint.fingerprint_document(self.document(), self.fields())
		changed_title = fingerprint.fingerprint_document(
			{**self.document(), "title": "Changed"},
			self.fields(),
		)
		excluded_title = fingerprint.fingerprint_document(
			{**self.document(), "title": "Changed"},
			self.fields(),
			excluded_fields={"title"},
		)
		base_excluded_title = fingerprint.fingerprint_document(
			self.document(),
			self.fields(),
			excluded_fields={"title"},
		)

		self.assertNotEqual(base.digest, changed_title.digest)
		self.assertEqual(base_excluded_title.digest, excluded_title.digest)

	def test_json_decimal_datetime_dynamic_link_and_attachment_are_canonical(self):
		fingerprint = self.fingerprint()
		alternate = {
			**self.document(),
			"amount": Decimal("12.34"),
			"payload": {"a": [3, 1], "b": 2},
			"event_at": datetime(2026, 1, 1, 15, 0, tzinfo=timezone(timedelta(hours=3))),
		}
		first = fingerprint.fingerprint_document(self.document(), self.fields())
		second = fingerprint.fingerprint_document(alternate, self.fields())
		payload = json.loads(first.canonical_json)

		self.assertEqual(first.digest, second.digest)
		self.assertEqual(payload["values"]["attachment"], "/files/example.pdf")
		self.assertEqual(payload["values"]["link_type"], "Project")
		self.assertEqual(payload["values"]["dynamic_link"], "PROJ-001")

	def test_child_identifiers_are_ignored_but_order_and_content_matter(self):
		fingerprint = self.fingerprint()
		base = fingerprint.fingerprint_document(self.document(), self.fields())
		renamed_rows = {
			**self.document(),
			"rows": [
				{"name": "NEW-1", "idx": 9, "description": "First", "hours": Decimal("1.5")},
				{"name": "NEW-2", "idx": 8, "description": "Second", "hours": Decimal("2")},
			],
		}
		reordered = {**self.document(), "rows": list(reversed(self.document()["rows"]))}
		edited = {
			**self.document(),
			"rows": [{**self.document()["rows"][0], "hours": Decimal("2.5")}],
		}

		self.assertEqual(
			base.digest,
			fingerprint.fingerprint_document(renamed_rows, self.fields()).digest,
		)
		self.assertNotEqual(
			base.digest,
			fingerprint.fingerprint_document(reordered, self.fields()).digest,
		)
		self.assertNotEqual(
			base.digest,
			fingerprint.fingerprint_document(edited, self.fields()).digest,
		)

	def test_child_documents_ignore_recreated_row_names(self):
		class Row:
			def __init__(self, payload):
				self.payload = payload

			def as_dict(self):
				return self.payload

		fingerprint = self.fingerprint()
		base = fingerprint.fingerprint_document(self.document(), self.fields())
		recreated = {
			**self.document(),
			"rows": [
				Row({"name": "OTHER-1", "idx": 3, "description": "First", "hours": Decimal("1.5")}),
				Row({"name": "OTHER-2", "idx": 4, "description": "Second", "hours": Decimal("2")}),
			],
		}

		self.assertEqual(
			base.digest,
			fingerprint.fingerprint_document(recreated, self.fields()).digest,
		)

	def test_metadata_field_addition_is_fail_closed(self):
		fingerprint = self.fingerprint()
		base = fingerprint.fingerprint_document(self.document(), self.fields())
		fields_with_new_business_field = [
			*self.fields(),
			{"fieldname": "new_business_field", "fieldtype": "Data"},
		]

		self.assertNotEqual(
			base.digest,
			fingerprint.fingerprint_document(
				{**self.document(), "new_business_field": None},
				fields_with_new_business_field,
			).digest,
		)

	def test_fingerprint_version_is_explicit(self):
		fingerprint = self.fingerprint()

		result = fingerprint.fingerprint_document(self.document(), self.fields())

		self.assertEqual(result.version, fingerprint.FINGERPRINT_VERSION)
		self.assertTrue(result.digest)

	def test_latest_matching_task_is_authoritative_without_older_fallback(self):
		fingerprint = self.fingerprint()
		criteria = {
			"approver": "alice@example.com",
			"reference_doctype": "Example",
			"reference_name": "DOC-001",
			"source_created_at": "2026-01-01 00:00:00",
			"workflow": "Example Workflow",
			"transition_uuid": "transition-1",
			"transition_semantic_hash": "semantic-1",
			"content_fingerprint_version": fingerprint.FINGERPRINT_VERSION,
			"content_fingerprint": "wanted",
		}
		tasks = [
			{**criteria, "name": "old", "status": "Completed", "completed_at": "2026-01-02",},
			{
				**criteria,
				"name": "latest",
				"status": "Completed",
				"completed_at": "2026-01-03",
				"content_fingerprint": "different",
			},
		]

		self.assertIsNone(fingerprint.find_latest_reusable_task(tasks, **criteria))

		tasks[1]["content_fingerprint"] = "wanted"
		self.assertEqual(
			fingerprint.find_latest_reusable_task(tasks, **criteria)["name"],
			"latest",
		)

	def test_source_creation_workflow_and_semantic_hash_are_reuse_boundaries(self):
		fingerprint = self.fingerprint()
		criteria = {
			"approver": "alice@example.com",
			"reference_doctype": "Example",
			"reference_name": "DOC-001",
			"source_created_at": "2026-01-01 00:00:00",
			"workflow": "Example Workflow",
			"transition_uuid": "transition-1",
			"transition_semantic_hash": "semantic-1",
			"content_fingerprint_version": fingerprint.FINGERPRINT_VERSION,
			"content_fingerprint": "wanted",
		}
		task = {**criteria, "status": "Completed", "completed_at": "2026-01-02"}

		for field, value in (
			("source_created_at", "2026-02-01 00:00:00"),
			("workflow", "Other Workflow"),
			("transition_semantic_hash", "changed"),
		):
			candidate = {**task, field: value}
			self.assertIsNone(fingerprint.find_latest_reusable_task([candidate], **criteria))

	def test_child_exclusion_is_scoped_to_its_table_and_keeps_business_fields(self):
		fingerprint = self.fingerprint()
		fields = [
			{"fieldname": "rows", "fieldtype": "Table"},
			{"fieldname": "other_rows", "fieldtype": "Table"},
			{"fieldname": "payload", "fieldtype": "JSON"},
		]
		document = {
			"rows": [{"date": "2026-10-12", "hours": 8.0, "description": "Work", "utilized_hours": 8.0}],
			"other_rows": [{"utilized_hours": 8.0}],
			"payload": {"utilized_hours": 8.0},
		}
		options = {"excluded_fields": {"rows.utilized_hours"}}
		base = fingerprint.fingerprint_document(document, fields, **options).digest
		changed = deepcopy(document)
		changed["rows"][0]["utilized_hours"] = 0.0
		self.assertEqual(base, fingerprint.fingerprint_document(changed, fields, **options).digest)
		for field, value in (("date", "2026-10-13"), ("hours", 7.0), ("description", "Other work")):
			with self.subTest(field=field):
				changed = deepcopy(document)
				changed["rows"][0][field] = value
				self.assertNotEqual(base, fingerprint.fingerprint_document(changed, fields, **options).digest)
		for field in ("other_rows", "payload"):
			with self.subTest(field=field):
				changed = deepcopy(document)
				row = changed[field][0] if field == "other_rows" else changed[field]
				row["utilized_hours"] = 0.0
				self.assertNotEqual(base, fingerprint.fingerprint_document(changed, fields, **options).digest)

	def test_document_like_children_apply_nested_exclusions_without_reordering(self):
		class Row:
			def __init__(self, hours, utilized):
				self.hours, self.utilized = hours, utilized

			def as_dict(self):
				return {"hours": self.hours, "utilized_hours": self.utilized}

		fingerprint = self.fingerprint()
		fields = [{"fieldname": "rows", "fieldtype": "Table"}]
		options = {"excluded_fields": {"rows.utilized_hours"}}
		first = [Row(8.0, 8.0), Row(4.0, 4.0)]
		second = [Row(8.0, 0.0), Row(4.0, 0.0)]
		base = fingerprint.fingerprint_document({"rows": first}, fields, **options).digest
		self.assertEqual(base, fingerprint.fingerprint_document({"rows": second}, fields, **options).digest)
		self.assertNotEqual(
			base, fingerprint.fingerprint_document({"rows": list(reversed(second))}, fields, **options).digest
		)

	def test_child_bookkeeping_is_ignored_but_unknown_private_business_values_remain(self):
		fingerprint = self.fingerprint()
		fields = [{"fieldname": "rows", "fieldtype": "Table"}]
		row = {"hours": 8.0, "_business_code": "A"}
		base = fingerprint.fingerprint_document({"rows": [row]}, fields).digest
		for key in (
			"__islocal",
			"__unsaved",
			"__onload",
			"__run_link_triggers",
			"_assign",
			"_comments",
			"_liked_by",
			"_seen",
			"_user_tags",
		):
			with self.subTest(key=key):
				changed = {"rows": [{**row, key: "transient"}]}
				self.assertEqual(base, fingerprint.fingerprint_document(changed, fields).digest)
		self.assertNotEqual(
			base,
			fingerprint.fingerprint_document({"rows": [{**row, "_business_code": "B"}]}, fields).digest,
		)
