import inspect
import logging
import os
import tempfile
import unittest
from unittest.mock import patch


class TestPermissionsLogger(unittest.TestCase):
	def test_default_log_dir_is_not_hardcoded_frappe_home(self):
		from dinext_common.dinext_common.permissions import get_custom_logger

		default_log_dir = inspect.signature(get_custom_logger).parameters["log_dir"].default
		self.assertNotEqual(default_log_dir, "/home/frappe/frappe-bench/logs")
		self.assertIn(default_log_dir, (None, inspect.Parameter.empty))

	def test_logger_initializes_when_frappe_home_cannot_be_created(self):
		from dinext_common.dinext_common import permissions

		logger_name = "dinext_common.tests.permissions_logger.missing_frappe_home"
		existing = logging.getLogger(logger_name)
		existing.handlers.clear()

		missing_home = "/home/frappe/frappe-bench/logs"
		with (
			patch.object(permissions.frappe.utils, "get_bench_path", return_value="/home/frappe/frappe-bench"),
			patch.object(permissions.os, "makedirs", side_effect=PermissionError("denied")),
			patch.object(permissions.os, "access", return_value=False),
		):
			logger = permissions.get_custom_logger(
				name=logger_name,
				log_file="has_permission_test.log",
				log_dir=missing_home,
			)

		self.assertTrue(logger.handlers)
		self.assertTrue(any(isinstance(handler, logging.NullHandler) for handler in logger.handlers))
		self.assertFalse(os.path.exists(missing_home))

	def test_logger_uses_bench_logs_when_writable(self):
		from dinext_common.dinext_common import permissions

		logger_name = "dinext_common.tests.permissions_logger.writable_bench"
		existing = logging.getLogger(logger_name)
		existing.handlers.clear()

		with tempfile.TemporaryDirectory() as bench_root:
			logs_dir = os.path.join(bench_root, "logs")
			with patch.object(permissions.frappe.utils, "get_bench_path", return_value=bench_root):
				logger = permissions.get_custom_logger(
					name=logger_name,
					log_file="has_permission_test.log",
					log_dir=None,
				)

			self.assertTrue(os.path.isdir(logs_dir))
			self.assertTrue(
				any(
					isinstance(handler, logging.FileHandler)
					and os.path.dirname(handler.baseFilename) == logs_dir
					for handler in logger.handlers
				)
			)
			for handler in list(logger.handlers):
				handler.close()
				logger.removeHandler(handler)
