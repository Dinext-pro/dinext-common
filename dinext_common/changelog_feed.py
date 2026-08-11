# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Dinext What's New publisher (docs site) and consumer sync (ERP sites)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

import frappe
from frappe.utils.data import add_to_date, get_datetime

DEFAULT_NEWS_FEED_URL = "https://docs.dinext.ru"
CONF_KEY_NEWS_FEED_URL = "dinext_news_feed_url"
FRAPPE_CHANGELOG_FETCH_METHOD = (
	"frappe.desk.doctype.changelog_feed.changelog_feed.fetch_changelog_feed"
)
PUBLISHER_METHOD_PATH = "dinext_common.changelog_feed.get_published_feed"
SOURCE_DOCTYPE = "Dinext News Feed"
FEED_LIMIT = 20


def get_publisher_base_url() -> str:
	"""Resolve publisher site base URL from site config (default docs.dinext.ru)."""
	raw = frappe.conf.get(CONF_KEY_NEWS_FEED_URL)
	if raw is None or (isinstance(raw, str) and not raw.strip()):
		return DEFAULT_NEWS_FEED_URL
	return str(raw).strip().rstrip("/")


def _normalize_since(since: Any):
	if since is None or since == "":
		return add_to_date(None, months=-1, as_datetime=True, as_string=False)
	return get_datetime(since)


@frappe.whitelist(allow_guest=True)
def get_published_feed(since=None) -> list[dict]:
	"""Public publisher API: published Dinext News Feed rows as Frappe What's New items."""
	if not frappe.db.exists("DocType", SOURCE_DOCTYPE):
		return []

	since_dt = _normalize_since(since)
	rows = frappe.db.get_all(
		SOURCE_DOCTYPE,
		filters={
			"is_published": 1,
			"posting_timestamp": (">", since_dt),
		},
		fields=["title", "app_name", "link", "posting_timestamp"],
		order_by="posting_timestamp desc",
		limit=FEED_LIMIT,
	)
	return [
		{
			"title": row.title,
			"app_name": row.app_name,
			"link": row.link,
			"creation": row.posting_timestamp,
		}
		for row in rows
	]


def _fetch_from_publisher(since) -> list[dict]:
	"""HTTP-fetch publisher feed; raises on network/HTTP/JSON errors."""
	base = get_publisher_base_url()
	url = urljoin(base + "/", f"api/method/{PUBLISHER_METHOD_PATH}")
	response = requests.get(url, params={"since": since}, timeout=30)
	response.raise_for_status()
	payload = response.json()
	message = payload.get("message")
	if message is None:
		return []
	if not isinstance(message, list):
		raise ValueError("Publisher response message must be a list")
	return message[:FEED_LIMIT]


def get_feed(since) -> list[dict]:
	"""`get_changelog_feed` hook: return feed items or [] on failure."""
	try:
		return _fetch_from_publisher(since) or []
	except Exception:
		frappe.log_error(title="Dinext News Feed: failed to fetch publisher")
		return []


def disable_frappe_changelog_fetch() -> None:
	"""Stop Frappe's built-in weekly changelog aggregation job."""
	job_name = frappe.db.exists("Scheduled Job Type", {"method": FRAPPE_CHANGELOG_FETCH_METHOD})
	if not job_name:
		return
	frappe.db.set_value("Scheduled Job Type", job_name, "stopped", 1, update_modified=False)


def clear_changelog_caches() -> None:
	"""Invalidate Desk boot changelog cache and shared fetch caches."""
	from frappe.desk.doctype.changelog_feed.changelog_feed import get_changelog_feed_items

	get_changelog_feed_items.clear_cache()
	# Drop Frappe per-hook shared caches if present
	for fn in frappe.get_hooks("get_changelog_feed") or []:
		frappe.cache.delete_value(f"changelog_feed::{fn}", shared=True)


def sync_dinext_news_feed() -> bool:
	"""Fetch from publisher; on success replace local Changelog Feed. Returns success."""
	since = add_to_date(None, years=-10, as_datetime=True, as_string=False)
	try:
		items = _fetch_from_publisher(since) or []
	except Exception:
		frappe.log_error(title="Dinext News Feed: sync aborted, local feed unchanged")
		return False

	frappe.db.truncate("Changelog Feed")
	for feed_item in items:
		feed = {
			"title": feed_item.get("title"),
			"app_name": feed_item.get("app_name"),
			"link": feed_item.get("link"),
			"posting_timestamp": feed_item.get("creation"),
		}
		if not all(feed.get(key) for key in ("title", "link", "posting_timestamp")):
			continue
		frappe.get_doc({"doctype": "Changelog Feed", **feed}).insert(ignore_permissions=True)

	clear_changelog_caches()
	return True


def setup_dinext_news_feed() -> None:
	"""Install/migrate: stop core job and run owned sync."""
	disable_frappe_changelog_fetch()
	clear_changelog_caches()
	sync_dinext_news_feed()


def on_after_migrate() -> None:
	setup_dinext_news_feed()
