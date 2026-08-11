# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from dinext_common.changelog_feed import setup_dinext_news_feed


def after_install() -> None:
	setup_dinext_news_feed()
