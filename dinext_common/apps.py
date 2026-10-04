"""Dinext application launcher visibility and default-app helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe

CONF_KEY_HIDDEN_APPS = "dinext_hidden_apps"
DEFAULT_HIDDEN_APPS = ("erpnext", "hrms")
DINEXT_DEFAULT_APP = "dinext_common"


def get_hidden_app_names() -> set[str]:
	"""Return normalized hidden launcher names from the current site configuration."""
	raw_apps = frappe.conf.get(CONF_KEY_HIDDEN_APPS)
	if raw_apps is None:
		return set(DEFAULT_HIDDEN_APPS)

	if isinstance(raw_apps, str):
		raw_apps = raw_apps.split(",")
	elif not isinstance(raw_apps, (list, tuple, set)):
		return set(DEFAULT_HIDDEN_APPS)

	return {
		app_name.strip().lower()
		for app_name in raw_apps
		if isinstance(app_name, str) and app_name.strip()
	}


def _app_name(app: Any) -> str:
	if isinstance(app, dict):
		return str(app.get("name") or "")
	return str(getattr(app, "name", "") or "")


def filter_hidden_apps(apps: Iterable[Any] | None) -> list[Any]:
	"""Exclude configured applications from a Frappe app-record collection."""
	hidden_apps = get_hidden_app_names()
	return [app for app in apps or [] if _app_name(app).lower() not in hidden_apps]


@frappe.whitelist()
def get_apps() -> list[Any]:
	"""Return Frappe app launchers after applying per-site visibility settings."""
	from frappe.apps import get_apps as original_get_apps

	return filter_hidden_apps(original_get_apps())


def configure_boot_app_filter(bootinfo) -> None:
	"""Use the filtered app provider before Frappe sessions builds ``apps_data``."""
	import frappe.sessions

	frappe.sessions.get_apps = get_apps


def update_website_context(context: Any) -> None:
	"""Filter app launchers and present guest login navigation."""
	if apps := context.get("apps"):
		context["apps"] = filter_hidden_apps(apps)

	request = getattr(frappe.local, "request", None)
	if not request or request.path.rstrip("/") != "/login":
		return

	context["brand_html"] = '<img src="/assets/dinext_common/images/dinext.png" alt="Dinext">'
	items = list(context.get("top_bar_items") or [])
	for label, url in (
		("Документация", "https://docs.dinext.ru"),
		("На главную", "/homepage"),  # noqa: RUF001 -- Cyrillic navigation label
	):
		if not any(item.get("url") == url for item in items):
			items.append(frappe._dict(label=label, url=url, right=1))
	context["top_bar_items"] = items


def needs_dinext_default_app(default_app: str | None) -> bool:
	"""Return whether an empty or hidden default app needs a Dinext fallback."""
	return not default_app or default_app.lower() in get_hidden_app_names()


def set_default_app_for_new_user(doc, method=None) -> None:
	"""Assign Dinext when a newly created user has no app preference."""
	if not needs_dinext_default_app(doc.default_app):
		return

	doc.db_set("default_app", DINEXT_DEFAULT_APP, update_modified=False)


def ensure_default_apps() -> None:
	"""Repair empty or hidden default app values during install and migration."""
	changed = False
	system_default_app = frappe.db.get_single_value("System Settings", "default_app")
	if needs_dinext_default_app(system_default_app):
		frappe.db.set_single_value(
			"System Settings",
			"default_app",
			DINEXT_DEFAULT_APP,
			update_modified=False,
		)
		changed = True

	for user in frappe.db.get_all(
		"User",
		filters={"user_type": "System User"},
		fields=["name", "default_app"],
	):
		user_name = _app_name(user)
		default_app = user.get("default_app") if isinstance(user, dict) else user.default_app
		if needs_dinext_default_app(default_app):
			frappe.db.set_value(
				"User",
				user_name,
				"default_app",
				DINEXT_DEFAULT_APP,
				update_modified=False,
			)
			changed = True

	if changed:
		frappe.clear_cache()
