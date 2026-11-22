"""Boot supplies destination styles without one request per rendered action."""

import unittest
from unittest.mock import patch

from dinext_common import boot


class TestWorkflowStateStyles(unittest.TestCase):
	def test_all_configured_styles_are_published_and_blank_styles_are_omitted(self):
		rows = [
			{"name": name, "style": name}
			for name in (
				"Primary",
				"Info",
				"Success",
				"Warning",
				"Danger",
				"Inverse",
			)
		]
		with patch.object(
			boot.frappe, "get_all", return_value=[*rows, {"name": "Blank", "style": ""}]
		) as query:
			self.assertEqual(boot.workflow_state_styles(), {row["name"]: row["style"] for row in rows})
		query.assert_called_once_with("Workflow State", fields=["name", "style"])

	def test_empty_state_catalog_is_supported(self):
		with patch.object(boot.frappe, "get_all", return_value=[]):
			self.assertEqual(boot.workflow_state_styles(), {})
