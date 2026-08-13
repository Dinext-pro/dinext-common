# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Typed whitelist contract for Dinext Workspace hub APIs."""

from __future__ import annotations

from typing import TypedDict


class WorkspaceHubFormInput(TypedDict, total=False):
	"""Input for `get_workspace_hub`."""

	settings_name: str


class WorkspaceHubCard(TypedDict):
	"""One navigation card in a hub section."""

	label: str
	description: str
	icon: str
	route: str


class WorkspaceHubCreateAction(TypedDict):
	"""Quick-create action shown in a section list bar."""

	doctype: str
	label: str
	icon: str


class WorkspaceHubRecord(TypedDict, total=False):
	"""One personal-list row (recent, assigned, liked, attention)."""

	doctype: str
	type_label: str
	icon: str
	name: str
	title: str
	modified: str
	route: str


class WorkspaceHubSectionLists(TypedDict, total=False):
	"""Personal lists attached to a hub section."""

	list_limit: int
	show_recently_opened: bool
	show_assigned: bool
	show_liked: bool
	show_attention: bool
	create_actions: list[WorkspaceHubCreateAction]
	recent: list[WorkspaceHubRecord]
	assigned: list[WorkspaceHubRecord]
	liked: list[WorkspaceHubRecord]
	attention: list[WorkspaceHubRecord]


class WorkspaceHubSection(TypedDict):
	"""One projected hub section."""

	label: str
	items: list[WorkspaceHubCard]
	lists: WorkspaceHubSectionLists | None
	list_limit: int
	card_columns: int


class WorkspaceHubResponse(TypedDict):
	"""Successful hub payload."""

	sections: list[WorkspaceHubSection]
