"""Real fixture imports preserve administrator settings, including an empty list."""

from copy import deepcopy

import frappe
from frappe.modules.import_file import import_doc
from frappe.tests.utils import FrappeTestCase

from dinext_common.workflow_approval.exclusions import EXCLUSIONS_FIELD


class TestWorkflowFingerprintFixtures(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.previous_flags = {key: frappe.flags.get(key) for key in ("in_fixtures", "in_import")}
		self.addCleanup(lambda: frappe.flags.update(self.previous_flags))
		self.workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": "_Test snapshot fixture " + frappe.generate_hash(length=8),
				"document_type": "ToDo",
				"workflow_state_field": "status",
				"is_active": 0,
				EXCLUSIONS_FIELD: [{"field_path": "description"}],
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)
		self.fixture = deepcopy(self.workflow.as_dict())
		self.fixture[EXCLUSIONS_FIELD] = [{"field_path": "priority"}]

	def test_fixture_reimport_preserves_custom_rows_and_their_identity(self):
		original = self.workflow.custom_fingerprint_excluded_fields[0].name
		frappe.flags.in_fixtures = True
		import_doc(self.fixture)
		self.workflow.reload()
		self.assertEqual([row.field_path for row in self.workflow.get(EXCLUSIONS_FIELD)], ["description"])
		self.assertEqual(self.workflow.get(EXCLUSIONS_FIELD)[0].name, original)

	def test_fixture_reimport_does_not_restore_intentionally_removed_defaults(self):
		self.workflow.set(EXCLUSIONS_FIELD, [])
		self.workflow.update_child_table(EXCLUSIONS_FIELD)
		frappe.flags.in_fixtures = True
		import_doc(self.fixture)
		self.workflow.reload()
		self.assertEqual(self.workflow.get(EXCLUSIONS_FIELD), [])

	def test_first_fixture_import_keeps_packaged_defaults(self):
		frappe.delete_doc("Workflow", self.workflow.name, force=True, ignore_permissions=True)
		frappe.flags.in_fixtures = True
		import_doc(self.fixture)
		self.workflow.reload()
		self.assertEqual([row.field_path for row in self.workflow.get(EXCLUSIONS_FIELD)], ["priority"])

	def test_explicit_import_outside_fixtures_can_replace_settings(self):
		frappe.flags.in_fixtures = False
		import_doc(self.fixture)
		self.workflow.reload()
		self.assertEqual([row.field_path for row in self.workflow.get(EXCLUSIONS_FIELD)], ["priority"])
