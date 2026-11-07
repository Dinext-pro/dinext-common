# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from dinext_common.changelog_feed import setup_dinext_news_feed
from dinext_common.apps import ensure_default_apps
from dinext_common.setup.workspace import configure_workspace_menu


def after_install() -> None:
	from dinext_common.workflow_approval.email_metadata import ensure_workflow_email_fields
	ensure_workflow_email_fields()
	from dinext_common.workflow_approval.metadata import ensure_workflow_fingerprint_fields

	ensure_workflow_fingerprint_fields()
	setup_dinext_news_feed()
	configure_workspace_menu()
	ensure_default_apps()
