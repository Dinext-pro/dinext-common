# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime
from frappe.utils.data import add_to_date

from dinext_common.changelog_feed import (
	CONF_KEY_NEWS_FEED_URL,
	DEFAULT_NEWS_FEED_URL,
	FRAPPE_CHANGELOG_FETCH_METHOD,
	SOURCE_DOCTYPE,
	_fetch_from_publisher,
	disable_frappe_changelog_fetch,
	get_feed,
	get_published_feed,
	get_publisher_base_url,
	setup_dinext_news_feed,
	sync_dinext_news_feed,
)


class TestPublisherBaseUrl(unittest.TestCase):
	def test_default_url(self):
		with patch("dinext_common.changelog_feed.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = None
			self.assertEqual(get_publisher_base_url(), DEFAULT_NEWS_FEED_URL)
			mock_frappe.conf.get.assert_called_once_with(CONF_KEY_NEWS_FEED_URL)

	def test_override_url_strips_slash(self):
		with patch("dinext_common.changelog_feed.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = "https://news.example.test/"
			self.assertEqual(get_publisher_base_url(), "https://news.example.test")

	def test_empty_string_uses_default(self):
		with patch("dinext_common.changelog_feed.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = "  "
			self.assertEqual(get_publisher_base_url(), DEFAULT_NEWS_FEED_URL)


class TestGetFeedConsumer(unittest.TestCase):
	def test_get_feed_returns_items(self):
		items = [
			{
				"title": "A",
				"app_name": "dinext_projects",
				"link": "https://docs.example/a",
				"creation": "2026-01-01 00:00:00",
			}
		]
		with patch(
			"dinext_common.changelog_feed._fetch_from_publisher", return_value=items
		) as mock_fetch:
			self.assertEqual(get_feed("2020-01-01"), items)
			mock_fetch.assert_called_once()

	def test_get_feed_swallows_errors(self):
		with patch(
			"dinext_common.changelog_feed._fetch_from_publisher",
			side_effect=RuntimeError("boom"),
		), patch("dinext_common.changelog_feed.frappe") as mock_frappe:
			self.assertEqual(get_feed("2020-01-01"), [])
			mock_frappe.log_error.assert_called()


class TestFetchFromPublisher(unittest.TestCase):
	def test_builds_url_from_config(self):
		mock_response = MagicMock()
		mock_response.json.return_value = {"message": [{"title": "T", "app_name": "x", "link": "l", "creation": "c"}]}
		mock_response.raise_for_status = MagicMock()
		with patch(
			"dinext_common.changelog_feed.get_publisher_base_url",
			return_value="https://custom.example",
		), patch("dinext_common.changelog_feed.requests.get", return_value=mock_response) as mock_get:
			result = _fetch_from_publisher("2024-01-01")
			self.assertEqual(len(result), 1)
			args, kwargs = mock_get.call_args
			self.assertEqual(args[0], "https://custom.example/api/method/dinext_common.changelog_feed.get_published_feed")
			self.assertEqual(kwargs["params"]["since"], "2024-01-01")


class TestDinextNewsFeedIntegration(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete(SOURCE_DOCTYPE)
		frappe.db.truncate("Changelog Feed")

	def tearDown(self):
		frappe.db.delete(SOURCE_DOCTYPE)
		frappe.db.truncate("Changelog Feed")
		super().tearDown()

	def _insert_news(self, **kwargs):
		defaults = {
			"doctype": SOURCE_DOCTYPE,
			"title": "News",
			"app_name": "dinext_common",
			"link": "https://docs.dinext.ru/n",
			"posting_timestamp": now_datetime(),
			"is_published": 1,
		}
		defaults.update(kwargs)
		doc = frappe.get_doc(defaults)
		doc.insert(ignore_permissions=True)
		return doc

	def test_publisher_returns_only_published_and_respects_since(self):
		old_ts = add_to_date(None, days=-10, as_datetime=True)
		new_ts = add_to_date(None, days=-1, as_datetime=True)
		self._insert_news(title="Old", posting_timestamp=old_ts, is_published=1)
		self._insert_news(title="Draft", posting_timestamp=new_ts, is_published=0)
		self._insert_news(
			title="New",
			app_name="dinext_projects",
			posting_timestamp=new_ts,
			is_published=1,
		)

		since = add_to_date(None, days=-5, as_datetime=True)
		feed = get_published_feed(since=since)
		titles = [item["title"] for item in feed]
		self.assertIn("New", titles)
		self.assertNotIn("Old", titles)
		self.assertNotIn("Draft", titles)
		item = next(i for i in feed if i["title"] == "New")
		self.assertEqual(item["app_name"], "dinext_projects")
		self.assertEqual(set(item.keys()), {"title", "app_name", "link", "creation"})

	def test_sync_replaces_changelog_feed_on_success(self):
		frappe.get_doc(
			{
				"doctype": "Changelog Feed",
				"title": "From Frappe IO",
				"app_name": "frappe",
				"link": "https://frappe.io/x",
				"posting_timestamp": now_datetime(),
			}
		).insert(ignore_permissions=True)

		payload = [
			{
				"title": "Dinext A",
				"app_name": "dinext_projects",
				"link": "https://docs.dinext.ru/a",
				"creation": now_datetime(),
			},
			{
				"title": "Dinext B",
				"app_name": "dinext_common",
				"link": "https://docs.dinext.ru/b",
				"creation": now_datetime(),
			},
		]
		with patch(
			"dinext_common.changelog_feed._fetch_from_publisher", return_value=payload
		):
			self.assertTrue(sync_dinext_news_feed())

		rows = frappe.get_all("Changelog Feed", fields=["title", "app_name"])
		titles = {r.title for r in rows}
		self.assertEqual(titles, {"Dinext A", "Dinext B"})
		self.assertTrue(any(r.app_name == "dinext_projects" for r in rows))

	def test_sync_keeps_rows_on_fetch_failure(self):
		frappe.get_doc(
			{
				"doctype": "Changelog Feed",
				"title": "Keep Me",
				"app_name": "dinext_common",
				"link": "https://docs.dinext.ru/keep",
				"posting_timestamp": now_datetime(),
			}
		).insert(ignore_permissions=True)

		with patch(
			"dinext_common.changelog_feed._fetch_from_publisher",
			side_effect=RuntimeError("down"),
		), patch("dinext_common.changelog_feed.frappe.log_error"):
			self.assertFalse(sync_dinext_news_feed())

		self.assertTrue(frappe.db.exists("Changelog Feed", {"title": "Keep Me"}))

	def test_disable_frappe_changelog_fetch_sets_stopped(self):
		job_name = frappe.db.exists("Scheduled Job Type", {"method": FRAPPE_CHANGELOG_FETCH_METHOD})
		if not job_name:
			self.skipTest("Frappe changelog fetch Scheduled Job Type missing")
		frappe.db.set_value("Scheduled Job Type", job_name, "stopped", 0)
		disable_frappe_changelog_fetch()
		self.assertEqual(frappe.db.get_value("Scheduled Job Type", job_name, "stopped"), 1)

	def test_setup_calls_disable_and_sync(self):
		with patch(
			"dinext_common.changelog_feed.disable_frappe_changelog_fetch"
		) as mock_disable, patch(
			"dinext_common.changelog_feed.clear_changelog_caches"
		) as mock_clear, patch(
			"dinext_common.changelog_feed.sync_dinext_news_feed", return_value=True
		) as mock_sync:
			setup_dinext_news_feed()
			mock_disable.assert_called_once()
			mock_clear.assert_called_once()
			mock_sync.assert_called_once()
