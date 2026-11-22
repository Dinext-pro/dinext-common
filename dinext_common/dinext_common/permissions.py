import logging
import os
import tempfile

import frappe


def _candidate_log_dirs(preferred=None):
	candidates = []
	if preferred:
		candidates.append(preferred)
	try:
		bench_path = frappe.utils.get_bench_path()
	except Exception:
		bench_path = None
	if bench_path:
		candidates.append(os.path.join(bench_path, "logs"))
	candidates.append(tempfile.gettempdir())
	seen = set()
	for path in candidates:
		if not path or path in seen:
			continue
		seen.add(path)
		yield path


def _writable_log_dir(preferred=None):
	for path in _candidate_log_dirs(preferred):
		try:
			os.makedirs(path, exist_ok=True)
		except OSError:
			continue
		if os.access(path, os.W_OK):
			return path
	return None


def get_custom_logger(
	name="dinext_projects",
	log_file="has_permission.log",
	log_dir=None,
	level=logging.INFO,
):
	logger = logging.getLogger(name)
	logger.setLevel(level)

	if logger.hasHandlers():
		return logger

	resolved = _writable_log_dir(log_dir)
	if resolved:
		try:
			file_handler = logging.FileHandler(os.path.join(resolved, log_file))
			file_handler.setLevel(level)
			file_handler.setFormatter(
				logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
			)
			logger.addHandler(file_handler)
			return logger
		except OSError:
			pass

	logger.addHandler(logging.NullHandler())
	return logger


logger = get_custom_logger()
logger.info("dinext_projects.permissions loaded successfully")


@frappe.whitelist()
def has_permission(
	doctype,
	ptype="read",
	doc=None,
	user=None,
	raise_exception=True,
	*,
	parent_doctype=None,
	debug=False,
) -> bool:
	from frappe.permissions import has_permission as og_has_permission

	cur_user = frappe.session.user
	if user:
		frappe.set_user(user)
		logger.info(f"user set to: '{user}'")

	try:
		return og_has_permission(
			doctype=doctype,
			ptype=ptype,
			doc=doc,
			user=user,
			raise_exception=raise_exception,
			parent_doctype=parent_doctype,
			debug=debug,
		)
	finally:
		if user:
			frappe.set_user(cur_user)
			logger.info(f"user set back to: '{cur_user}'")


@frappe.whitelist()
def get_doc_permissions(doctype, doc, user=None, ptype=None, debug=False):
	meta = frappe.get_meta(doctype)
	doc = frappe.get_doc(meta.name, doc)

	cur_user = frappe.session.user
	if user:
		frappe.set_user(user)

	from frappe.permissions import get_doc_permissions as og_get_doc_permissions

	res = og_get_doc_permissions(doc=doc, user=user, ptype=ptype, debug=debug)

	if user:
		frappe.set_user(cur_user)

	return res


@frappe.whitelist()
def get_users_with_role(role: str) -> list[str]:
	from frappe.utils.user import get_users_with_role as og_get_users_with_role

	cur_user = frappe.session.user
	frappe.set_user("Administrator")

	try:
		return og_get_users_with_role(role)
	finally:
		frappe.set_user(cur_user)
