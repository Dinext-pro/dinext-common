import unittest
from unittest.mock import patch

import frappe

from dinext_common.workflow_approval import api


class TestWorkflowAPIValidation(unittest.TestCase):
	def test_source_transition_query_rejects_invalid_name_lists(self):
		with patch.object(api, "_", side_effect=lambda message: message):
			for names in ({}, {"selection": []}, "invalid-json", [[1]], [None], [4]):
				with self.subTest(names=names), self.assertRaises(frappe.ValidationError):
					api.get_my_source_transitions.__wrapped__("Application For Leave", names)

	def test_source_transition_query_accepts_empty_name_lists(self):
		self.assertEqual(api.get_my_source_transitions.__wrapped__("Application For Leave", []), {})
		self.assertEqual(api.get_my_source_transitions.__wrapped__("Application For Leave", "[]"), {})
