# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from dinext_common.setup.workspace import configure_workspace_menu


def after_install() -> None:
	configure_workspace_menu()
